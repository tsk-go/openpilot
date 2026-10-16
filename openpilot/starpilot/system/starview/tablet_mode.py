"""StarView tablet mode: while a StarView tablet shows the drive, the comma's own screen stays off.

starviewd refreshes /dev/shm/starview_tablet once a second while a tablet is connected; a flag older than FLAG_MAX_AGE_S
means the tablet is gone and the screen comes back. A critical alert always brings it back. With the screen off, 7.0's
UI loop stops drawing by itself (Device._set_awake -> gui_app.set_should_render(False)).
"""
import os
import time

from openpilot.cereal import log

FLAG_PATH = "/dev/shm/starview_tablet"
FLAG_MAX_AGE_S = 5.0
CRITICAL = log.SelfdriveState.AlertStatus.critical


class StarViewTabletMode:
  def __init__(self, device, ui_state, flag_path: str = FLAG_PATH):
    self._device = device
    self._ui_state = ui_state
    self._flag_path = flag_path
    self._active = False
    self._flag_fresh = False
    self._check_t = float("-inf")
    # while active the normal wake logic (touch, ignition, timeouts) must not light the screen
    self._orig_update_wakefulness = device._update_wakefulness
    device._update_wakefulness = self._update_wakefulness

  @property
  def active(self) -> bool:
    return self._active

  def _update_wakefulness(self):
    if self._active:
      self._device._set_awake(False)
    else:
      self._orig_update_wakefulness()

  def _flag_is_fresh(self) -> bool:
    try:
      age = time.time() - os.path.getmtime(self._flag_path)  # noqa: TID251  file mtimes are wall clock
      return 0 <= age < FLAG_MAX_AGE_S    # a clock set back makes it "new" for a while: not fresh then
    except OSError:
      return False

  def _critical_alert(self) -> bool:
    try:
      sm = self._ui_state.sm
      return bool(sm.valid.get("selfdriveState", False) and sm.alive.get("selfdriveState", False) and
                  sm["selfdriveState"].alertStatus == CRITICAL)
    except Exception:
      return False

  def update(self, now: float) -> None:
    """Call once per UI loop iteration (drawn or not)."""
    if now - self._check_t >= 1.0:
      self._check_t = now
      self._flag_fresh = self._flag_is_fresh()
    active = bool(self._ui_state.started) and self._flag_fresh and not self._critical_alert()
    if active == self._active:
      return
    self._active = active
    if active:
      self._device._set_awake(False)
    else:
      self._device._reset_interactive_timeout()
      self._device._set_awake(True)
