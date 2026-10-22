"""The RTK receiver on the comma's USB hub (SparkFun ZED-F9R), for the tablet.

starviewd reads it: NAV-PVT arrives by itself 10x a second (the receiver keeps that setting in its own flash), NAV-SAT,
ESF-STATUS and ESF-ALG are asked for once a second (the F9R's HPS 1.00 accepted them as periodic outputs but never sent
them). RTK corrections (RTCM3) come from the tablet, which reaches the caster over its own internet (the comma has none in
the car), and are written to the receiver as they are. The tablet gets status() once a second in the params snapshot
("k"); it also builds the GGA sentence network RTK casters ask for from it.

Only a u-blox (USB vendor 1546) is ever opened: the blinker's Pico is another ttyACM on the same hub. Localization
never sees it: the comma's own GPS still drives locationd. Its fix is also handed, at most 5x a second, to the same
/dev/shm file a companion phone's fix goes through (starpilot/gps/phone.py), so navigation, the comma's map, map speed
limits and place search can use it. With Galaxy's default GPS source ("backup") that only happens while neither the
comma's GPS nor the car's has a fix of its own, and only a fresh 3D fix within 25 m passes (the same checks as theirs).

The tablet's RTK tools (action()): restart the receiver (hot / warm / cold), reset the learned mount alignment, factory
reset (our settings are written back right after), save our settings to its flash, and the car's speed feed: starviewd's
carState speed sent as UBX-ESF-MEAS (type 11) 10x a second, so the F9R's fusion has a speed sensor like a built-in
navigation's (the F9R has no wheel-tick wire here). The feed choice lives in /data/starview/rtk.json; the receiver only
gets the speed settings in RAM, so unplugged from the comma it is back to its own.
"""
import calendar
import glob
from pathlib import Path
import json
import math
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
HANDOFF_S = 0.2             # navigationd forwards a new fix at once (5 Hz loop); more often buys nothing
HANDOFF_FIXES = ("3D", "GNSS + dead reckoning")
HANDOFF_MAX_ACC_M = 25.0    # what starpilot/gps/source.py accepts from any receiver
RTCM_MAX = 64 * 1024        # never queue more than this for the receiver (old corrections are useless)
# NAV-PVT flags3 lastCorrectionAge -> upper bound in seconds
CORRECTION_AGE = (None, 1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120, 999)
FIX = ("none", "dead reckoning", "2D", "3D", "GNSS + dead reckoning", "time only")
FUSION = ("initializing", "on", "suspended", "disabled")
ALIGN = ("fixed angles", "learning roll/pitch", "learning heading", "coarse", "fine")
INIT = ("off", "initializing", "done", "done")
CALIB = ("not calibrated", "calibrating", "calibrated", "calibrated")
SENSOR = {5: "gyro z", 6: "wheel tick FL", 7: "wheel tick FR", 8: "wheel tick RL", 9: "wheel tick RR", 10: "wheel tick",
          11: "speed", 12: "gyro temperature", 13: "gyro y", 14: "gyro x", 16: "accel x", 17: "accel y", 18: "accel z"}
ALG_ERRORS = ((1, "tilt"), (2, "yaw"), (4, "angle"))
FAULTS = ((1, "bad measurements"), (2, "bad time tags"), (4, "missing measurements"), (8, "noisy measurements"))
SETTINGS_PATH = Path("/data/starview/rtk.json")
SPEED_HZ = 10.0
SPEED_MAX_AGE_S = 0.1       # a speed older than this is dropped, never sent late
SPEED_LATENCY_MS = 15       # CAN sample -> carState (~5 ms) + reader tick (<= 10 ms) + USB; delayMs shows carState -> USB
ACK_WAIT_S = 3.0


def ubx(cls: int, msg: int, payload: bytes = b"") -> bytes:
  body = struct.pack("<BBH", cls, msg, len(payload)) + payload
  a = b = 0
  for x in body:
    a = (a + x) & 0xFF
    b = (b + a) & 0xFF
  return b"\xb5\x62" + body + bytes((a, b))


RAM, BBR, FLASH = 0x01, 0x02, 0x04


def valset(items, layers: int = RAM) -> bytes:
  payload = struct.pack("<BBH", 0, layers, 0) + b"".join(struct.pack("<I", k) + v.to_bytes(n, "little") for k, v, n in items)
  return ubx(0x06, 0x8A, payload)


def valset_ram(items) -> bytes:
  """CFG-VALSET to RAM only (the flash already holds them; this just makes sure, without wearing it)."""
  return valset(items, RAM)


BASE = (
  (0x30210001, 100, 2),   # CFG-RATE-MEAS: 10 Hz
  (0x20110021, 4, 1),     # CFG-NAVSPG-DYNMODEL: automotive
  (0x20910009, 1, 1),     # CFG-MSGOUT-UBX_NAV_PVT_USB: every epoch
  (0x10770004, 1, 1),     # CFG-USBINPROT-RTCM3X: corrections in
  (0x10780002, 0, 1),     # CFG-USBOUTPROT-NMEA: off
)
# The fusion's own settings are never rewritten at every connect (Oct 22: "sensors initializing" and the mount learned
# all over again after a night parked - a write of these may restart what the fusion learned): read back at connect
# (VALGET) and only what differs from what we want is written, to RAM, BBR and flash.
USE_SF, AUTO_MNTALG = 0x10080001, 0x10060027          # CFG-SFCORE-USE_SF, CFG-SFIMU-AUTO_MNTALG_ENA
MNT_YAW, MNT_PITCH, MNT_ROLL = 0x4006002d, 0x3006002e, 0x3006002f   # CFG-SFIMU-IMU_MNTALG_YAW (U4) / PITCH, ROLL (I2), 0.01 deg
KEY_BYTES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8}            # key bits 28-30: the value's size
FUSION_KEYS = (USE_SF, AUTO_MNTALG, MNT_YAW, MNT_PITCH, MNT_ROLL)
KEEP_FINE_S = 120.0       # the mount alignment "fine" this long (same angles within 0.5 deg): kept for good
# Nothing is wired to UART1, UART2 or I2C: output there only fills the receiver's shared send memory (UART1's NMEA at
# 10 Hz outruns its 38400 baud), and then it drops USB messages too (MON-COMMS txErrors mem+alloc: ESF-STATUS never
# arrived, fusion never started). One VALSET per key: a key this firmware doesn't know refuses only itself.
PORTS_OFF = (
  0x10740001, 0x10740002,   # CFG-UART1OUTPROT-UBX / NMEA
  0x10760001, 0x10760002,   # CFG-UART2OUTPROT-UBX / NMEA
  0x10720001, 0x10720002,   # CFG-I2COUTPROT-UBX / NMEA
)
SETUP = valset_ram(BASE) + b"".join(valset_ram(((k, 0, 1),)) for k in PORTS_OFF)
SAVE_FRAMES = [valset(BASE, RAM | BBR | FLASH)] + [valset(((k, 0, 1),), RAM | BBR | FLASH) for k in PORTS_OFF] + \
  [valset(((USE_SF, 1, 1),), RAM | BBR | FLASH)]
SAVE = b"".join(SAVE_FRAMES)


def valget(keys) -> bytes:
  """CFG-VALGET from RAM (what the receiver uses now)."""
  return ubx(0x06, 0x8B, struct.pack("<BBH", 0, 0, 0) + b"".join(struct.pack("<I", k) for k in keys))


def parse_valget(p: bytes) -> dict:
  out, i = {}, 4
  while i + 4 <= len(p):
    k = struct.unpack_from("<I", p, i)[0]
    n = KEY_BYTES.get((k >> 28) & 7)
    if n is None or i + 4 + n > len(p):
      break
    out[k] = int.from_bytes(p[i + 4:i + 4 + n], "little")
    i += 4 + n
  return out


def mount_wanted(kept: dict | None) -> dict:
  """The fusion settings we want: sensor fusion on; the kept mount angles with learning off, or learning on."""
  if kept is None:
    return {USE_SF: 1, AUTO_MNTALG: 1}
  return {USE_SF: 1, MNT_YAW: round(kept["yaw"] * 100) % 36000,
          MNT_PITCH: max(-9000, min(9000, round(kept["pitch"] * 100))) & 0xFFFF,
          MNT_ROLL: max(-18000, min(18000, round(kept["roll"] * 100))) & 0xFFFF, AUTO_MNTALG: 0}


def mount_frames(kept: dict | None) -> list:
  """mount_wanted() without sensor fusion, one VALSET per key (to RAM, BBR and flash: a key refused refuses only itself)."""
  return [valset(((k, v, KEY_BYTES[(k >> 28) & 7]),), RAM | BBR | FLASH) for k, v in mount_wanted(kept).items() if k != USE_SF]
SPEED_ON = valset_ram((
  (0x1007000f, 0, 1),     # CFG-SFODO-USE_WT_PIN: no wheel-tick wire
  (0x10070003, 1, 1),     # CFG-SFODO-USE_SPEED: speed instead of wheel ticks
  (0x10070011, 0, 1),     # CFG-SFODO-DIS_AUTOSW: do use what comes over USB
  (0x2007000b, int(SPEED_HZ), 1),       # CFG-SFODO-FREQUENCY
  (0x3007000a, SPEED_LATENCY_MS, 2),    # CFG-SFODO-LATENCY (ms)
)) + valset_ram(((0x40070008, 0, 4),))  # CFG-SFODO-QUANT_ERROR 0: the receiver learns the speed's noise itself (2.56's
                                        # 0.05 m/s was too strict: "bad measurements"); its own VALSET in case it refuses
SPEED_OFF = valset_ram(((0x10070003, 0, 1), (0x10070011, 1, 1)))
FACTORY = ubx(0x06, 0x09, struct.pack("<IIIB", 0xFFFF, 0, 0xFFFF, 0x17))   # CFG-CFG: clear BBR/flash, load the defaults
RESTART = {"hot": 0x0000, "warm": 0x0001, "cold": 0xFFFF}                  # CFG-RST navBbrMask
REALIGN = ubx(0x10, 0x13)                                                   # ESF-RESETALG: learn the mount again
MON_VER = ubx(0x0A, 0x04)
POLLS = ubx(0x01, 0x35) + ubx(0x10, 0x10) + ubx(0x10, 0x14)   # NAV-SAT, ESF-STATUS, ESF-ALG


def restart(kind: str) -> bytes:
  """CFG-RST, GNSS only (resetMode 2): the USB link stays up."""
  return ubx(0x06, 0x04, struct.pack("<HBB", RESTART[kind], 2, 0))


def esf_speed(speed_ms: float, time_tag_ms: int) -> bytes:
  """UBX-ESF-MEAS with one speed (data type 11, signed, mm/s; negative backing up), time-tagged in ms."""
  mm = max(-(1 << 23), min((1 << 23) - 1, round(speed_ms * 1000)))
  data = (mm & 0xFFFFFF) | (11 << 24)
  return ubx(0x10, 0x02, struct.pack("<IHHI", time_tag_ms & 0xFFFFFFFF, 1 << 11, 0, data))


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


def rtcm_whole(buf) -> int:
  """How many leading bytes of buf are whole RTCM3 frames (or junk between them). The rest waits for the tablet's next
  chunk, so the receiver only ever sees whole frames and a UBX message from us can go between any two writes."""
  i, n = 0, len(buf)
  while i < n:
    if buf[i] != 0xD3:
      i += 1
      continue
    if n - i < 3:
      break
    size = 6 + (((buf[i + 1] & 3) << 8) | buf[i + 2])   # preamble + 10-bit length, the message, 3-byte CRC
    if n - i < size:
      break
    i += size
  return i


def parse_pvt(p: bytes) -> dict | None:
  if len(p) < 92:
    return None
  fix, flags, flags2, used = p[20], p[21], p[22], p[23]
  lon, lat, height, hmsl, hacc, vacc = struct.unpack_from("<iiiiII", p, 24)
  gspeed, headmot = struct.unpack_from("<ii", p, 60)
  pdop = struct.unpack_from("<H", p, 76)[0]
  flags3 = struct.unpack_from("<H", p, 78)[0]
  headveh = struct.unpack_from("<i", p, 84)[0]
  sacc, headacc = struct.unpack_from("<II", p, 68)
  year, month, day, hour, minute, second, valid = struct.unpack_from("<HBBBBBB", p, 4)
  nano = struct.unpack_from("<i", p, 16)[0]
  unix_ms = None
  if valid & 0x03 == 0x03:   # validDate and validTime
    try:
      unix_ms = calendar.timegm((year, month, day, hour, minute, second)) * 1000 + nano // 1_000_000
    except (ValueError, OverflowError):
      unix_ms = None
  carr = (flags >> 6) & 3
  age = CORRECTION_AGE[min((flags3 >> 1) & 0xF, len(CORRECTION_AGE) - 1)]
  return {
    "fixType": FIX[min(fix, 5)], "fixOk": bool(flags & 1), "rtk": ("none", "float", "fixed")[min(carr, 2)],
    "diff": bool(flags & 2), "used": used, "lat": round(lat * 1e-7, 7), "lon": round(lon * 1e-7, 7), "altM": hmsl / 1000, "ellM": height / 1000,
    "hAccM": hacc / 1000, "vAccM": vacc / 1000, "speedMs": gspeed / 1000, "headingDeg": round(headmot * 1e-5, 5),
    "carHeadingDeg": round(headveh * 1e-5, 5) if flags & 0x20 else None, "pdop": pdop / 100, "correctionAgeS": age,
    "invalid": bool(flags3 & 1), "timeOk": bool(flags2 & 0x80),
    "speedAccMs": sacc / 1000, "headingAccDeg": headacc * 1e-5, "unixMs": unix_ms,
  }


def handoff_fix(pvt: dict, now_ns: int) -> dict | None:
  """The receiver's fix in the phone handoff's format (starpilot/gps/phone.py), or None when it isn't a usable fix."""
  from openpilot.starpilot.gps.phone import phone_gps
  if (not pvt.get("fixOk") or pvt.get("invalid") or pvt.get("fixType") not in HANDOFF_FIXES or
      not 0 < pvt.get("hAccM", 0) <= HANDOFF_MAX_ACC_M):
    return None
  heading_acc = pvt.get("headingAccDeg", 180.)
  known = 0 < heading_acc < 180
  unix_ms = pvt.get("unixMs")
  payload = {
    "latitude": pvt["lat"], "longitude": pvt["lon"], "altitude": min(max(pvt["altM"], -999.), 9999.),
    "speed": min(max(pvt["speedMs"], 0.), 99.9), "bearing": pvt["headingDeg"] % 360,
    "horizontalAccuracy": pvt["hAccM"], "verticalAccuracy": pvt["vAccM"],
    "speedAccuracy": min(max(pvt["speedAccMs"], 0.), 99.9), "bearingAccuracy": heading_acc if known else 179.,
    "timestamp": unix_ms if type(unix_ms) is int and 0 <= unix_ms < 2 ** 53 else 0, "ageMs": 0,
  }
  try:
    gps = phone_gps(payload, now_ns)
  except ValueError:
    return None
  if not known:
    gps["bearingAccuracyDeg"] = math.nan   # no heading yet (standing still, fusion not aligned): navigation ignores it
  return gps


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
  """Fusion mode, each step of its start (IMU, INS, mount alignment, speed/wheel ticks) and every sensor it sees."""
  if len(p) < 16:
    return None
  i1, i2 = p[5], p[6]
  sensors = []
  for k in range(min(p[15], (len(p) - 16) // 4)):
    s1, s2, freq, faults = p[16 + 4 * k:20 + 4 * k]
    sensors.append({"type": SENSOR.get(s1 & 0x3F, f"type {s1 & 0x3F}"), "used": bool(s1 & 0x40), "ready": bool(s1 & 0x80),
                    "calib": CALIB[s2 & 3], "hz": freq, "faults": [name for bit, name in FAULTS if faults & bit]})
  return {"fusion": FUSION[min(p[12], 3)], "imuInit": INIT[i2 & 3], "insInit": INIT[(i1 >> 5) & 3],
          "mountInit": INIT[min((i1 >> 2) & 7, 3)], "speedInit": INIT[i1 & 3], "sensors": sensors}


def parse_mon_ver(p: bytes) -> dict | None:
  """Firmware ("HPS 1.30") and module ("ZED-F9R") from UBX-MON-VER."""
  if len(p) < 40:
    return None
  out = {}
  for k in range(40, len(p) - 29, 30):
    ext = p[k:k + 30].split(b"\0", 1)[0].decode("ascii", "replace")
    if ext.startswith("FWVER="):
      out["firmware"] = ext[6:]
    elif ext.startswith("MOD="):
      out["module"] = ext[4:]
  if "firmware" not in out:
    out["firmware"] = p[:30].split(b"\0", 1)[0].decode("ascii", "replace")
  return out


def parse_esf_alg(p: bytes) -> dict | None:
  if len(p) < 16:
    return None
  flags, errors = p[5], p[6]
  yaw = struct.unpack_from("<I", p, 8)[0] / 100
  pitch, roll = struct.unpack_from("<hh", p, 12)
  return {"mountAuto": bool(flags & 1), "mount": ALIGN[min((flags >> 1) & 7, 4)], "mountYawDeg": yaw,
          "mountPitchDeg": pitch / 100, "mountRollDeg": roll / 100,
          "mountErrors": [name for bit, name in ALG_ERRORS if errors & bit]}


class Calibration:
  """What the tablet's calibration view shows: every change in the fusion's start-up with the time it happened, and what
  the drive so far gave the receiver to learn from (u-blox: a stop with the engine on, then about 10 left and right turns
  of 90 degrees or more at 30 km/h or more). Fed from the receiver's own messages; nothing is guessed."""
  KEYS = ("fusion", "imuInit", "insInit", "mountInit", "mount", "speedInit", "speedCalib", "fixType", "carHeading")
  EVENTS = 20
  TURN_MIN_MS = 3.0          # below this a heading is noise (and the car isn't turning on a road)
  TURN_DEG = 80.0            # a corner of ~90 degrees
  TURN_WINDOW_S = 20.0
  FAST_MS = 30 / 3.6         # u-blox: 30 km/h
  STILL_MS = 0.3

  def __init__(self, clock=time.monotonic):
    self.clock = clock   # monotonic: the comma's wall clock can be off in the car; the tablet gets ages instead
    self.last = {}
    self.events = []
    self.reset_drive()
    self.speed_checks = []   # recent ESF-STATUS reports (1 Hz): True = the speed sensor had bad measurements

  def reset_drive(self) -> None:
    self.since = self.clock()
    self.turns = {"left": 0, "right": 0, "leftFast": 0, "rightFast": 0}
    self.fast_s = self.still_s = self.longest_still_s = 0.0
    self._acc = 0.0
    self._acc_t = None
    self._acc_speeds = []
    self._prev = None        # (clock, heading deg, speed m/s)

  def note(self, key: str, value) -> None:
    if value is None:
      return
    old = self.last.get(key)
    self.last[key] = value
    if key in self.last and old is not None and old != value:
      self.events.append({"t": self.clock(), "k": key, "from": old, "to": value})
      del self.events[:-self.EVENTS]

  def tool(self, op: str) -> None:
    self.events.append({"t": self.clock(), "k": "tool", "from": None, "to": op})
    del self.events[:-self.EVENTS]
    if op in ("realign", "factory", "cold"):
      self.reset_drive()

  def esf(self, esf: dict) -> None:
    for k in ("fusion", "imuInit", "insInit", "mountInit", "speedInit"):
      self.note(k, esf.get(k))
    speed = next((x for x in esf.get("sensors", ()) if x["type"] == "speed"), None)
    if speed is not None:
      self.note("speedCalib", speed["calib"])
      self.speed_checks.append("bad measurements" in speed["faults"])
      del self.speed_checks[:-60]

  def pvt(self, pvt: dict, now: float) -> None:
    self.note("fixType", pvt.get("fixType"))
    self.note("carHeading", "valid" if pvt.get("carHeadingDeg") is not None else "not valid")
    v = pvt.get("speedMs", 0.0)
    heading = pvt.get("headingDeg")
    prev, self._prev = self._prev, (now, heading, v)
    if prev is None or not 0 < now - prev[0] < 1.0:
      self._acc, self._acc_t, self._acc_speeds = 0.0, None, []
      return
    dt = now - prev[0]
    if v >= self.FAST_MS:
      self.fast_s += dt
    if v < self.STILL_MS:
      self.still_s += dt
      self.longest_still_s = max(self.longest_still_s, self.still_s)
    else:
      self.still_s = 0.0
    if v < self.TURN_MIN_MS or prev[2] < self.TURN_MIN_MS or heading is None or prev[1] is None:
      self._acc, self._acc_t, self._acc_speeds = 0.0, None, []
      return
    d = (heading - prev[1] + 180.0) % 360.0 - 180.0
    if self._acc_t is None or now - self._acc_t > self.TURN_WINDOW_S or (self._acc and d * self._acc < 0 and abs(d) > 0.5):
      self._acc, self._acc_t, self._acc_speeds = 0.0, now, []
    self._acc += d
    self._acc_speeds.append(v)
    if abs(self._acc) >= self.TURN_DEG:
      side = "right" if self._acc > 0 else "left"   # heading grows clockwise
      self.turns[side] += 1
      if sum(self._acc_speeds) / len(self._acc_speeds) >= self.FAST_MS:
        self.turns[side + "Fast"] += 1
      self._acc, self._acc_t, self._acc_speeds = 0.0, None, []

  def alg(self, alg: dict) -> None:
    self.note("mount", alg.get("mount"))

  def status(self) -> dict:
    now = self.clock()
    out = {"events": [{"agoS": round(now - e["t"], 1), "k": e["k"], "from": e["from"], "to": e["to"]} for e in self.events],
           "drive": {"sinceAgoS": round(now - self.since), **self.turns, "fastS": round(self.fast_s),
                     "longestStillS": round(self.longest_still_s), "stillNowS": round(self.still_s)}}
    if self.speed_checks:
      out["speedBadPct"] = round(100 * sum(self.speed_checks) / len(self.speed_checks))
    return out


OPS = ("hot", "warm", "cold", "realign", "factory", "save", "speed_on", "speed_off")
# not a tool: the learned mount angles written to the receiver's flash (its ACK / NAK show like a tool's)
KEEPMOUNT = "keepmount"
STOPPED_ONLY = ("cold", "factory")   # the fix is gone for a while: not while driving


class Rtk:
  def __init__(self, port_glob: str = PORT_GLOB, clock=time.monotonic, handoff_path=None, mono_ns=time.monotonic_ns,
               settings_path=SETTINGS_PATH):
    self.port_glob, self.clock = port_glob, clock
    self.handoff_path, self.mono_ns = handoff_path, mono_ns
    self.settings_path = Path(settings_path)
    self._handoff_t = None
    self.lock = threading.Lock()
    self.parser = UbxParser()
    self.fd = None
    self.port = None
    self.pvt = self.sat = self.esf = self.alg = self.ver = None
    self.pvt_t = None
    self.pvt_seq = 0
    self.rtcm = bytearray()
    self.rtcm_bytes = 0
    self.rtcm_t = None
    self.dropped = 0
    self._poll_t = 0.0
    self.thread = None
    self._wake = None
    self.partial = b""          # the end of a write the USB side didn't take: goes out before anything else
    self.cmds = []              # the tablet's RTK tools, written between two RTCM frames
    self.act = None             # the last tool used: {"op", "state", "t", "acks": [(cls, id) still to be confirmed]}
    self.speed_on = self._settings().get("speedFeed") is True
    self.sample = None          # (signed speed m/s, carState logMonoTime ns, clock time)
    self._sample_t = None
    self._sent_win = [0.0, 0]
    self.speed_hz = 0.0
    self.delay_ms = None
    self.cal = Calibration(clock)
    kept = self._settings().get("mount")   # {"yaw", "pitch", "roll"}: the learned mount kept in the receiver's flash
    ok = isinstance(kept, dict) and all(isinstance(kept.get(k), (int, float)) for k in ("yaw", "pitch", "roll"))
    self.kept = kept if ok else None
    self._fine_t = None         # since when ESF-ALG says "fine" with the same angles
    self._fine_angles = None
    self._keeping = None        # angles being written (until the receiver ACKs every key)
    self._no_keep = False       # the receiver refused them: not again this run
    self._dirty = False         # settings to write (outside the lock)
    self.cfg = {}               # what VALGET read back at the last connect

  # ---- tablet side ----
  def _settings(self) -> dict:
    try:
      got = json.loads(self.settings_path.read_text())
      return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
      return {}

  def _save_settings(self) -> None:
    try:
      self.settings_path.parent.mkdir(parents=True, exist_ok=True)
      tmp = self.settings_path.with_name(self.settings_path.name + ".tmp")
      tmp.write_text(json.dumps({**self._settings(), "speedFeed": self.speed_on, "mount": self.kept}))
      tmp.replace(self.settings_path)
    except OSError as e:
      cloudlog.warning(f"starview: rtk settings: {e}")

  def _poke(self) -> None:
    w = self._wake
    if w is not None:
      try:
        os.write(w[1], b"x")
      except OSError:
        pass

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

  def action(self, op, moving: bool = False) -> dict:
    """One of the tablet's RTK tools. The receiver's answer (ACK / NAK) shows up in status()["action"]."""
    if op not in OPS:
      return {"ok": False, "error": "Unknown RTK tool"}
    if op in STOPPED_ONLY and moving:
      return {"ok": False, "error": "Stop the car first"}
    with self.lock:
      if self.fd is None:
        return {"ok": False, "error": "RTK receiver not connected"}
      valset = (0x06, 0x8A)
      if op in RESTART:
        frames, acks = [restart(op)], []          # CFG-RST is never acknowledged
      elif op == "realign":
        # learn again: learning back on (in flash too), then ESF-RESETALG; the kept angles are forgotten
        self.kept, self._keeping, self._fine_t, self._no_keep = None, None, None, False
        frames, acks = mount_frames(None) + [REALIGN], [valset, (0x10, 0x13)]
      elif op == "factory":
        self.kept, self._keeping, self._fine_t, self._no_keep = None, None, None, False
        frames, acks = [FACTORY, SAVE] + mount_frames(None), [(0x06, 0x09)] + [valset] * (len(SAVE_FRAMES) + 1)
        if self.speed_on:
          frames.append(SPEED_ON)
          acks.append(valset)
        frames.append(MON_VER)
      elif op == "save":
        mf = mount_frames(self.kept)
        frames, acks = [SAVE] + mf, [valset] * (len(SAVE_FRAMES) + len(mf))
      else:
        self.speed_on = op == "speed_on"
        frames, acks = [SPEED_ON if self.speed_on else SPEED_OFF], [valset]
        self.speed_hz, self.delay_ms, self.sample = 0.0, None, None
      self.cmds += frames
      self.act = {"op": op, "state": "sent", "t": self.clock(), "acks": acks}
      self.cal.tool(op)
    if op in ("speed_on", "speed_off", "realign", "factory"):
      self._save_settings()
    self._poke()
    cloudlog.warning(f"starview: rtk tool {op}")
    return {"ok": True}

  def wants_speed(self) -> bool:
    """The hub's reader asks before decoding a carState: the feed is on, the receiver is there, 0.1 s since the last."""
    if not self.speed_on or self.fd is None:
      return False
    t = self._sample_t
    return t is None or self.clock() >= t

  def speed(self, speed_ms: float, reverse: bool, log_mono_ns: int) -> None:
    """One speed every 0.1 s on a fixed grid (not 0.1 s after the last one), so the gaps the receiver sees stay even."""
    now = self.clock()
    with self.lock:
      t = self._sample_t
      self._sample_t = now + 1 / SPEED_HZ if t is None or now - t > 0.3 else t + 1 / SPEED_HZ
      self.sample = (-abs(speed_ms) if reverse else speed_ms, log_mono_ns, now)
    self._poke()

  def fast(self) -> dict | None:
    """The newest fix for the tablet's 10 Hz RTK stream (lane position, map arrow), or None when there is no fresh one."""
    with self.lock:
      pvt, t = self.pvt, self.pvt_t
      if pvt is None or t is None or self.clock() - t >= FRESH_S or pvt.get("fixType") in ("none", "time only"):
        return None
      out = {"type": "rtk", "seq": self.pvt_seq, "ageMs": round((self.clock() - t) * 1000)}
      for k in ("lat", "lon", "hAccM", "speedMs", "headingDeg", "headingAccDeg", "carHeadingDeg", "fixType", "rtk", "fixOk"):
        out[k] = pvt.get(k)
      if self.esf:
        out["fusion"] = self.esf.get("fusion")
      return out

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
      for part in (self.sat, self.esf, self.alg, self.ver):
        if part:
          out.update(part)
      feed = {"on": self.speed_on}
      if self.speed_on:
        feed["hz"] = round(self.speed_hz, 1) if self._sent_win[0] and now - self._sent_win[0] < 3.0 else 0.0
        if self.delay_ms is not None:
          feed["delayMs"] = round(self.delay_ms)
      out["speedFeed"] = feed
      if self.kept is not None:
        out["mountKept"] = self.kept                   # the learned mount, in the receiver's flash (learning off)
      elif self._keeping is not None:
        out["mountKeeping"] = True
      out["calibration"] = self.cal.status()
      act = self.act
      if act is not None:
        state = act["state"]
        if state == "sent" and act["acks"] and now - act["t"] > ACK_WAIT_S:
          state = "no answer"
        elif state == "sent" and not act["acks"]:
          state = "done"
        out["action"] = {"op": act["op"], "state": state, "ageS": round(now - act["t"], 1)}
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
      self.partial = b""
      self.cmds = [SPEED_ON] if self.speed_on else []
    os.write(fd, SETUP + MON_VER + valget(FUSION_KEYS))
    cloudlog.warning(f"starview: rtk receiver connected on {path}")

  def _close(self, why: str) -> None:
    with self.lock:
      fd, self.fd = self.fd, None
      self.rtcm.clear()
      self.partial = b""
      self.sample = None
    if fd is not None:
      try:
        os.close(fd)
      except OSError:
        pass
      cloudlog.warning(f"starview: rtk receiver disconnected ({why})")

  def handle(self, cls: int, msg: int, payload: bytes) -> None:
    now = self.clock()
    pvt = None
    with self.lock:
      if (cls, msg) == (0x01, 0x07):
        pvt = parse_pvt(payload)
        if pvt:
          self.pvt, self.pvt_t = pvt, now
          self.pvt_seq += 1
          self.cal.pvt(pvt, now)
      elif (cls, msg) == (0x01, 0x35):
        self.sat = parse_sat(payload)
      elif (cls, msg) == (0x10, 0x10):
        self.esf = parse_esf_status(payload)
        if self.esf:
          self.cal.esf(self.esf)
      elif (cls, msg) == (0x10, 0x14):
        self.alg = parse_esf_alg(payload)
        if self.alg:
          self.cal.alg(self.alg)
          self._maybe_keep(self.alg, now)
      elif (cls, msg) == (0x06, 0x8B):                 # CFG-VALGET: the fusion settings as the receiver has them
        self.cfg = parse_valget(payload)
        self._fix_fusion_cfg()
      elif (cls, msg) == (0x0A, 0x04):
        self.ver = parse_mon_ver(payload)
      elif cls == 0x05 and msg in (0x00, 0x01) and len(payload) >= 2:   # ACK-NAK / ACK-ACK
        act = self.act
        what = (payload[0], payload[1])
        if msg == 0x00 and what == (0x06, 0x8B) and not self.cfg:   # VALGET refused (a key unknown): the two sure ones
          self.cmds.append(valget((USE_SF, AUTO_MNTALG)))
        if act is not None and act["state"] == "sent" and what in act["acks"]:
          if msg == 0x00:
            act["state"] = "refused"
            if act["op"] == KEEPMOUNT:
              self._keeping, self._no_keep = None, True  # this firmware won't take them: not again this run
          else:
            act["acks"].remove(what)
            if not act["acks"]:
              act["state"] = "done"
              if act["op"] == KEEPMOUNT and self._keeping is not None:
                self.kept, self._keeping, self._dirty = self._keeping, None, True
    if self._dirty:
      self._dirty = False
      self._save_settings()
    if pvt and (self._handoff_t is None or not 0 <= now - self._handoff_t < HANDOFF_S):
      self._handoff_t = now
      self._hand_off(pvt)

  def _fix_fusion_cfg(self) -> None:
    """After a connect: write only the fusion settings that differ from what we want (lock held)."""
    diff = [(k, v) for k, v in mount_wanted(self.kept).items() if self.cfg.get(k) != v]
    if diff:
      self.cmds += [valset(((k, v, KEY_BYTES[(k >> 28) & 7]),), RAM | BBR | FLASH) for k, v in diff]
      cloudlog.warning(f"starview: rtk fusion settings differed, written: {[hex(k) for k, _ in diff]}")

  def _maybe_keep(self, alg: dict, now: float) -> None:
    """The learned mount angles, once "fine" and steady for KEEP_FINE_S, go into the receiver's flash with learning off:
    after a power cut (the hub is off with the car) the fusion starts from them instead of learning again (lock held)."""
    if self.kept is not None or self._keeping is not None or self._no_keep:
      return
    if self.act is not None and self.act.get("state") == "sent":
      return
    if not (alg.get("mountAuto") and alg.get("mount") == "fine" and not alg.get("mountErrors")):
      self._fine_t, self._fine_angles = None, None
      return
    a = (alg["mountYawDeg"], alg["mountPitchDeg"], alg["mountRollDeg"])
    f = self._fine_angles
    if f is None or max(abs((a[0] - f[0] + 180) % 360 - 180), abs(a[1] - f[1]), abs(a[2] - f[2])) > 0.5:
      self._fine_t, self._fine_angles = now, a
      return
    if now - self._fine_t < KEEP_FINE_S:
      return
    self._keeping = {"yaw": round(a[0], 2), "pitch": round(a[1], 2), "roll": round(a[2], 2)}
    frames = mount_frames(self._keeping)
    self.cmds += frames
    self.act = {"op": KEEPMOUNT, "state": "sent", "t": now, "acks": [(0x06, 0x8A)] * len(frames)}
    self.cal.tool(KEEPMOUNT)
    cloudlog.warning(f"starview: rtk mount kept in flash: {self._keeping}")

  def _hand_off(self, pvt: dict) -> None:
    gps = handoff_fix(pvt, self.mono_ns())
    if gps is None:
      return
    try:
      from openpilot.starpilot.gps.phone import handoff_path
      path = self.handoff_path or handoff_path()
      temporary = path.with_name(path.name + ".rtk.tmp")
      temporary.write_text(json.dumps(gps))
      temporary.replace(path)
    except OSError as e:
      cloudlog.warning(f"starview: rtk handoff: {e}")

  def _out(self, fd: int, data: bytes) -> bool:
    """Write, keeping what the USB side didn't take for next time. False: it's full, nothing more this pass."""
    data = self.partial + data
    n = _write_some(fd, data) if data else 0
    self.partial = data[n:]
    return not self.partial

  def _write(self, fd: int) -> None:
    now = self.clock()
    if self.partial and not self._out(fd, b""):
      return
    ubx_out = b""
    with self.lock:
      cmds, self.cmds = self.cmds, []
      sample, self.sample = self.sample, None
    ubx_out += b"".join(cmds)
    if sample is not None and 0 <= now - sample[2] <= SPEED_MAX_AGE_S:
      ubx_out += esf_speed(sample[0], sample[1] // 1_000_000)
      delay = (self.mono_ns() - sample[1]) / 1e6
      self.delay_ms = delay if self.delay_ms is None else 0.9 * self.delay_ms + 0.1 * delay
      win = self._sent_win
      if not win[0] or now - win[0] > 3.0:
        self._sent_win = win = [now, 0]
      win[1] += 1
      if now - win[0] >= 2.0:
        self.speed_hz = win[1] / (now - win[0])
        self._sent_win = [now, 0]
    if now - self._poll_t >= POLL_S:
      self._poll_t = now
      ubx_out += POLLS
    if ubx_out and not self._out(fd, ubx_out):
      return
    with self.lock:
      whole = rtcm_whole(self.rtcm)
      if len(self.rtcm) - whole > 1100:   # longer than any RTCM3 frame: not one, let the receiver sort it out
        whole = len(self.rtcm)
      pending = bytes(self.rtcm[:whole])
      del self.rtcm[:whole]
    if pending:
      self._out(fd, pending)

  def step(self, timeout: float = 0.1) -> None:
    """One pass: open if needed, read what's there, then write (tools, speed, the 1 Hz polls, whole RTCM frames)."""
    if self._wake is None:
      self._wake = os.pipe()
      for end in self._wake:
        os.set_blocking(end, False)
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
      ready, _, _ = select.select([fd, self._wake[0]], [], [], timeout)
      if self._wake[0] in ready:
        try:
          os.read(self._wake[0], 512)
        except BlockingIOError:
          pass
      if fd in ready:
        data = os.read(fd, 8192)
        if not data:
          raise OSError("receiver closed")
        for frame in self.parser.feed(data):
          self.handle(*frame)
      self._write(fd)
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
