import json
import os

from openpilot.starpilot.system.starview import hub_power as hpm
from openpilot.starpilot.system.starview.hub_power import HubPower, clamp_delay
from openpilot.starpilot.system.starview.tether import RESET_CMD, STUCK_S, TetherWatch


def make(tmp_path, device_mode=lambda: False, cfg=None):
  vbus = tmp_path / "enable"
  vbus.write_text("1\n")
  cfg_path = tmp_path / "hub_power.json"
  if cfg is not None:
    cfg_path.write_text(json.dumps(cfg))
  logs = []
  hp = HubPower(vbus=str(vbus), cfg=str(cfg_path), device_mode=device_mode, log=logs.append, wall=lambda: 1000.0)
  return hp, vbus, logs


def port(vbus):
  return vbus.read_text().strip()


def drive_then_park(hp, t0=0.0):
  hp.tick(t0, True, True)          # driving
  hp.tick(t0 + 1, False, False)    # parked: the delay starts here


def test_off_five_minutes_after_the_car(tmp_path):
  hp, vbus, _ = make(tmp_path)
  drive_then_park(hp)
  hp.tick(1 + 299, False, False)
  assert port(vbus) == "1" and not hp.cut
  st = hp.status(1 + 299)
  assert st["cut_in_s"] == 1 and st["delay_min"] == 5 and st["car"] == "off"
  hp.tick(1 + 300, False, False)
  assert port(vbus) == "0" and hp.cut
  assert hp.events[-1]["what"] == "off" and "5 min" in hp.events[-1]["why"]


def test_car_on_brings_it_back_at_once(tmp_path):
  hp, vbus, _ = make(tmp_path)
  drive_then_park(hp)
  hp.tick(400, False, False)
  assert port(vbus) == "0"
  hp.tick(400.5, True, False)        # ignition, openpilot not started yet
  assert port(vbus) == "1" and not hp.cut and hp.events[-1]["why"] == "car on"


def test_never_off_while_started(tmp_path):
  hp, vbus, _ = make(tmp_path)
  hp.tick(0, False, True)            # ignition reads off but openpilot is started (force onroad): the car counts as on
  for t in range(1, 2000, 100):
    hp.tick(t, False, True)
  assert port(vbus) == "1" and not hp.cut


def test_comma_woke_with_the_car_off_uses_the_short_delay(tmp_path):
  hp, vbus, _ = make(tmp_path, cfg={"on": True, "delay_min": 30})
  hp.tick(0, False, False)           # first reading: car already off (CAN wake / low-voltage restart)
  hp.tick(59, False, False)
  assert port(vbus) == "1"
  hp.tick(60, False, False)
  assert port(vbus) == "0"


def test_after_a_drive_the_full_delay_even_if_it_is_long(tmp_path):
  hp, vbus, _ = make(tmp_path, cfg={"on": True, "delay_min": 300})
  drive_then_park(hp)
  hp.tick(1 + 5 * 3600 - 1, False, False)
  assert port(vbus) == "1"
  hp.tick(1 + 5 * 3600, False, False)
  assert port(vbus) == "0" and "5 h 0 min" in hp.events[-1]["why"]


def test_can_wake_after_quiet_turns_it_on_early_and_off_again(tmp_path):
  hp, vbus, _ = make(tmp_path)
  drive_then_park(hp)
  hp.tick(301, False, False, can_active=True)    # bus still awake when the delay runs out: off anyway
  assert port(vbus) == "0"
  hp.tick(302, False, False, can_active=True)    # still talking: not a wake
  assert port(vbus) == "0"
  hp.tick(310, False, False)                     # bus asleep
  hp.tick(339, False, False)
  hp.tick(339.5, False, False, can_active=True)  # quiet 29.5 s: too short to count
  assert port(vbus) == "0"
  hp.tick(400, False, False)
  hp.tick(431, False, False, can_active=True)    # quiet 31 s, then traffic: unlocked / door opened
  assert port(vbus) == "1" and hp.events[-1]["why"] == "the car woke up"
  hp.tick(431 + 299, False, False)
  assert port(vbus) == "1"
  hp.tick(431 + 300, False, False)               # didn't start: off again after the full delay
  assert port(vbus) == "0"


def test_no_car_data_turns_it_back_on(tmp_path):
  hp, vbus, _ = make(tmp_path)
  drive_then_park(hp)
  hp.tick(400, False, False)
  assert port(vbus) == "0"
  hp.tick(401, None, False)
  assert port(vbus) == "1" and not hp.cut


def test_switched_off_on_the_tablet(tmp_path):
  hp, vbus, _ = make(tmp_path)
  drive_then_park(hp)
  hp.tick(400, False, False)
  assert port(vbus) == "0"
  st = hp.set_config(on=False)
  assert st["on"] is False
  hp.tick(401, False, False)
  assert port(vbus) == "1"
  hp.tick(5000, False, False)
  assert port(vbus) == "1"
  assert json.loads((tmp_path / "hub_power.json").read_text()) == {"on": False, "delay_min": 5}


def test_left_alone_while_the_port_is_a_usb_device(tmp_path):
  hp, vbus, _ = make(tmp_path, device_mode=lambda: True)
  drive_then_park(hp)
  hp.tick(5000, False, False)
  assert port(vbus) == "1" and not hp.cut


def test_delay_limits_and_config(tmp_path):
  assert clamp_delay(0) == 1 and clamp_delay(301) == 300 and clamp_delay("x") == 5 and clamp_delay(12.4) == 12
  hp, vbus, _ = make(tmp_path)
  st = hp.set_config(delay_min=1)
  assert st["delay_min"] == 1 and st["min_delay"] == 1 and st["max_delay"] == 300
  drive_then_park(hp)
  hp.tick(61, False, False)
  assert port(vbus) == "0"
  # the file changed by hand: re-read
  (tmp_path / "hub_power.json").write_text(json.dumps({"on": True, "delay_min": 9999}))
  os.utime(tmp_path / "hub_power.json", ns=(1, 1))
  assert hp.config()["delay_min"] == 300


def test_write_failure_is_reported_and_not_counted_as_off(tmp_path):
  hp, vbus, logs = make(tmp_path)
  hp.vbus = str(tmp_path / "missing" / "enable")
  drive_then_park(hp)
  hp.tick(400, False, False)
  assert not hp.cut and hp.error and any("can't switch" in m for m in logs)
  assert hp.status(400)["port"] is None


def test_ensure_on_at_start(tmp_path):
  hp, vbus, _ = make(tmp_path)
  vbus.write_text("0\n")            # StarView restarted while the port was off
  hp.ensure_on("StarView started")
  assert port(vbus) == "1"


def test_module_paths():
  assert hpm.VBUS == "/sys/kernel/debug/regulator/smb2-vbus/enable"
  assert hpm.CFG == "/data/starview/hub_power.json"


# ------------------------------------------------------------------ tether.py
class FakeAdb:
  def __init__(self, functions="mtp"):
    self.functions = functions
    self.calls = []

  def __call__(self, sn, *args):
    self.calls.append(args)
    if args[-1] == "getFunctions":
      return self.functions + "\n"
    if args[:4] == ("shell", "svc", "usb", "setFunctions"):
      self.functions = args[4] if len(args) > 4 else "none"
    return ""


def test_tether_switches_rndis_on():
  adb, logs = FakeAdb("mtp"), []
  w = TetherWatch(adb, log=logs.append)
  assert w.step(0, ["T1"]) == [("T1", "on")]
  assert ("shell", "svc", "usb", "setFunctions", "rndis") in adb.calls and "switched USB tethering on" in logs[-1]


def test_tether_resets_when_rndis_but_no_link():
  adb, logs = FakeAdb("rndis"), []
  w = TetherWatch(adb, log=logs.append)
  assert w.step(0, ["T1"]) == []                 # says rndis, no link: wait
  assert w.step(STUCK_S - 1, ["T1"]) == []
  assert w.step(STUCK_S, ["T1"]) == [("T1", "reset")]
  assert ("shell", RESET_CMD) in adb.calls and "reset its USB (#1)" in logs[-1]
  # backs off: 60 s after the first reset, then 300 s
  assert w.step(STUCK_S + 59, ["T1"]) == []
  assert w.step(STUCK_S + 60, ["T1"]) == [("T1", "reset")]
  assert w.step(STUCK_S + 60 + 299, ["T1"]) == []
  assert w.step(STUCK_S + 60 + 300, ["T1"]) == [("T1", "reset")]


def test_tether_link_up_clears_the_count():
  adb = FakeAdb("rndis")
  w = TetherWatch(adb, log=lambda m: None)
  w.step(0, ["T1"])
  w.step(STUCK_S, ["T1"])
  w.link_up()
  assert w.step(100, ["T1"]) == []               # a fresh wait, not straight into a reset
  assert w.step(100 + STUCK_S, ["T1"]) == [("T1", "reset")]


def test_reset_command_survives_the_adb_drop():
  assert RESET_CMD.startswith("nohup sh -c '") and RESET_CMD.endswith("&")
  assert "svc usb setFunctions; sleep 2; svc usb setFunctions rndis" in RESET_CMD


# ------------------------------------------------------------------ as the comma user: debugfs through sudo
def test_switches_through_sudo_when_debugfs_is_root_only(tmp_path, monkeypatch):
  calls = []
  state = {"v": "1"}

  def sudo(args, data=None):
    calls.append((tuple(args), data))
    if args[0] == "cat":
      return 0, state["v"] + "\n"
    if args[0] == "tee":
      state["v"] = data.strip()
      return 0, data
    if args[0] == "test":
      return 0, ""
    return 1, ""

  def no_access(*a, **k):
    raise PermissionError(13, "Permission denied")
  monkeypatch.setattr(hpm, "_open", no_access)
  hp = HubPower(vbus="/sys/kernel/debug/regulator/smb2-vbus/enable", cfg=str(tmp_path / "c.json"), log=lambda m: None,
                sudo=sudo)
  assert hp.port() is True and hp.can_switch(0) is True
  drive_then_park(hp)
  hp.tick(301, False, False)
  assert hp.cut and state["v"] == "0"
  assert (("tee", "/sys/kernel/debug/regulator/smb2-vbus/enable"), "0\n") in calls
  assert hp.status(302)["port"] == "off"
  hp.tick(303, True, False)
  assert not hp.cut and state["v"] == "1"


def test_sudo_refused_is_an_error_not_a_cut(tmp_path, monkeypatch):
  def no_access(*a, **k):
    raise PermissionError(13, "Permission denied")
  monkeypatch.setattr(hpm, "_open", no_access)
  hp = HubPower(vbus="/x", cfg=str(tmp_path / "c.json"), log=lambda m: None, sudo=lambda args, data=None: (1, ""))
  drive_then_park(hp)
  hp.tick(301, False, False)
  assert not hp.cut and "sudo" in hp.error
  assert hp.status(302)["can_switch"] is False and hp.status(302)["port"] is None


# ------------------------------------------------------------------ battery low: the hub first
def test_battery_low_turns_the_hub_off_before_the_delay(tmp_path):
  hp, vbus, _ = make(tmp_path, cfg={"on": True, "delay_min": 300})
  hp.cutoff_tenths = lambda: 118            # stock: the comma itself at 11.8 V, the hub at 12.0 V
  hp.tick(0, True, True, volts_mv=14200)
  hp.tick(1, False, False, volts_mv=12600)
  for t in range(2, 120):
    hp.tick(t, False, False, volts_mv=12600)
  assert port(vbus) == "1"
  t = 120
  while port(vbus) == "1" and t < 400:
    hp.tick(t, False, False, volts_mv=11900)
    t += 1
  assert port(vbus) == "0" and "battery low" in hp.events[-1]["why"]
  assert 120 + 60 <= t <= 120 + 60 + 40     # ~60 s below once the smoothed reading crosses 12.0 V
  st = hp.status(t)
  assert st["hub_cutoff_v"] == 12.0 and 11.8 < st["battery_v"] < 12.0


def test_battery_low_follows_parked_power_and_never_with_the_car_on(tmp_path):
  hp, vbus, _ = make(tmp_path)
  hp.cutoff_tenths = lambda: 122             # Parked Power On at 12.2 V: the hub at 12.4 V
  for t in range(600):
    hp.tick(t, True, False, volts_mv=12000)  # car on (e.g. accessory) with a low reading: never
  assert port(vbus) == "1"
  hp.tick(600, False, False, volts_mv=12300)
  for t in range(601, 700):
    hp.tick(t, False, False, volts_mv=12300)
  assert port(vbus) == "0" and hp.status(700)["hub_cutoff_v"] == 12.4


def test_a_brief_dip_does_nothing(tmp_path):
  hp, vbus, _ = make(tmp_path, cfg={"on": True, "delay_min": 300})
  drive_then_park(hp)
  for t in range(2, 200):
    hp.tick(t, False, False, volts_mv=11000 if 50 <= t < 55 else 12600)
  assert port(vbus) == "1"


def test_kept_on_while_the_log_copy_runs(tmp_path):
  """Patch 73: the stick is on the hub - a copy still running when the delay is up keeps it on (at most 20 min more)."""
  hp, vbus, logs = make(tmp_path)
  copying = [True]
  hp.busy = lambda: copying[0]
  drive_then_park(hp)
  hp.tick(1 + 300, False, False)
  assert port(vbus) == "1" and hp.held and hp.status(301)["held_for_copy"]
  assert any("log copy" in m for m in logs)
  hp.tick(1 + 600, False, False)
  assert port(vbus) == "1"
  copying[0] = False                       # the copy finished
  hp.tick(1 + 601, False, False)
  assert port(vbus) == "0" and not hp.held and "10 min" in hp.events[-1]["why"]


def test_the_copy_keeps_it_on_at_most_20_more_minutes(tmp_path):
  hp, vbus, _ = make(tmp_path)
  hp.busy = lambda: True
  drive_then_park(hp)
  hp.tick(1 + 300 + 1199, False, False)
  assert port(vbus) == "1"
  hp.tick(1 + 300 + 1200, False, False)
  assert port(vbus) == "0"


def test_battery_low_beats_the_copy(tmp_path):
  hp, vbus, _ = make(tmp_path, cfg={"on": True, "delay_min": 1})
  hp.busy = lambda: True
  hp.cutoff_tenths = lambda: 118
  hp.tick(0, True, True, volts_mv=14200)
  t = 1
  while port(vbus) == "1" and t < 2000:
    hp.tick(t, False, False, volts_mv=11500)
    t += 1
  assert port(vbus) == "0" and "battery low" in hp.events[-1]["why"]


def test_a_broken_copy_check_never_keeps_it_on(tmp_path):
  hp, vbus, _ = make(tmp_path)
  def boom():
    raise OSError("no /dev/shm")
  hp.busy = boom
  drive_then_park(hp)
  hp.tick(1 + 300, False, False)
  assert port(vbus) == "0"
