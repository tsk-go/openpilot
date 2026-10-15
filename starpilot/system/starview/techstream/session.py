"""Diagnostic mode: pause pandad for a while so TechStream has the panda to itself for diagnostic requests.

pandad normally owns the panda, and with the ignition off it locks safety to NO_OUTPUT, so diagnostic frames can't
go through it. Entering writes the flag file DIAG_FLAG; system/manager/process_config.py's pandad_run stops pandad while
the flag is fresh (renewed every few seconds by keepalive()), we wait until the process is really gone, then open
Panda() directly. Leaving (by hand, idle timeout, or starviewd exiting) deletes the flag and manager brings pandad back;
a flag nobody renews goes stale on its own, so a crashed starviewd can never keep pandad off. /dev/shm is cleared at
every boot. During diagnostic mode openpilot gets no pandaStates and treats the car as off; with ELM327 safety the
harness relay doesn't take over, so the car's own functions are untouched.
(toyopilot used a LanLinkDiagMode param instead; StarPilot's prebuilt params can't take new keys.)

One bus operation at a time: run() holds the lock, and enter/exit use the same lock.
"""
import os
import threading
import time
from collections.abc import Callable

DIAG_FLAG = "/dev/shm/starview_diag"
FLAG_FRESH_S = 20     # process_config.pandad_run treats an older flag as gone


class SessionError(Exception):
  def __init__(self, status: int, message: str):
    super().__init__(message)
    self.status = status
    self.message = message


def flag_fresh(path: str = DIAG_FLAG, now: float | None = None) -> bool:
  try:
    return (time.time() if now is None else now) - os.path.getmtime(path) < FLAG_FRESH_S  # noqa: TID251  file mtime is wall clock
  except OSError:
    return False


class DiagSession:
  def __init__(self, open_link: Callable[[], object], pandad_running: Callable[[], bool],
               is_offroad: Callable[[], bool], is_parked: Callable[[], bool],
               clock: Callable[[], float] = time.time,  # noqa: TID251  lastActivity is unix seconds
               sleep: Callable[[float], None] = time.sleep, idle_timeout_s: float = 900,
               pandad_stop_timeout_s: float = 15, flag_path: str = DIAG_FLAG):
    self._open_link = open_link
    self._pandad_running = pandad_running
    self._is_offroad = is_offroad
    self._is_parked = is_parked
    self._clock = clock
    self._sleep = sleep
    self.idle_timeout_s = idle_timeout_s
    self.pandad_stop_timeout_s = pandad_stop_timeout_s
    self.flag_path = flag_path
    self._lock = threading.RLock()
    self._state = "idle"
    self._error = ""
    self._link = None
    self._last_activity: float | None = None

  # ---- the flag that keeps pandad stopped ----
  def _set_flag(self, on: bool) -> None:
    if on:
      with open(self.flag_path + ".tmp", "w") as f:
        f.write(f"{time.time():.0f}\n")  # noqa: TID251
      os.replace(self.flag_path + ".tmp", self.flag_path)
    else:
      try:
        os.unlink(self.flag_path)
      except FileNotFoundError:
        pass

  def keepalive(self) -> None:
    """Renew the flag while entering / active (call every few seconds)."""
    with self._lock:
      if self._state in ("entering", "active"):
        self._set_flag(True)

  def snapshot(self) -> dict:
    snap = {"state": self._state, "idleTimeoutS": self.idle_timeout_s}
    if self._error:
      snap["error"] = self._error
    if self._last_activity is not None:
      snap["lastActivity"] = self._last_activity
      snap["idleRemainingS"] = max(0, round(self.idle_timeout_s - (self._clock() - self._last_activity)))
    return snap

  def reset_on_startup(self) -> None:
    self._set_flag(False)

  def enter(self) -> None:
    with self._lock:
      if self._state == "active":
        return
      if not self._is_offroad() and not self._is_parked():
        raise self._fail(409, "The car is driving: turn it off, or put it in Park and stop, then enter diagnostic mode")
      self._state, self._error = "entering", ""
      self._set_flag(True)
      deadline = self._clock() + self.pandad_stop_timeout_s
      while self._pandad_running():
        if self._clock() > deadline:
          self._set_flag(False)
          raise self._fail(504, "pandad didn't stop in time - diagnostic mode cancelled")
        self._set_flag(True)
        self._sleep(0.5)
      try:
        self._link = self._open_link()
      except Exception as exc:
        self._set_flag(False)
        raise self._fail(500, f"Couldn't open the panda: {exc}") from exc
      self._state = "active"
      self._last_activity = self._clock()

  def exit(self) -> None:
    with self._lock:
      link, self._link = self._link, None
      try:
        if link is not None:
          link.close()
      finally:
        self._set_flag(False)
        self._state = "idle"
        self._last_activity = None

  def expire_if_idle(self) -> None:
    with self._lock:
      if self._state == "active" and self._clock() - self._last_activity > self.idle_timeout_s:
        self.exit()

  def run(self, operation: Callable[[object], object]):
    with self._lock:
      if self._state != "active":
        raise SessionError(409, "Enter diagnostic mode first")
      self._last_activity = self._clock()
      try:
        return operation(self._link)
      finally:
        self._last_activity = self._clock()

  def _fail(self, status: int, message: str) -> SessionError:
    self._state, self._error = "idle", message
    return SessionError(status, message)
