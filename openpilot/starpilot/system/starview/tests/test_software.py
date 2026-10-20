"""The tablet's Software page on 7.0: status and fast update through 7.0's software owner (Galaxy's)."""
from types import SimpleNamespace
from unittest.mock import Mock

from openpilot.starpilot.galaxy import software_operations
from openpilot.starpilot.system.starview import starviewd


class FakeOwner:
  def __init__(self, process=None, refuse=None):
    self.process = process
    self.refuse = refuse
    self.status = SimpleNamespace(snapshot=lambda: {"installed": {"branch": "SecretGoodStarPilot_v2", "commit": "29dc772"},
                                                    "updater": {"state": "idle", "fast": None}})
    self.calls = []

  def snapshot(self, include_history=True):
    assert include_history is False
    return {"progress": {"stage": None}, "parked": True, "canFastUpdate": True, "reason": None, "history": "not sent"}

  def action(self, action, payload, *, authorized):
    assert authorized()
    if self.refuse:
      raise software_operations.SoftwareOperationError(self.refuse)
    self.calls.append((action, payload))
    return {}


def ops(monkeypatch, owner):
  monkeypatch.setattr(software_operations, "UpdaterProcess", lambda: "updater-link")
  monkeypatch.setattr(software_operations, "SoftwareOperations", lambda process: owner)
  return starviewd.DeviceOps(Mock(), Mock())


def test_status_for_the_tablet(monkeypatch):
  owner = FakeOwner()
  d = ops(monkeypatch, owner)
  st = d.software_status()
  assert st["ok"] and st["installed"]["commit"] == "29dc772"
  assert st["operations"]["canFastUpdate"] is True and "history" not in st["operations"]


def test_fast_update_of_the_installed_branch(monkeypatch):
  owner = FakeOwner()
  d = ops(monkeypatch, owner)
  assert d.software_fast() == {"ok": True, "branch": "SecretGoodStarPilot_v2"}
  # Galaxy's Update button: fast when possible, the full update otherwise
  assert owner.calls == [("update", {"action": "update", "branch": "SecretGoodStarPilot_v2"})]
  assert d._software() is owner                       # one owner, kept


def test_refused_update_says_why(monkeypatch):
  d = ops(monkeypatch, FakeOwner(refuse="Vehicle is not safely parked"))
  assert d.software_fast() == {"ok": False, "error": "Vehicle is not safely parked"}
