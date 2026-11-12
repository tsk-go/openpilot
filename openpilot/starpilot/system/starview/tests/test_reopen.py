from types import SimpleNamespace

from openpilot.starpilot.system.starview import starviewd


class SyncThread:
  def __init__(self, target=None, **kw):
    self.target = target

  def start(self):
    self.target()


def make(monkeypatch, pid="", front=None):
  calls = []
  monkeypatch.setattr(starviewd, "_tablet_front", lambda: front)
  monkeypatch.setattr(starviewd, "_tablet_home", lambda: "com.android.launcher3")
  monkeypatch.setattr(starviewd.threading, "Thread", SyncThread)
  monkeypatch.setattr(starviewd.shutil, "which", lambda name: "/usr/bin/adb")
  monkeypatch.setattr(starviewd.os.path, "isdir", lambda p: True)
  monkeypatch.setattr(starviewd, "_adb", lambda *a, **k: calls.append(a) or SimpleNamespace(stdout=pid))
  monkeypatch.setattr(starviewd, "_tablet_awake", lambda: True)
  monkeypatch.setattr(starviewd, "_tablet_wake", lambda awake: calls.append(("wake", awake)) or "started")
  hub = object.__new__(starviewd.Hub)
  hub.started = True
  hub.tablet_mode = True
  hub._tablet_seen = 100.0
  return hub, calls


def test_reopens_when_starview_is_gone_with_the_car_on(monkeypatch):
  hub, calls = make(monkeypatch)
  hub._reopen_check(105.0, False)                     # 5 s: not yet
  assert calls == []
  hub._reopen_check(109.0, False)                     # 9 s: StarView's process gone -> started again
  assert ("shell", "pidof", starviewd.STARVIEW_PKG) in calls and ("wake", True) in calls
  calls.clear()
  hub._reopen_check(115.0, False)                     # at most every 20 s
  assert calls == []
  hub._reopen_check(130.0, False)
  assert ("wake", True) in calls


def test_leaves_starview_alone_when_its_process_still_runs(monkeypatch):
  hub, calls = make(monkeypatch, pid="12345\n")       # the driver switched to another app
  hub._reopen_check(109.0, False)
  assert ("wake", True) not in calls
  calls.clear()
  hub._reopen_check(140.0, False)                     # no more tries for this drop
  assert calls == []


def test_nothing_parked_connected_or_long_gone(monkeypatch):
  hub, calls = make(monkeypatch)
  hub.started = False
  hub._reopen_check(109.0, False)
  hub.started = True
  hub._reopen_check(109.0, True)                      # connected
  hub._reopen_check(500.0, False)                     # gone more than 5 min (tablet off / unplugged)
  assert calls == []


def test_never_pops_up_over_another_app(monkeypatch):
  hub, calls = make(monkeypatch, front="com.waze")     # StarView gone, but the driver is in another app
  hub._reopen_check(109.0, False)
  assert ("wake", True) not in calls
  hub._reopen_check(130.0, False)                     # still in front 20 s later: still left alone
  assert ("wake", True) not in calls
  monkeypatch.setattr(starviewd, "_tablet_front", lambda: "com.android.launcher3")
  hub._reopen_check(150.0, False)                     # back on the home screen: StarView comes back
  assert ("wake", True) in calls


def test_may_cover():
  assert starviewd._may_cover(None)
  assert starviewd._may_cover(starviewd.STARVIEW_PKG)
  assert starviewd._may_cover("com.android.systemui")
  assert starviewd._may_cover("com.google.android.apps.nexuslauncher")
