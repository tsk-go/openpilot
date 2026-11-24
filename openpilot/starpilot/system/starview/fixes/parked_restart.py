"""Fork fix 4 (CLAUDE.md "Fork fixes"): the comma four restarts all night once it shut down while parked.

After a parked shutdown the panda's deep sleep wakes on the car's CAN, resets and bootkicks, and every such start stayed
on for MIN_ON_TIME_S (an hour) on a battery already below the cutoff - 14 restarts in one night (Oct 27). A shutdown
with the car off leaves MARKER; a start with it present and no drive since shuts down again after RESTART_SHUTDOWN_S.
A drive clears it.

Hooks: system/hardware/power_monitoring.py makes `self.parked = ParkedRestart()` and ORs `shutdown_now(...)` into
should_shutdown's answer; hardwared.py calls `parked.clear()` when the car starts and `parked.mark()` before a shutdown
with the car off.
"""
import os

MARKER = "/data/starview/parked_off"
RESTART_SHUTDOWN_S = 120


class ParkedRestart:
  def __init__(self):
    self.restart = os.path.exists(MARKER)   # this start is a wake after a parked shutdown

  def mark(self) -> None:
    """Shutting down with the car off: a wake before the next drive shuts down again quickly."""
    try:
      with open(MARKER, "w") as f:
        f.write("parked shutdown\n")
    except OSError:
      pass

  def clear(self) -> None:
    """The car started: back to the normal parked rules."""
    self.restart = False
    try:
      os.unlink(MARKER)
    except OSError:
      pass

  def shutdown_now(self, params, ignition: bool, in_car: bool, offroad_time: float, started_seen: bool) -> bool:
    """Woken while parked after a parked shutdown and no drive since: it was already time to be off. True means shut
    down even though upstream's rules (its hour minimum, its 5-minute delay) would wait - never with the ignition on, in
    "Disable power down", or out of a car, and always with "Force power down"."""
    if not self.restart or started_seen or offroad_time <= RESTART_SHUTDOWN_S:
      return False
    return (not ignition and not params.get_bool("DisablePowerDown") and in_car) or params.get_bool("ForcePowerDown")
