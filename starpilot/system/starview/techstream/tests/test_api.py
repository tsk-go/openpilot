import functools
import sys
import types

import pytest

from openpilot.starpilot.system.starview.techstream import api
from openpilot.starpilot.system.starview.techstream.link import DiagLink
from openpilot.starpilot.system.starview.techstream.session import DiagSession, SessionError

from .fakes import PROBE, FakeEcu, FakePanda, FakeUdsEcu


class FakeSession:
  def __init__(self, enter_error: SessionError | None = None):
    self.enter_error = enter_error
    self.exited = False
    self.calls: list[str] = []

  def snapshot(self):
    return {"state": "idle", "idleTimeoutS": 900}

  def enter(self):
    if self.enter_error:
      raise self.enter_error

  def exit(self):
    self.exited = True
    self.calls.append("exit")

  def keepalive(self):
    self.calls.append("keepalive")

  def expire_if_idle(self):
    self.calls.append("expire_if_idle")


def make_api(session):
  return api.TechStreamApi(session, backup_dir="/nonexistent")


class TestSessionEndpoints:
  def test_get_returns_snapshot(self):
    assert make_api(FakeSession()).session_get() == (200, {"state": "idle", "idleTimeoutS": 900})

  def test_enter_success_returns_new_snapshot(self):
    assert make_api(FakeSession()).session_enter() == (200, {"state": "idle", "idleTimeoutS": 900})

  def test_enter_failure_maps_status_and_message(self):
    api_ = make_api(FakeSession(SessionError(409, "The car is driving")))
    assert api_.session_enter() == (409, {"error": "The car is driving"})

  def test_exit_is_204(self):
    session = FakeSession()
    assert make_api(session).session_exit() == (204, None)
    assert session.exited


class FakeStop:
  """threading.Event stand-in for the watchdog: wait() says "not stopped" `ticks` times, then "stopped"."""

  def __init__(self, ticks: int):
    self.ticks = ticks
    self.timeouts: list[float] = []

  def wait(self, timeout=None):
    self.timeouts.append(timeout)
    if self.ticks == 0:
      return True
    self.ticks -= 1
    return False


class TestWatchdog:
  def test_keeps_flag_fresh_expires_idle_and_exits_on_stop(self):
    session = FakeSession()
    stop = FakeStop(ticks=2)
    make_api(session).watchdog(stop)
    assert session.calls == ["keepalive", "expire_if_idle", "keepalive", "expire_if_idle", "exit"]
    assert stop.timeouts == [api.WATCHDOG_PERIOD_S] * 3

  def test_period_renews_well_inside_the_flag_window(self):
    from openpilot.starpilot.system.starview.techstream.session import FLAG_FRESH_S
    assert api.WATCHDOG_PERIOD_S * 3 <= FLAG_FRESH_S

  def test_an_error_does_not_stop_the_watchdog(self):
    class FlakySession(FakeSession):
      def keepalive(self):
        super().keepalive()
        if self.calls.count("keepalive") == 1:
          raise OSError("/dev/shm full")

    session = FlakySession()
    make_api(session).watchdog(FakeStop(ticks=2))
    assert session.calls == ["keepalive", "keepalive", "expire_if_idle", "exit"]

  def test_real_session_flag_renewed_and_dropped(self, tmp_path):
    flag = tmp_path / "starview_diag"
    session = DiagSession(open_link=lambda: types.SimpleNamespace(close=lambda: None), pandad_running=lambda: False,
                          is_offroad=lambda: True, is_parked=lambda: False, sleep=lambda s: None, flag_path=str(flag))
    session.enter()
    flag.unlink()
    seen = []

    class Stop(FakeStop):
      def wait(self, timeout=None):
        seen.append(flag.exists())
        return super().wait(timeout)

    make_api(session).watchdog(Stop(ticks=1))
    assert seen == [False, True]           # recreated by the first keepalive
    assert not flag.exists() and session.snapshot()["state"] == "idle"


class TestCreate:
  def test_wires_offroad_and_parked_and_clears_stale_flag(self, tmp_path, monkeypatch):
    flag = tmp_path / "starview_diag"
    flag.write_text("1\n")
    monkeypatch.setattr(api, "DiagSession", functools.partial(DiagSession, flag_path=str(flag)))
    monkeypatch.setattr(api, "BACKUP_DIR", str(tmp_path / "backups"))
    is_offroad, is_parked = (lambda: False), (lambda: False)
    created = api.create(is_offroad, is_parked)
    assert isinstance(created, api.TechStreamApi)
    assert not flag.exists()                 # reset_on_startup
    assert created.session._is_offroad is is_offroad and created.session._is_parked is is_parked
    assert created.session._pandad_running is api.pandad_running and created.session._open_link is api.open_panda_link
    status, body = created.session_enter()
    assert status == 409 and "driving" in body["error"]
    assert not flag.exists()


class TestCatalogEndpoint:
  def test_catalog_works_without_session_and_hides_dtc_text(self):
    status, body = make_api(FakeSession()).catalog_get()
    assert status == 200
    assert len(body["ecus"]) == 41 and len(body["settings"]) == 130 and len(body["categories"]) == 18
    assert {"live", "liveTools", "battery"} <= body.keys()
    assert "dtcText" not in body   # trouble-code texts are filled in by the backend and come with the scan results


class TestPandadRunning:
  def test_native_or_python_pandad_counts(self):
    assert api.pandad_running(run=lambda cmd: cmd[0] == "pidof")
    assert api.pandad_running(run=lambda cmd: cmd[0] == "pgrep")
    assert not api.pandad_running(run=lambda cmd: False)


# ---- customization / backups: the real flow + frame-level fake ECUs ----


class ActiveSession(FakeSession):
  def __init__(self, link):
    super().__init__()
    self.link = link

  def run(self, operation):
    return operation(self.link)


HEADLIGHTS = "car_setting_warn_headlights_on_door_open"   # 750/40 DID 2270, real car value 01 (on)


def make_active_api(tmp_path, ecus=None):
  body_ecu = FakeUdsEcu.from_probe(PROBE, "750", "40")
  panda = FakePanda(ecus if ecus is not None else {(0x750, 0x40): body_ecu})
  link = DiagLink(panda, elm327_mode=3, heartbeat_thread=False, timeout=0.02, pending_timeout=0.1)
  return body_ecu, api.TechStreamApi(ActiveSession(link), str(tmp_path))


class TestCustomizationEndpoints:
  def test_scan_one_ecu(self, tmp_path):
    _, api_ = make_active_api(tmp_path)
    status, body = api_.customizations_scan({"ecu": "750/40"})
    assert status == 200
    assert body["ecu"] == "750/40" and body["status"] == "ok" and len(body["items"]) == 44
    assert {"key": HEADLIGHTS, "value": 1, "raw": "01"} in body["items"]

  @pytest.mark.parametrize("request_body", [{}, {"ecu": "7FF"}, {"ecu": 7}])
  def test_scan_rejects_unknown_ecu(self, tmp_path, request_body):
    _, api_ = make_active_api(tmp_path)
    assert api_.customizations_scan(request_body) == (400, {"error": "invalid ecu"})

  def test_write_list_and_restore(self, tmp_path):
    body_ecu, api_ = make_active_api(tmp_path)
    status, result = api_.customization_write(HEADLIGHTS, {"value": 0, "before": "01"})
    assert status == 200 and result["verified"] and result["value"] == 0
    assert body_ecu.memory[0x2270] == b"\x00"
    status, listing = api_.backups_list()
    assert status == 200
    assert listing["backups"] == [{"id": result["backupId"], "time": listing["backups"][0]["time"], "key": HEADLIGHTS,
                                   "name": "Headlights-on reminder when door opens", "ecu": "Main Body",
                                   "before": {"value": 1, "label": "On"}, "after": {"value": 0, "label": "Off"},
                                   "restored": False}]
    status, restored = api_.backup_restore(result["backupId"])
    assert status == 200 and restored["verified"] and restored["value"] == 1
    assert body_ecu.memory[0x2270] == b"\x01"
    listing = api_.backups_list()[1]["backups"]
    assert len(listing) == 2 and next(b for b in listing if b["id"] == result["backupId"])["restored"] is True

  def test_old_format_backups_are_not_listed(self, tmp_path):
    (tmp_path / "0123456789ab.json").write_text('{"id": "0123456789ab", "time": 1, "uid": 10001, "data": "a020"}')
    _, api_ = make_active_api(tmp_path)
    assert api_.backups_list() == (200, {"backups": []})
    assert api_.backup_restore("0123456789ab") == (404, {"error": "no such backup"})

  def test_stale_before_is_409(self, tmp_path):
    _, api_ = make_active_api(tmp_path)
    status, body = api_.customization_write(HEADLIGHTS, {"value": 0, "before": "00"})
    assert status == 409 and body["error"].endswith(" - scan again")

  @pytest.mark.parametrize("key, request_body, expected", [
    ("nope", {"value": 0, "before": "01"}, (404, "unknown setting")),
    (HEADLIGHTS, {"value": 5, "before": "01"}, (400, "invalid value")),                       # not one of the options
    (HEADLIGHTS, {"value": True, "before": "01"}, (400, "invalid value")),
    (HEADLIGHTS, {"value": 0}, (400, "missing before (the raw data from the scan)")),         # no before
    ("car_setting_speaker_volume", {"value": 15, "before": "00"}, (400, "invalid value")),    # numeric, outside 1..14
  ])
  def test_bad_write_input(self, tmp_path, key, request_body, expected):
    _, api_ = make_active_api(tmp_path)
    status, body = api_.customization_write(key, request_body)
    assert (status, body["error"]) == expected

  def test_bad_backup_id_is_404(self, tmp_path):
    _, api_ = make_active_api(tmp_path)
    assert api_.backup_restore("../../etc")[0] == 404

  def test_silent_ecu_is_504(self, tmp_path):
    _, api_ = make_active_api(tmp_path, ecus={})
    status, body = api_.customization_write(HEADLIGHTS, {"value": 0, "before": "01"})
    assert status == 504 and body["error"].startswith("ECU didn't respond: ")

  def test_rejected_write_is_502(self, tmp_path):
    body_ecu = FakeUdsEcu.from_probe(PROBE, "750", "40", reject_writes=b"\x7f\x2e\x22")
    _, api_ = make_active_api(tmp_path, ecus={(0x750, 0x40): body_ecu})
    status, body = api_.customization_write(HEADLIGHTS, {"value": 0, "before": "01"})
    assert (status, body) == (502, {"error": "ECU rejected 2e22: 7f2e22"})

  def test_malformed_response_is_502(self, tmp_path):
    garbled = FakeEcu({b"\x22\x22\x70": b"\x62\x22\x70" + bytes(10)}, misnumbered_frames=True)
    _, api_ = make_active_api(tmp_path, ecus={(0x750, 0x40): garbled})
    status, body = api_.customization_write(HEADLIGHTS, {"value": 0, "before": "01"})
    assert status == 502 and body["error"].startswith("Bad ECU response: ")

  def test_failed_backup_is_500(self, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")
    _, api_ = make_active_api(blocker / "sub")
    status, body = api_.customization_write(HEADLIGHTS, {"value": 0, "before": "01"})
    assert status == 500 and "nothing written" in body["error"]

  def test_session_not_active_is_409(self, tmp_path):
    session = DiagSession(open_link=object, pandad_running=lambda: False, is_offroad=lambda: True, is_parked=lambda: False,
                          flag_path=str(tmp_path / "flag"))
    status, body = api.TechStreamApi(session, str(tmp_path)).customizations_scan({"ecu": "750/40"})
    assert (status, body) == (409, {"error": "Enter diagnostic mode first"})

  def test_unexpected_error_is_json_500(self, tmp_path):
    class BrokenSession(FakeSession):
      def run(self, operation):
        raise RuntimeError("panda unplugged")
    status, body = make_api(BrokenSession()).customizations_scan({"ecu": "750/40"})
    assert (status, body) == (500, {"error": "Internal error: panda unplugged"})


# ---- trouble codes ----

def make_dtc_api(tmp_path):
  body_ecu = FakeUdsEcu.from_probe(PROBE, "750", "40")
  body_ecu.responses[bytes.fromhex("14ffffff")] = b"\x54"
  _, api_ = make_active_api(tmp_path, ecus={(0x750, 0x40): body_ecu})
  return body_ecu, api_


class TestDtcEndpoints:
  def test_scan_one_ecu_with_text(self, tmp_path):
    _, api_ = make_dtc_api(tmp_path)
    status, body = api_.dtc_scan({"ecu": "750/40"})
    assert status == 200
    assert (body["ecu"], body["status"], body["protocol"]) == ("750/40", "ok", "uds")
    assert body["dtcs"][1] == {"code": "U0163-87", "status": 0x28,
                               "text": "Lost Communication With Navigation Control Module (Missing Message)"}

  @pytest.mark.parametrize("request_body", [{}, {"ecu": "7FF"}, {"ecu": 7}])
  def test_scan_rejects_unknown_ecu(self, tmp_path, request_body):
    _, api_ = make_dtc_api(tmp_path)
    assert api_.dtc_scan(request_body) == (400, {"error": "invalid ecu"})

  def test_clear_reports_each_ecu(self, tmp_path):
    body_ecu, api_ = make_dtc_api(tmp_path)
    status, body = api_.dtc_clear({"ecus": ["750/40", "7C4"]})
    assert status == 200
    assert body["results"] == [{"ecu": "750/40", "ok": True}, {"ecu": "7C4", "ok": False, "error": "no response"}]
    assert bytes.fromhex("14ffffff") in body_ecu.requests

  @pytest.mark.parametrize("request_body", [{}, {"ecus": []}, {"ecus": "750/40"}, {"ecus": [1]}, {"ecus": ["7FF"]}])
  def test_clear_rejects_bad_ecu_list(self, tmp_path, request_body):
    body_ecu, api_ = make_dtc_api(tmp_path)
    assert api_.dtc_clear(request_body) == (400, {"error": "invalid ecus"})
    assert bytes.fromhex("14ffffff") not in body_ecu.requests


# ---- live data ----

class TestLiveEndpoints:
  def test_read_values(self, tmp_path):
    engine = FakeUdsEcu.from_probe(PROBE, "700", None)
    _, api_ = make_active_api(tmp_path, ecus={(0x700, None): engine})
    status, body = api_.live_read({"keys": ["car_tool_mileage", "car_tool_mileage_unit"]})
    assert status == 200
    assert body == {"values": [{"key": "car_tool_mileage", "value": 13875, "text": "13875"},
                               {"key": "car_tool_mileage_unit", "value": 1, "text": "Kilometers"}]}

  @pytest.mark.parametrize("request_body", [{}, {"keys": []}, {"keys": "car_tool_mileage"}, {"keys": [1]},
                                            {"keys": ["nope"]}, {"keys": ["car_tool_mileage"] * 41}])
  def test_rejects_bad_keys(self, tmp_path, request_body):
    _, api_ = make_active_api(tmp_path)
    assert api_.live_read(request_body) == (400, {"error": "keys must be 1 to 40 live-data items from the catalog"})


class TestOpenPandaLink:
  def test_failed_setup_closes_panda(self, monkeypatch):
    class BrokenPanda:
      closed = False

      def set_safety_mode(self, mode, param=0):
        raise RuntimeError("usb gone")

      def close(self):
        BrokenPanda.closed = True

    monkeypatch.setitem(sys.modules, "panda", types.SimpleNamespace(Panda=BrokenPanda))
    try:
      import opendbc.car.structs  # noqa: F401
    except ImportError:  # off-device test env without the generated structs: a stand-in with just the safety model
      structs = types.SimpleNamespace(CarParams=types.SimpleNamespace(SafetyModel=types.SimpleNamespace(elm327=3)))
      monkeypatch.setitem(sys.modules, "opendbc.car.structs", structs)
    with pytest.raises(RuntimeError, match="usb gone"):
      api.open_panda_link()
    assert BrokenPanda.closed
