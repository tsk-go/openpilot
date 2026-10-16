"""Toyota Active Tests (output tests) for the Sienna's body / comfort modules: honk, lock, move a window, light a lamp...

Definitions: data/active_tests.json, built by tools/build_toyota_extras.py from Toyota's GTS+ metadata (published by
kaikozlov/toyota-diagnostics); request building follows that project's executor.py (current GTS+ P5 rules):

- direct test (UDS 2F InputOutputControlByIdentifier):
    N = length of the data block read with 22 <DID>
    value packed into N bytes:  mode 0 = whole bytes at bitStart..bitEnd (big-endian);  mode 1 = shifted into one byte
    control-enable mask:        mode 0 = the record bits whose bytes lie inside the selected span (start and stop);
                                mode 1 = none on start, the selected bits on stop
    start = <start prefix: 2F DID 03> + value + start mask   ->  6F DID ...
    stop  = <stop prefix: 2F DID 00> + stop mask             (returns control to the ECU)
- routine test (UDS 31 RoutineControl): fixed start / stop requests.

Every test runs in the ECU's extended session (10 03). While a test runs, TesterPresent (3E 00) keeps the session up;
if the page stops checking in (PING_TIMEOUT_S) or a test has run for MAX_RUN_S, it is stopped. Should all of that fail
(starviewd gone), the ECU drops the extended session by itself after ~5 s without TesterPresent and takes control
back. Only one test at a time; diagnostic mode (session.py) only opens parked or with the car off.
"""
import json
import os
import threading
import time
from functools import cache

from openpilot.starpilot.system.starview.techstream import coding
from openpilot.starpilot.system.starview.techstream.link import ECU_COMMUNICATION_ERRORS, EcuRejectedError, NoResponseError, \
  expect_positive

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "active_tests.json")
EXTENDED_SESSION = b"\x10\x03"
DEFAULT_SESSION = b"\x10\x01"
TESTER_PRESENT = b"\x3e\x00"
KEEPALIVE_S = 1.5
PING_TIMEOUT_S = 3.0
MAX_RUN_S = 60.0


class TestError(Exception):
  pass


@cache
def load() -> dict:
  with open(DATA_PATH) as f:
    return json.load(f)


@cache
def _by_key() -> dict:
  return {(t["ecu"], t["id"]): t for t in load()["tests"]}


def find(ecu: str, test_id: str) -> dict | None:
  return _by_key().get((ecu, test_id))


def address(ecu_id: str) -> tuple[int, int | None]:
  tx, _, sub = ecu_id.partition("/")
  return int(tx, 16), int(sub, 16) if sub else None


def listing() -> dict:
  """What the page needs: modules and their tests (name, kind, choice labels) - not the wire details."""
  data = load()
  return {"ecus": data["ecus"],
          "tests": [{"ecu": t["ecu"], "id": t["id"], "name": t["name"], "kind": t["kind"],
                     "choices": [c["label"] for c in t.get("choices", [])]} for t in data["tests"]]}


def check(link, ecu_id: str) -> dict:
  """Which of Toyota's tests this module really has (Toyota's list covers every model using the module) - read only.

  A direct test needs its DID: the module's support bitmap (22 XX00) answers that in one read per high byte; a module
  without bitmaps gets each DID read on its own. Routines can't be checked without running them, so they stay listed.
  Returns {ecu, status: ok / offline, have: [test ids]}.
  """
  addr = address(ecu_id)
  mine = [t for t in load()["tests"] if t["ecu"] == ecu_id]
  try:
    link.request(*addr, b"\x3e\x00")
  except NoResponseError:
    return {"ecu": ecu_id, "status": "offline", "have": []}
  bitmaps: dict[int, bytes | None] = {}
  reads: dict[int, bool] = {}

  def has(did: int) -> bool:
    high = did >> 8
    if high not in bitmaps:
      try:
        bitmaps[high] = expect_positive(link, addr, b"\x22" + (high << 8).to_bytes(2, "big"), 3)
      except ECU_COMMUNICATION_ERRORS:
        bitmaps[high] = None
    bitmap = bitmaps[high]
    if bitmap is not None and len(bitmap) == coding.UDS_BITMAP_LEN:
      return coding.uds_did_supported(bitmap, did)
    if did not in reads:
      try:
        expect_positive(link, addr, b"\x22" + did.to_bytes(2, "big"), 3)
        reads[did] = True
      except ECU_COMMUNICATION_ERRORS:
        reads[did] = False
    return reads[did]

  have = [t["id"] for t in mine if t["kind"] != "direct" or has(int(t["did"], 16))]
  return {"ecu": ecu_id, "status": "ok", "have": have}


# ---- request building (pure) ----
def _bits_mask(bit_start: int, bit_end: int) -> bytes:
  mask = bytearray(bit_end // 8 + 1)
  for bit in range(bit_start, bit_end + 1):
    mask[bit // 8] |= 1 << (7 - (bit & 7))
  return bytes(mask)


def control_masks(test: dict, length: int) -> tuple[bytes, bytes]:
  s, e = test["bitStart"], test["bitEnd"]
  if s < 0 or e < s or e >= length * 8:
    raise TestError(f"test bits {s}..{e} don't fit the {length}-byte data block")
  if test["mode"] == 0:
    span_start, span_end = s >> 3, (s >> 3) + ((e - s) >> 3) + 1
    bits = [r["bit"] - 1 for r in test["records"]
            if r["bit"] > 0 and span_start <= r["offset"] < span_end and r["offset"] + r["length"] <= span_end]
    if not bits:
      raise TestError("no control-enable bit for this test")
    mask = bytearray(max(bits) // 8 + 1)
    for b in bits:
      mask[b // 8] |= 1 << (7 - (b & 7))
    return bytes(mask), bytes(mask)
  if test["mode"] == 1:
    return b"", _bits_mask(s, e)
  raise TestError(f"encoding mode {test['mode']} not supported")


def raw_value(test: dict, label: str) -> int:
  choice = next((c for c in test.get("choices", []) if c["label"] == label), None)
  if choice is None:
    raise TestError(f"unknown choice {label!r}")
  p = test["physical"]
  scaled = choice["value"]                     # choices are already integers at decimal_point_count 0
  q = abs((scaled - p["offset"]) * p["div"]) // abs(p["mul"])
  return (-q if ((scaled - p["offset"]) * p["div"] < 0) != (p["mul"] < 0) else q) & 0xFF


def pack_value(test: dict, length: int, raw: int) -> bytes:
  s, e = test["bitStart"], test["bitEnd"]
  width = e - s + 1
  if raw < 0 or raw >= (1 << width):
    raise TestError(f"value {raw} doesn't fit the {width}-bit field")
  payload = bytearray(length)
  sb, eb = s >> 3, e >> 3
  if test["mode"] == 0:
    if (s & 7) != 0 or (e & 7) != 7:
      raise TestError("mode 0 needs a whole-byte field")
    payload[sb:eb + 1] = raw.to_bytes(eb - sb + 1, "big")
  elif test["mode"] == 1:
    if sb != eb:
      raise TestError("mode 1 needs a field inside one byte")
    payload[eb] = (raw << (7 - (e & 7))) & 0xFF
  else:
    raise TestError(f"encoding mode {test['mode']} not supported")
  return bytes(payload)


def direct_requests(test: dict, length: int, label: str) -> tuple[bytes, bytes]:
  start_mask, stop_mask = control_masks(test, length)
  start = bytes.fromhex(test["start"]) + pack_value(test, length, raw_value(test, label)) + start_mask
  stop = bytes.fromhex(test["stop"]) + stop_mask
  return start, stop


# ---- running one test at a time ----
class Runner:
  def __init__(self, run_on_bus, clock=time.monotonic):
    """run_on_bus(fn) runs fn(link) under the diagnostic session's lock (DiagSession.run)."""
    self._run = run_on_bus
    self._clock = clock
    self._lock = threading.Lock()
    self.active: dict | None = None      # {test, address, stop, started, pinged, label}
    self._thread: threading.Thread | None = None
    self.last_error = ""

  def status(self) -> dict:
    a = self.active
    if not a:
      return {"active": None, "error": self.last_error}
    return {"active": {"ecu": a["test"]["ecu"], "id": a["test"]["id"], "name": a["test"]["name"], "choice": a["label"],
                       "runningS": round(self._clock() - a["started"], 1)}, "error": ""}

  def start(self, test: dict, label: str | None) -> dict:
    self.stop()
    addr = address(test["ecu"])

    def go(link):
      expect_positive(link, addr, EXTENDED_SESSION, 2)
      if test["kind"] == "direct":
        if label is None:
          raise TestError("pick a value")
        length = len(expect_positive(link, addr, b"\x22" + bytes.fromhex(test["did"]), 3))
        start, stop = direct_requests(test, length, label)
        expect_positive(link, addr, start, 3)
      else:
        start, stop = bytes.fromhex(test["start"]), bytes.fromhex(test["stop"]) if test.get("stop") else b""
        expect_positive(link, addr, start, 4)
      return stop

    try:
      stop = self._run(go)
    except Exception:
      try:
        self._run(lambda link: _quiet(link, addr, DEFAULT_SESSION))
      except Exception:
        pass
      raise
    now = self._clock()
    with self._lock:
      self.active = {"test": test, "address": addr, "stop": stop, "started": now, "pinged": now, "tester": now, "label": label}
      self.last_error = ""
    if self._thread is None or not self._thread.is_alive():
      self._thread = threading.Thread(target=self._loop, name="techstream-active-test", daemon=True)
      self._thread.start()
    return self.status()

  def ping(self) -> dict:
    with self._lock:
      if self.active:
        self.active["pinged"] = self._clock()
    return self.status()

  def stop(self, reason: str = "") -> dict:
    with self._lock:
      a, self.active = self.active, None
    if a:
      def back(link):
        if a["stop"]:
          _quiet(link, a["address"], a["stop"])
        _quiet(link, a["address"], DEFAULT_SESSION)
      try:
        self._run(back)
      except Exception as exc:          # session gone: the ECU takes control back by itself without TesterPresent
        reason = reason or f"stop not confirmed ({exc}); the module returns control on its own within seconds"
      self.last_error = reason
    return self.status()

  def tick(self) -> None:
    a = self.active
    if not a:
      return
    now = self._clock()
    if now - a["pinged"] > PING_TIMEOUT_S:
      self.stop("stopped: the page stopped checking in")
    elif now - a["started"] > MAX_RUN_S:
      self.stop(f"stopped after {MAX_RUN_S:.0f} s")
    elif now - a["tester"] >= KEEPALIVE_S:
      a["tester"] = now
      try:
        self._run(lambda link: link.request(*a["address"], TESTER_PRESENT))
      except Exception as exc:
        self.stop(f"stopped: {exc}")

  def _loop(self) -> None:
    while self.active:
      self.tick()
      time.sleep(0.25)


def _quiet(link, addr, request: bytes) -> None:
  try:
    link.request(*addr, request)
  except Exception:
    pass


__all__ = ["EcuRejectedError", "Runner", "TestError", "address", "check", "control_masks", "direct_requests", "find", "listing",
           "load", "pack_value", "raw_value"]
