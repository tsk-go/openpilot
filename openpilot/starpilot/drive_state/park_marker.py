"""Whether the car was stopped in Park, disengaged, the last time card saw it (fork fix, remove if upstream fixes it).

Galaxy only allows an update with the ignition on when live carState proves standstill + Park and selfdriveState proves
disengaged (evidence.PhysicalSource.status). But card and selfdrived only run onroad: once the comma is offroad (Force
Offroad with the car on) that proof can't exist, so updating needed the ignition off. card now leaves its last word in
/dev/shm (gone at reboot): the update check accepts "parked when card stopped" while the pandas confirm the car is not
being controlled (noOutput, controls not allowed). If the car is driven after that with openpilot forced offroad, the
worst an update does is reboot the comma, which isn't driving.
"""
import json
import os
import time

PATH = "/dev/shm/starpilot_last_park"
WRITE_EVERY_NS = 500_000_000


def _boot_ns() -> int:
  return time.clock_gettime_ns(getattr(time, "CLOCK_BOOTTIME", time.CLOCK_MONOTONIC))


def write(parked: bool, *, path: str | None = None, now_ns: int | None = None) -> None:
  path = path or PATH
  tmp = f"{path}.{os.getpid()}"
  with open(tmp, "w") as f:
    f.write(json.dumps({"parked": bool(parked), "boot_ns": _boot_ns() if now_ns is None else now_ns}))
  os.replace(tmp, path)


def parked_when_card_stopped(*, path: str | None = None) -> bool:
  """The last thing card reported: stopped in Park and disengaged."""
  path = path or PATH
  try:
    with open(path) as f:
      value = json.loads(f.read(256))
  except (OSError, ValueError):
    return False
  return isinstance(value, dict) and value.get("parked") is True and type(value.get("boot_ns")) is int


def parked(car_state, enabled: bool) -> bool:
  return bool(car_state.canValid and not car_state.canTimeout and car_state.standstill and
              str(car_state.gearShifter) == "park" and not enabled)


class ParkMarker:
  """card's side: write on every change, and every 0.5 s while it holds (from card's slow params thread)."""

  def __init__(self, path: str | None = None, clock=_boot_ns):
    self.path, self.clock = path, clock
    self.last: bool | None = None
    self.written_ns = 0

  def update(self, car_state, enabled) -> None:
    """[enabled]: openpilot engaged, or a callable giving it (read inside the guard: card's messages change under it)."""
    if car_state is None:
      return
    try:
      now, value = self.clock(), parked(car_state, enabled() if callable(enabled) else enabled)
      if value != self.last or now - self.written_ns >= WRITE_EVERY_NS:
        write(value, path=self.path, now_ns=now)
        self.last, self.written_ns = value, now
    except Exception:
      pass   # never a reason for card to stop
