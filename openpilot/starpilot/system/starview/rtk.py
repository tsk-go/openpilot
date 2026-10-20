"""The RTK receiver on the comma's USB hub (SparkFun ZED-F9R), for the tablet.

starviewd reads it: NAV-PVT arrives by itself 10x a second (the receiver keeps that setting in its own flash), NAV-SAT,
ESF-STATUS and ESF-ALG are asked for once a second (the F9R's HPS 1.00 accepted them as periodic outputs but never sent
them). RTK corrections (RTCM3) come from the tablet, which reaches the caster over its own internet (the comma has none in
the car), and are written to the receiver as they are. The tablet gets status() once a second in the params snapshot
("k"); it also builds the GGA sentence network RTK casters ask for from it.

Only a u-blox (USB vendor 1546) is ever opened: the blinker's Pico is another ttyACM on the same hub. Nothing here
reaches openpilot: the comma's own GPS still drives localization.
"""
import glob
import os
import select
import struct
import termios
import threading
import time

from openpilot.common.swaglog import cloudlog

PORT_GLOB = "/dev/serial/by-id/*u-blox*"
FRESH_S = 2.0
POLL_S = 1.0
RTCM_MAX = 64 * 1024        # never queue more than this for the receiver (old corrections are useless)
# NAV-PVT flags3 lastCorrectionAge -> upper bound in seconds
CORRECTION_AGE = (None, 1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120, 999)
FIX = ("none", "dead reckoning", "2D", "3D", "GNSS + dead reckoning", "time only")
FUSION = ("initializing", "on", "suspended", "disabled")
ALIGN = ("fixed angles", "learning roll/pitch", "learning heading", "coarse", "fine")


def ubx(cls: int, msg: int, payload: bytes = b"") -> bytes:
  body = struct.pack("<BBH", cls, msg, len(payload)) + payload
  a = b = 0
  for x in body:
    a = (a + x) & 0xFF
    b = (b + a) & 0xFF
  return b"\xb5\x62" + body + bytes((a, b))


def valset_ram(items) -> bytes:
  """CFG-VALSET to RAM only (the flash already holds them; this just makes sure, without wearing it)."""
  payload = struct.pack("<BBH", 0, 0x01, 0) + b"".join(struct.pack("<I", k) + v.to_bytes(n, "little") for k, v, n in items)
  return ubx(0x06, 0x8A, payload)


SETUP = valset_ram((
  (0x30210001, 100, 2),   # CFG-RATE-MEAS: 10 Hz
  (0x20110021, 4, 1),     # CFG-NAVSPG-DYNMODEL: automotive
  (0x20910009, 1, 1),     # CFG-MSGOUT-UBX_NAV_PVT_USB: every epoch
  (0x10770004, 1, 1),     # CFG-USBINPROT-RTCM3X: corrections in
  (0x10780002, 0, 1),     # CFG-USBOUTPROT-NMEA: off
))
POLLS = ubx(0x01, 0x35) + ubx(0x10, 0x10) + ubx(0x10, 0x14)   # NAV-SAT, ESF-STATUS, ESF-ALG


def _write_some(fd: int, data: bytes) -> int:
  """Bytes written to a non-blocking fd (0 when its buffer is full)."""
  try:
    return os.write(fd, data)
  except BlockingIOError:
    return 0


class UbxParser:
  """Splits a byte stream into checked UBX frames (cls, id, payload); RTCM / NMEA / junk in between is skipped."""

  def __init__(self):
    self.buf = bytearray()

  def feed(self, data: bytes):
    self.buf += data
    out = []
    while True:
      i = self.buf.find(b"\xb5\x62")
      if i < 0:
        del self.buf[:max(0, len(self.buf) - 1)]
        return out
      if i:
        del self.buf[:i]
      if len(self.buf) < 6:
        return out
      n = struct.unpack_from("<H", self.buf, 4)[0]
      if n > 4096:
        del self.buf[:2]
        continue
      if len(self.buf) < 8 + n:
        return out
      frame = bytes(self.buf[:8 + n])
      if ubx(frame[2], frame[3], frame[6:6 + n]) == frame:
        out.append((frame[2], frame[3], frame[6:6 + n]))
        del self.buf[:8 + n]
      else:
        del self.buf[:2]


def parse_pvt(p: bytes) -> dict | None:
  if len(p) < 92:
    return None
  fix, flags, flags2, used = p[20], p[21], p[22], p[23]
  lon, lat, height, hmsl, hacc, vacc = struct.unpack_from("<iiiiII", p, 24)
  gspeed, headmot = struct.unpack_from("<ii", p, 60)
  pdop = struct.unpack_from("<H", p, 76)[0]
  flags3 = struct.unpack_from("<H", p, 78)[0]
  headveh = struct.unpack_from("<i", p, 84)[0]
  carr = (flags >> 6) & 3
  age = CORRECTION_AGE[min((flags3 >> 1) & 0xF, len(CORRECTION_AGE) - 1)]
  return {
    "fixType": FIX[min(fix, 5)], "fixOk": bool(flags & 1), "rtk": ("none", "float", "fixed")[min(carr, 2)],
    "diff": bool(flags & 2), "used": used, "lat": round(lat * 1e-7, 7), "lon": round(lon * 1e-7, 7), "altM": hmsl / 1000, "ellM": height / 1000,
    "hAccM": hacc / 1000, "vAccM": vacc / 1000, "speedMs": gspeed / 1000, "headingDeg": round(headmot * 1e-5, 5),
    "carHeadingDeg": round(headveh * 1e-5, 5) if flags & 0x20 else None, "pdop": pdop / 100, "correctionAgeS": age,
    "invalid": bool(flags3 & 1), "timeOk": bool(flags2 & 0x80),
  }


def parse_sat(p: bytes) -> dict | None:
  if len(p) < 8:
    return None
  n = min(p[5], (len(p) - 8) // 12)
  heard = used = corrected = 0
  for k in range(n):
    b = p[8 + 12 * k:20 + 12 * k]
    flags = struct.unpack_from("<I", b, 8)[0]
    heard += b[2] > 0
    used += bool(flags & 0x08)
    corrected += bool(flags & 0x08) and bool(flags & 0x40)
  return {"heard": heard, "usedSats": used, "corrected": corrected}


def parse_esf_status(p: bytes) -> dict | None:
  if len(p) < 16:
    return None
  return {"fusion": FUSION[min(p[12], 3)]}


def parse_esf_alg(p: bytes) -> dict | None:
  if len(p) < 16:
    return None
  flags = p[5]
  return {"mountAuto": bool(flags & 1), "mount": ALIGN[min((flags >> 1) & 7, 4)], "mountYawDeg": struct.unpack_from("<I", p, 8)[0] / 100}


class Rtk:
  def __init__(self, port_glob: str = PORT_GLOB, clock=time.monotonic):
    self.port_glob, self.clock = port_glob, clock
    self.lock = threading.Lock()
    self.parser = UbxParser()
    self.fd = None
    self.port = None
    self.pvt = self.sat = self.esf = self.alg = None
    self.pvt_t = None
    self.rtcm = bytearray()
    self.rtcm_bytes = 0
    self.rtcm_t = None
    self.dropped = 0
    self._poll_t = 0.0
    self.thread = None

  # ---- tablet side ----
  def feed_rtcm(self, data: bytes) -> dict:
    with self.lock:
      if self.fd is None:
        return {"ok": False, "error": "RTK receiver not connected"}
      self.rtcm += data
      if len(self.rtcm) > RTCM_MAX:
        self.dropped += len(self.rtcm) - RTCM_MAX
        del self.rtcm[:len(self.rtcm) - RTCM_MAX]
      self.rtcm_bytes += len(data)
      self.rtcm_t = self.clock()
    return {"ok": True}

  def status(self) -> dict | None:
    """None: no RTK receiver has been seen on this comma (the tablet hides the RTK part)."""
    with self.lock:
      if self.port is None:
        return None
      now = self.clock()
      fresh = self.pvt is not None and self.pvt_t is not None and now - self.pvt_t < FRESH_S
      out = {"connected": self.fd is not None, "fresh": fresh,
             "rtcmBytes": self.rtcm_bytes, "rtcmAgeS": round(now - self.rtcm_t, 1) if self.rtcm_t is not None else None}
      if fresh:
        out.update(self.pvt)
      for part in (self.sat, self.esf, self.alg):
        if part:
          out.update(part)
      return out

  # ---- receiver side ----
  def start(self) -> None:
    if self.thread is None:
      self.thread = threading.Thread(target=self._run, name="starview-rtk", daemon=True)
      self.thread.start()

  def _find(self) -> str | None:
    for path in sorted(glob.glob(self.port_glob)):
      if self._is_ublox(path):
        return path
    return None

  @staticmethod
  def _is_ublox(path: str) -> bool:
    try:
      dev = os.path.realpath(f"/sys/class/tty/{os.path.basename(os.path.realpath(path))}/device")
      return open(os.path.join(os.path.dirname(dev), "idVendor")).read().strip().lower() == "1546"
    except OSError:
      return "u-blox" in path    # by-id name only (tests, or sysfs laid out differently)

  def _open(self, path: str) -> None:
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
      a = termios.tcgetattr(fd)
      a[0] = a[1] = a[3] = 0
      a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
      termios.tcsetattr(fd, termios.TCSANOW, a)
    except termios.error:
      pass   # not a tty (tests use a pipe pair)
    with self.lock:
      self.fd, self.port = fd, path
    os.write(fd, SETUP)
    cloudlog.warning(f"starview: rtk receiver connected on {path}")

  def _close(self, why: str) -> None:
    with self.lock:
      fd, self.fd = self.fd, None
      self.rtcm.clear()
    if fd is not None:
      try:
        os.close(fd)
      except OSError:
        pass
      cloudlog.warning(f"starview: rtk receiver disconnected ({why})")

  def handle(self, cls: int, msg: int, payload: bytes) -> None:
    now = self.clock()
    with self.lock:
      if (cls, msg) == (0x01, 0x07):
        pvt = parse_pvt(payload)
        if pvt:
          self.pvt, self.pvt_t = pvt, now
      elif (cls, msg) == (0x01, 0x35):
        self.sat = parse_sat(payload)
      elif (cls, msg) == (0x10, 0x10):
        self.esf = parse_esf_status(payload)
      elif (cls, msg) == (0x10, 0x14):
        self.alg = parse_esf_alg(payload)

  def step(self, timeout: float = 0.1) -> None:
    """One pass: open if needed, read what's there, poll once a second, write pending corrections."""
    if self.fd is None:
      path = self._find()
      if path is None:
        time.sleep(5.0)
        return
      try:
        self._open(path)
      except OSError as e:
        cloudlog.warning(f"starview: rtk open {path}: {e}")
        time.sleep(5.0)
        return
      self._poll_t = 0.0
    fd = self.fd
    try:
      ready, _, _ = select.select([fd], [], [], timeout)
      if ready:
        data = os.read(fd, 8192)
        if not data:
          raise OSError("receiver closed")
        for frame in self.parser.feed(data):
          self.handle(*frame)
      now = self.clock()
      if now - self._poll_t >= POLL_S:
        self._poll_t = now
        _write_some(fd, POLLS)
      with self.lock:
        pending, self.rtcm = bytes(self.rtcm), bytearray()
      if pending:
        rest = pending[_write_some(fd, pending):]
        if rest:
          with self.lock:
            self.rtcm[:0] = rest   # the USB side is full: the rest goes first next time
    except OSError as e:
      self._close(str(e))

  def _run(self) -> None:
    while True:
      try:
        self.step()
      except Exception:
        cloudlog.exception("starview: rtk")
        self._close("error")
        time.sleep(1.0)
