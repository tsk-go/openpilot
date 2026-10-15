"""ISO-TP link that has the panda to itself while in diagnostic mode.

Only used once pandad is stopped (see session.py): the panda switches to ELM327 safety (lets only 0x6xx/0x7xx
diagnostic frames out), bus 0 is the car CAN on the camera harness, and the 0x750 gateway uses Toyota extended
addressing (first byte of every frame = sub-address).

The panda goes SILENT after 2 s (ignition off) / 5 s (ignition on) without a heartbeat, so a background thread keeps
sending heartbeats; while one request waits on an ECU (NRC 0x78 can drag on for seconds) it sends one too.
The SPI handle has its own lock, so the heartbeat and request threads may call it at the same time.
"""
import threading
import time

from opendbc.car.uds import CanClient, InvalidSubAddressError, IsoTpMessage

HEARTBEAT_PERIOD_S = 0.5
RESPONSE_PENDING = 0x78
NEGATIVE_RESPONSE = 0x7F


class NoResponseError(Exception):
  """The ECU didn't answer in time (not there, not powered, or doesn't use that address)."""


class MalformedResponseError(Exception):
  """The ECU answered, but not valid ISO-TP (e.g. out-of-order consecutive frames: the 750/AD moonroof's A8 03 answer
  always does this on the real car)."""


class EcuRejectedError(Exception):
  """The ECU sent a negative response, or a positive one that doesn't echo the request."""

  def __init__(self, request: bytes, response: bytes):
    self.nrc = response[2] if len(response) >= 3 and response[0] == NEGATIVE_RESPONSE else None
    super().__init__(f"ECU rejected {request[:2].hex()}: {response.hex()}")


# The three ways talking to an ECU fails: note it per ECU / per item and carry on (one ECU must never fail a whole scan
# or clear).
ECU_COMMUNICATION_ERRORS = (NoResponseError, MalformedResponseError, EcuRejectedError)


def read_error_text(exc: Exception) -> str:
  """Short reason for the user, for an ECU_COMMUNICATION_ERRORS error."""
  if isinstance(exc, NoResponseError):
    return "no response"
  if isinstance(exc, MalformedResponseError):
    return "bad response"
  return f"NRC {exc.nrc:02X}" if getattr(exc, "nrc", None) is not None else "unexpected response"


def expect_positive(link, address: tuple[int, int | None], request: bytes, echo_len: int) -> bytes:
  """Send a request, require a positive response (SID+0x40 echoing the first echo_len bytes); returns what follows the echo."""
  response = link.request(*address, request)
  if response[:echo_len] != bytes([request[0] + 0x40]) + request[1:echo_len]:
    raise EcuRejectedError(request, response)
  return response[echo_len:]


def _request_label(tx: int, sub: int | None, payload: bytes) -> str:
  return f"{tx:X}/{sub if sub is None else f'{sub:02X}'} {payload.hex()}"


class DiagLink:
  def __init__(self, panda, elm327_mode, bus: int = 0, timeout: float = 0.3, pending_timeout: float = 5.0,
               heartbeat_thread: bool = True):
    self.panda = panda
    self.bus = bus
    self.timeout = timeout
    self.pending_timeout = pending_timeout
    self._last_heartbeat = 0.0
    self._closed = threading.Event()
    # param 1: don't switch bus 1 to the OBD port, we only use bus 0
    panda.set_safety_mode(elm327_mode, 1)
    self._heartbeat()
    if heartbeat_thread:
      threading.Thread(target=self._heartbeat_loop, name="techstream_heartbeat", daemon=True).start()

  def request(self, tx: int, sub: int | None, payload: bytes) -> bytes:
    """Send one diagnostic request; returns the ECU's final response (positive or 7F negative, as received)."""
    client = CanClient(self.panda.can_send, self._receiver_for(tx + 8, sub), tx, tx + 8, self.bus, sub)
    message = IsoTpMessage(client, timeout=self.timeout)
    message.send(payload)
    deadline = time.monotonic() + self.timeout
    while True:
      try:
        response, frame_received = message.recv(timeout=0)
      except (AssertionError, InvalidSubAddressError) as exc:  # opendbc checks ISO-TP frames with assert
        self._discard_until_quiet(tx + 8)
        raise MalformedResponseError(f"{_request_label(tx, sub, payload)}: {exc}") from exc
      now = time.monotonic()
      if response is None:
        if frame_received:
          # multi-frame answer coming in (A8 03 mask tables run to dozens of frames): every frame extends the deadline,
          # it only times out once the ECU stops sending
          deadline = now + self.timeout
        elif now > deadline:
          raise NoResponseError(f"{_request_label(tx, sub, payload)}: no response")
        if now - self._last_heartbeat >= HEARTBEAT_PERIOD_S:
          self._heartbeat()
        time.sleep(0.001)
        continue
      if len(response) >= 3 and response[0] == NEGATIVE_RESPONSE and response[1] == payload[0] and response[2] == RESPONSE_PENDING:
        deadline = now + self.pending_timeout
        continue
      return response

  def _receiver_for(self, rx_addr: int, sub: int | None):
    """Gateway requests only take frames for their own sub-address: late frames from another sub-ECU (e.g. leftovers of
    a previous bad answer) are dropped rather than counted as a bad response."""
    if sub is None:
      return self.panda.can_recv
    return lambda: [f for f in self.panda.can_recv() if f[0] != rx_addr or (len(f[1]) > 1 and f[1][0] == sub)]

  def _discard_until_quiet(self, rx_addr: int) -> None:
    """After a bad answer the ECU is usually still sending the rest at its STmin: drop frames until it's quiet for
    `timeout`, so they don't end up in the next request's answer."""
    now = time.monotonic()
    quiet_at, give_up_at = now + self.timeout, now + self.pending_timeout
    while now < min(quiet_at, give_up_at):
      if any(f[0] == rx_addr for f in self.panda.can_recv()):
        quiet_at = now + self.timeout
      time.sleep(0.001)
      now = time.monotonic()

  def close(self) -> None:
    self._closed.set()
    self.panda.close()

  def _heartbeat(self) -> None:
    self._last_heartbeat = time.monotonic()
    self.panda.send_heartbeat(engaged=False)

  def _heartbeat_loop(self) -> None:
    while not self._closed.wait(HEARTBEAT_PERIOD_S):
      try:
        self._heartbeat()
      except Exception:
        return  # panda closed / unplugged: the session cleans up
