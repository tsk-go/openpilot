"""CAN-frame-level fake panda + fake Toyota ECUs, shared by the TechStream tests.

FakePanda implements the panda interface DiagLink uses (can_send/can_recv/set_safety_mode/send_heartbeat/close),
reassembles ISO-TP frames into requests for a FakeEcu, and sends the answers back segmented as ISO-TP - including the
0x750 gateway's sub-address first byte and flow-control frames - so the protocol modules are tested over the same frame
path as on the real car.
"""
import json
import os
from collections.abc import Callable

# Read-only probe recorded on a real 4th-gen Sienna in Ready (toyopilot's fixture)
PROBE = os.path.join(os.path.dirname(__file__), "fixtures", "sienna_ready_probe.jsonl")


class FakeEcu:
  """Answers by looking the request bytes up. A responses value is bytes, or a list of bytes sent one after another
  (for 7F xx 78). misnumbered_frames: consecutive frames of a multi-frame answer start numbering at 2 (the real car's
  750/AD moonroof does this for A8 03)."""

  def __init__(self, responses: dict[bytes, bytes | list[bytes]] | None = None,
               handler: Callable[[bytes], bytes | list[bytes] | None] | None = None, misnumbered_frames: bool = False):
    self.responses = dict(responses or {})
    self.handler = handler
    self.misnumbered_frames = misnumbered_frames
    self.requests: list[bytes] = []

  def respond(self, request: bytes) -> list[bytes]:
    self.requests.append(request)
    reply = self.handler(request) if self.handler else self.responses.get(request)
    if reply is None:
      return []
    return reply if isinstance(reply, list) else [reply]


class FakePanda:
  def __init__(self, ecus: dict[tuple[int, int | None], FakeEcu] | None = None, bus: int = 0):
    self.ecus = dict(ecus or {})
    self.bus = bus
    self.sent: list[tuple[int, bytes, int]] = []
    self.safety_modes: list[tuple[int, int]] = []
    self.heartbeats = 0
    self.closed = False
    self._rx: list[tuple[int, bytes, int]] = []
    self._partial: dict[tuple[int, int | None], tuple[int, bytearray]] = {}   # requests with a first frame, not complete yet
    self._pending_tx: dict[tuple[int, int | None], list[bytes]] = {}          # answer frames waiting for the tester's flow control

  # ---- panda interface ----
  def set_safety_mode(self, mode, param=0):
    self.safety_modes.append((mode, param))

  def send_heartbeat(self, engaged=True):
    self.heartbeats += 1

  def close(self):
    self.closed = True

  def can_recv(self):
    out, self._rx = self._rx, []
    return out

  def can_send(self, addr: int, dat: bytes, bus: int, **kwargs):
    dat = bytes(dat)
    assert len(dat) == 8, "ELM327 safety only lets 8-byte frames through"
    self.sent.append((addr, dat, bus))
    if bus != self.bus:
      return
    key, frame = self._route(addr, dat)
    if key is None:
      return
    kind = frame[0] >> 4
    if kind == 0:    # single frame
      self._deliver(key, frame[1:1 + (frame[0] & 0x0F)])
    elif kind == 1:  # first frame: answer with flow control, collect the data
      length = ((frame[0] & 0x0F) << 8) | frame[1]
      self._partial[key] = (length, bytearray(frame[2:]))
      self._emit(key, bytes([0x30, 0x00, 0x00]))
    elif kind == 2:  # consecutive frame
      length, buf = self._partial[key]
      buf += frame[1:]
      if len(buf) >= length:
        del self._partial[key]
        self._deliver(key, bytes(buf[:length]))
    elif kind == 3:  # the tester's flow control: send all the queued consecutive frames
      for f in self._pending_tx.pop(key, []):
        self._emit(key, f)

  # ---- internals ----
  def _route(self, addr: int, dat: bytes):
    if (addr, None) in self.ecus:
      return (addr, None), dat
    key = (addr, dat[0])
    if key in self.ecus:
      return key, dat[1:]
    return None, dat

  def _deliver(self, key, request: bytes):
    for reply in self.ecus[key].respond(request):
      self._send_isotp(key, reply)

  def _send_isotp(self, key, payload: bytes):
    max_len = 8 if key[1] is None else 7
    if len(payload) < max_len:
      self._emit(key, bytes([len(payload)]) + payload)
      return
    first = bytes([0x10 | (len(payload) >> 8), len(payload) & 0xFF]) + payload[:max_len - 2]
    rest = payload[max_len - 2:]
    chunks = [rest[i:i + max_len - 1] for i in range(0, len(rest), max_len - 1)]
    first_index = 2 if self.ecus[key].misnumbered_frames else 1
    self._pending_tx[key] = [bytes([0x20 | ((i + first_index) & 0x0F)]) + c for i, c in enumerate(chunks)]
    self._emit(key, first)

  def _emit(self, key, frame: bytes):
    tx, sub = key
    data = (bytes([sub]) if sub is not None else b"") + frame
    self._rx.append((tx + 8, data.ljust(8, b"\x00"), self.bus))


class FakeToyotaCanEcu(FakeEcu):
  """Toyota CAN customization ECU with memory (window-type): A8 03 reports masks, 21 reads compressed data, 3B writes
  back by mask."""

  def __init__(self, memory: dict[int, bytes], masks: dict[int, bytes], reject_writes: bytes | None = None):
    super().__init__(handler=self._handle)
    self.memory = dict(memory)    # local ID -> compressed data
    self.masks = dict(masks)      # local ID -> A8 03 mask
    self.reject_writes = reject_writes

  def _handle(self, request: bytes):
    if request == b"\x3e":
      return b"\x7e"
    if request == b"\xa8\x03":
      return b"\xe8\x03" + b"".join(bytes([i, len(m)]) + m for i, m in self.masks.items())
    if len(request) == 2 and request[0] == 0x21 and request[1] in self.memory:
      return b"\x61" + request[1:2] + self.memory[request[1]]
    if len(request) > 2 and request[0] == 0x3B and request[1] in self.masks:
      if self.reject_writes:
        return self.reject_writes
      self.memory[request[1]] = bytes(b for b, m in zip(request[2:], self.masks[request[1]], strict=True) if m)
      return [b"\x7f\x3b\x78", b"\x7b" + request[1:2]]
    return b"\x7f" + request[:1] + b"\x11"


class FakeUdsEcu(FakeEcu):
  """UDS ECU with memory: 22 reads by DID (an XX00 bitmap is a DID too), 2E writes into memory, 10 03 switches to the
  extended session.

  writes_need_extended_session: in the default session 2E answers 7F 2E 7F; writing works only after 10 03.
  ignore_writes: 2E answers positively but memory doesn't change (the write didn't take; the read-back check must fail).
  Every other request (3E, 19 02 8D, 14 FFFFFF...) is looked up in responses, answering 7F xx 11 when it isn't there.
  """

  def __init__(self, memory: dict[int, bytes], responses: dict[bytes, bytes | list[bytes]] | None = None,
               reject_writes: bytes | None = None, writes_need_extended_session: bool = False, ignore_writes: bool = False):
    super().__init__(responses, handler=self._handle)
    self.memory = dict(memory)
    self.reject_writes = reject_writes
    self.writes_need_extended_session = writes_need_extended_session
    self.ignore_writes = ignore_writes
    self.extended_session = False

  @classmethod
  def from_probe(cls, path: str, tx: str, sub: str | None, **kwargs) -> "FakeUdsEcu":
    """Replay this ECU from the real car's read-only probe recording (fixtures/sienna_ready_probe.jsonl)."""
    memory: dict[int, bytes] = {}
    responses: dict[bytes, bytes] = {}
    with open(path) as f:
      for line in f:
        row = json.loads(line)
        if row.get("tx") != tx or row.get("sub") != sub or "resp" not in row:
          continue
        request, response = bytes.fromhex(row["req"]), bytes.fromhex(row["resp"])
        if request[0] == 0x22 and response[0] == 0x62:
          memory[int.from_bytes(request[1:3], "big")] = response[3:]
        else:
          responses[request] = response
    return cls(memory, responses, **kwargs)

  def _handle(self, request: bytes):
    if request == b"\x10\x03":
      self.extended_session = True
      return b"\x50\x03"
    did = int.from_bytes(request[1:3], "big") if len(request) >= 3 else None
    if request[0] == 0x22 and len(request) == 3:
      return b"\x62" + request[1:3] + self.memory[did] if did in self.memory else b"\x7f\x22\x31"
    if request[0] == 0x2E and did in self.memory:
      if self.reject_writes:
        return self.reject_writes
      if self.writes_need_extended_session and not self.extended_session:
        return b"\x7f\x2e\x7f"
      if not self.ignore_writes:
        self.memory[did] = request[3:]
      return [b"\x7f\x2e\x78", b"\x6e" + request[1:3]]
    return self.responses.get(request, b"\x7f" + request[:1] + b"\x11")
