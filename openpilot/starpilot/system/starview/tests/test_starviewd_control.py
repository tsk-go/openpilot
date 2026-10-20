import threading
from types import SimpleNamespace

import pytest

from openpilot.starpilot.system.starview import starviewd


class FakeParams:
  def __init__(self, values=None):
    self.values = dict(values or {})
    self.reads = 0

  def get(self, key, encoding=None):
    self.reads += 1
    return self.values.get(key)

  def get_bool(self, key):
    return bool(self.values.get(key, False))

  def put_bool(self, key, value):
    self.values[key] = bool(value)

  def put_bool_nonblocking(self, key, value):
    self.put_bool(key, value)


class FakeOps:
  def info(self):
    return {}

  def _locked(self, key):
    return False


def make_hub(onroad=False, started=False, engaged=False):
  hub = object.__new__(starviewd.Hub)
  hub.params = FakeParams({"IsOffroad": not onroad})   # 7.0: no IsOnroad, onroad = not IsOffroad
  hub.params_mem = FakeParams()
  hub.started = started
  hub.engaged = engaged
  hub.ops = FakeOps()
  hub.aol_active = False
  hub._aol_t = float("-inf")
  hub._aol_sock = None
  hub._snap_lock = threading.Lock()
  hub._snap = None
  hub._snap_t = 0.0
  hub._info = {}
  hub._info_t = 0.0
  hub.enc_stall_s = 0.0
  hub.openpilot_down = False
  hub._ds_sock = FakeSock()
  hub._ds_t = 0.0
  hub.live = False
  hub._param_keys = None
  return hub


class FakeSock:
  def __init__(self):
    self.pending = []

  def receive(self, non_blocking=False):
    return self.pending.pop(0) if self.pending else None


@pytest.fixture
def reboots(monkeypatch):
  calls = []

  class FakeTimer:
    def __init__(self, delay, fn):
      calls.append(fn)

    def start(self):
      pass

  monkeypatch.setattr(starviewd.threading, "Timer", FakeTimer)
  return calls


@pytest.mark.parametrize("onroad,started", [(True, False), (False, True), (True, True)])
def test_reboot_refused_while_car_is_on(reboots, onroad, started):
  hub = make_hub(onroad=onroad, started=started)
  ack = hub.control({"action": "reboot"})
  assert ack["ok"] is False
  assert reboots == []
  assert "DoUserReboot" not in hub.params.values


def test_reboot_allowed_offroad(reboots):
  hub = make_hub()
  ack = hub.control({"action": "reboot"})
  assert ack["ok"] is True
  assert len(reboots) == 1


def test_drive_state_refused_while_engaged(monkeypatch):
  hub = make_hub(onroad=True, started=True, engaged=True)
  monkeypatch.setattr(hub, "_aol_steering", lambda: False)
  ack = hub.control({"action": "drive_state", "mode": "offroad"})
  assert ack["ok"] is False
  assert "ForceOffroad" not in hub.params.values


def test_drive_state_refused_while_always_on_lateral_steers(monkeypatch):
  # AOL steers with openpilot disengaged: going offroad would drop the steering mid-drive
  hub = make_hub(onroad=True, started=True)
  monkeypatch.setattr(hub, "_aol_steering", lambda: True)
  ack = hub.control({"action": "drive_state", "mode": "offroad"})
  assert ack["ok"] is False and "Always On Lateral" in ack["error"]
  assert "ForceOffroad" not in hub.params.values


def test_drive_state_allowed_when_disengaged_even_while_driving(monkeypatch):
  # as in StarPilot's own settings: no Park needed once openpilot isn't steering or driving at all
  hub = make_hub(onroad=True, started=True)
  monkeypatch.setattr(hub, "_aol_steering", lambda: False)
  asked = []
  monkeypatch.setattr(starviewd, "drive_state_request", lambda p, mode: asked.append(mode) or {"ok": True, "mode": mode})
  ack = hub.control({"action": "drive_state", "mode": "offroad"})
  assert ack["ok"] is True
  assert asked == ["offroad"]              # 7.0's drive state owner records it (starpilot/drive_state)


def test_drive_state_default_is_auto(monkeypatch):
  hub = make_hub()
  monkeypatch.setattr(hub, "_aol_steering", lambda: False)
  asked = []
  monkeypatch.setattr(starviewd, "drive_state_request", lambda p, mode: asked.append(mode) or {"ok": True})
  hub.control({"action": "drive_state", "mode": "default"})
  assert asked == ["auto"]


@pytest.mark.parametrize("onroad,started", [(True, False), (False, True)])
def test_update_install_refused_while_the_car_is_on(onroad, started):
  hub = make_hub(onroad=onroad, started=started)
  assert hub.control({"action": "update_install"})["ok"] is False
  assert "DoReboot" not in hub.params.values


@pytest.mark.parametrize("action", ["power_off", "reset_calibration", "reset_dm"])
def test_restarting_actions_refused_while_always_on_lateral_steers(monkeypatch, action):
  hub = make_hub(onroad=True, started=True)
  monkeypatch.setattr(hub, "_aol_steering", lambda: True)
  assert hub.control({"action": action})["ok"] is False
  assert "DoShutdown" not in hub.params.values and "OnroadCycleRequested" not in hub.params.values


class FakeAolSock:
  def __init__(self, aol=None, fail=False):
    self.aol, self.fail, self.reads = aol, fail, 0


def test_aol_state(monkeypatch, clock):
  hub = make_hub()
  assert hub._aol_steering() is False and hub._aol_sock is None          # offroad: nothing read
  hub = make_hub(onroad=True, started=True)
  hub.aol_active, hub._aol_t = True, clock[0]                              # fresh from the tablet's stream
  assert hub._aol_steering() is True and hub._aol_sock is None
  reads = []

  def fake_sub(name, **kw):
    assert name == "starpilotCarState"                                     # never another carState reader
    return FakeAolSock()

  def fake_recv(sock):
    reads.append(1)
    if fake_recv.fail:
      raise RuntimeError("msgq")
    return None if fake_recv.aol is None else SimpleNamespace(starpilotCarState=SimpleNamespace(alwaysOnLateralEnabled=fake_recv.aol))
  monkeypatch.setattr(starviewd.messaging, "sub_sock", fake_sub)
  monkeypatch.setattr(starviewd.messaging, "recv_one", fake_recv)
  clock[0] += hub.AOL_FRESH_S + 1                                         # stream stale: read it directly
  fake_recv.fail, fake_recv.aol = False, False
  assert hub._aol_steering() is False
  fake_recv.aol = True
  assert hub._aol_steering() is True
  fake_recv.aol = None                                                     # card not running: nothing steers
  assert hub._aol_steering() is False
  fake_recv.fail = True                                                    # can't tell: refuse
  assert hub._aol_steering() is True
  assert len(reads) == 4


def test_params_snapshot_is_shared_between_tablets(monkeypatch):
  hub = make_hub()
  now = [100.0]
  monkeypatch.setattr(starviewd.time, "monotonic", lambda: now[0])
  first = hub.params_snapshot()
  reads = hub.params.reads
  assert hub.params_snapshot() is first  # a second tablet in the same second: no new reads
  assert hub.params.reads == reads

  hub.invalidate_params_snapshot()  # after a control action the next snapshot is fresh
  assert hub.params_snapshot() is not first

  now[0] += 1.0
  third = hub.params_snapshot()
  assert hub.params.reads > reads
  assert third is not first


@pytest.fixture
def clock(monkeypatch):
  now = [1000.0]
  monkeypatch.setattr(starviewd.time, "monotonic", lambda: now[0])
  return now


def test_openpilot_stopped_forgets_the_car_state_it_left(reboots, clock):
  # openpilot stopped while the car was on (e.g. `sudo systemctl stop comma` for a CAN scan): IsOnroad stays "1"
  hub = make_hub(onroad=True, started=True, engaged=True)
  hub._ds_t = clock[0]
  hub.openpilot_tick()
  assert not hub.openpilot_down
  assert hub.control({"action": "reboot"})["ok"] is False

  clock[0] += hub.OPENPILOT_DOWN_S + 1  # no deviceState any more
  hub.openpilot_tick()
  assert hub.openpilot_down
  assert (hub.started, hub.engaged, hub._onroad()) == (False, False, False)
  assert hub.control({"action": "reboot"})["ok"] is True

  hub._ds_sock.pending.append(b"deviceState")  # openpilot is back
  hub.openpilot_tick()
  assert not hub.openpilot_down
  assert hub._onroad()


def test_power_off_works_while_openpilot_is_stopped(reboots, clock):
  hub = make_hub()
  hub.openpilot_down = True
  assert hub.control({"action": "power_off"})["ok"] is True
  assert len(reboots) == 1  # direct shutdown timer: the manager isn't there to read DoShutdown
  assert "DoShutdown" not in hub.params.values


def test_power_off_goes_through_openpilot_while_it_runs(reboots):
  hub = make_hub()
  hub.control({"action": "power_off"})
  assert hub.params.values["DoShutdown"] is True
  assert reboots == []


def test_live_video_is_asked_for_again_after_openpilot_restarts(monkeypatch, clock):
  hub = make_hub(onroad=True, started=True)
  hub._ds_t = clock[0]
  hub.live = True  # a tablet is watching; openpilot just restarted and cleared IsLiveStreaming
  asked = []
  monkeypatch.setattr(hub, "recompute_wanted", lambda: asked.append(hub.live))
  hub.openpilot_tick()
  assert asked == [False]  # recompute runs with live reset, so it writes IsLiveStreaming again

  hub.params.values["IsLiveStreaming"] = True
  asked.clear()
  hub.openpilot_tick()
  assert asked == []


def test_galaxy_pairing_goes_through_local_galaxy():
  from openpilot.starpilot.system.starview import galaxy_local
  calls = []

  def call(path, cookie="", payload=None, deadline=0):
    calls.append((path, payload))
    if path == "/api/auth/session":
      return 200, {"authenticated": True, "localAccess": True}, "galaxy_session=abc"
    if path == "/api/galaxy/pair":
      return (400, {"error": "Use at least 8 characters"}, "") if len(payload["password"]) < 8 else (200, {}, "")
    if path == "/api/galaxy/status":
      return 200, {"paired": True, "url": "https://galaxy.firestar.link/ABCDEFGHijklmnop"}, ""
    return 404, {}, ""

  r = galaxy_local.remote("pair", "short", call=call)
  assert not r["ok"] and r["error"] == "Use at least 8 characters"
  r = galaxy_local.remote("pair", "long enough", call=call)
  assert r["ok"] and r["paired"] and r["url"].endswith("ABCDEFGHijklmnop")
  assert ("/api/galaxy/pair", {"password": "long enough"}) in calls
  assert galaxy_local.remote("status", call=lambda *a, **k: (_ for _ in ()).throw(OSError("refused")))["error"] == "Local Galaxy is unavailable"


def test_galaxy_status_keeps_one_local_session(monkeypatch):
  # Galaxy keeps 64 sessions and drops the oldest: a new one per check would log the phone out of Galaxy
  from openpilot.starpilot.system.starview import galaxy_local
  monkeypatch.setattr(galaxy_local, "_cookie", "")
  minted, seen = [], []

  def call(path, cookie="", payload=None, deadline=0):
    if path == "/api/auth/session":
      seen.append(cookie)
      if not cookie:
        minted.append(1)
        cookie = f"galaxy_session=t{len(minted)}"
      return 200, {"authenticated": True, "localAccess": True}, cookie
    return 200, {"paired": False}, ""

  for _ in range(5):
    assert galaxy_local.remote("status", call=call)["ok"]
  assert len(minted) == 1 and seen[1:] == ["galaxy_session=t1"] * 4


class _Loop:
  def __init__(self):
    self.calls = []

  def call_soon_threadsafe(self, fn, *args):
    self.calls.append(args)


def gpu_hub(state):
  hub = object.__new__(starviewd.Hub)
  hub.started, hub.lock, hub.data_clients, hub.live = True, threading.Lock(), set(), False
  hub.state = [state]
  hub._replaying = lambda: False
  hub._chestnut_display = lambda: {"ChestnutState": hub.state[0]}
  hub.events = []
  hub.recompute_wanted = lambda: hub.events.append("wanted")
  hub._video_resync = lambda: hub.events.append("resync")
  hub.invalidate_params_snapshot = lambda: None
  return hub


def test_tablet_steps_back_while_the_big_model_loads():
  hub = gpu_hub("loading")
  hub.gpu_quiet_tick(10.0)
  assert hub.gpu_quiet and hub.events == ["wanted"]
  hub.gpu_quiet_tick(10.2)                       # checked twice a second
  hub.state[0] = "active"                        # green: the video comes back at once, from a keyframe
  hub.gpu_quiet_tick(11.0)
  assert not hub.gpu_quiet and hub.events == ["wanted", "wanted", "resync"]
  hub.state[0] = "loading"
  hub.gpu_quiet_tick(20.0)
  assert hub.gpu_quiet
  hub.gpu_quiet_tick(20.0 + starviewd.Hub.GPU_QUIET_MAX_S + 1)   # stuck "loading": not longer than 3 minutes
  assert not hub.gpu_quiet
  hub.gpu_quiet_tick(20.0 + starviewd.Hub.GPU_QUIET_MAX_S + 2)
  assert not hub.gpu_quiet
  hub.started = False                            # parked: nothing to hold back
  hub.state[0] = "loading"
  hub.gpu_quiet_tick(1000.0)
  assert not hub.gpu_quiet


def test_while_loading_no_video_and_data_at_5_hz():
  hub = gpu_hub("loading")
  hub.loop, hub.gpu_quiet = _Loop(), True
  c = SimpleNamespace(rates={"carState": 0, "modelV2": 20.0}, last_sent={"carState": 0.0, "modelV2": 0.0}, sent=0, push=None)
  hub.data_clients = [c]
  for i in range(100):                           # 1 s of 100 Hz carState and 20 Hz modelV2
    t = 1.0 + i / 100
    hub._fanout_data("carState", [b"x"], t)
    if i % 5 == 0:
      hub._fanout_data("modelV2", [b"m"], t)
  assert 5 <= c.sent <= 12
  hub.video_clients = {"road": {object()}}
  hub._fanout_video("narrowRoadEncodeData", [b"frame"])     # dropped before parsing
  hub.gpu_quiet = False
  hub.loop.calls.clear()
  c.sent = 0
  for i in range(100):
    hub._fanout_data("carState", [b"x"], 3.0 + i / 100)
  assert c.sent == 100
