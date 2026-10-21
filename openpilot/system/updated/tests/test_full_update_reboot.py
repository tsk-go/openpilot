"""Fork fix: after the reboot a full update ends with, the update is reported installed, not failed."""
from openpilot.system.updated import updated


class Params:
  def __init__(self, value):
    self.values = {"UpdaterFastState": value}

  def get(self, key):
    return self.values.get(key)

  def put(self, key, value, block=False):
    self.values[key] = value


def test_full_update_reboot_is_complete_after_the_reboot():
  p = Params({"version": 1, "stage": "rebooting", "detail": updated.FULL_UPDATE_REBOOT, "branch": "SecretGoodStarPilot_v2"})
  updated.recover_fast_state(p)
  assert p.values["UpdaterFastState"] == {"version": 1, "stage": "complete", "detail": "Update installed.", "branch": "SecretGoodStarPilot_v2"}


def test_fast_update_cut_off_while_rebooting_is_still_an_error():
  # the fast update says "rebooting" a moment before its own "complete": a restart in between is an interruption
  p = Params({"version": 1, "stage": "rebooting", "detail": "Update complete. Device is rebooting; please wait for reconnection."})
  updated.recover_fast_state(p)
  assert p.values["UpdaterFastState"]["stage"] == "error"
  for stage in ("fetching", "applying", "preparing"):
    p = Params({"version": 1, "stage": stage, "detail": "x"})
    updated.recover_fast_state(p)
    assert p.values["UpdaterFastState"]["stage"] == "error"


def test_finished_states_are_left_alone():
  for value in ({"version": 1, "stage": "complete", "detail": "Already up to date."}, {"version": 1, "stage": "error", "detail": "x"}, None):
    p = Params(value)
    updated.recover_fast_state(p)
    assert p.values["UpdaterFastState"] == value
