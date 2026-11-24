"""Fork fix 5: with StarView's offline mode on, the uploader's actual main loop sleeps like with no network instead of
rescanning every drive folder (fixes/offline_uploads.py). Moved here from upstream's test_uploader_preferences.py,
whose harness runs the loop (its namespace fakes offline_mode_on from each observation's 'offline')."""
from openpilot.starpilot.system.starview import offline
from openpilot.starpilot.system.starview.fixes import offline_uploads
from openpilot.system.loggerd.tests import test_uploader_preferences as upstream


def test_offline_mode_sleeps_instead_of_scanning():
  case = upstream.TestUploadPreferences("test_metered_default_off_and_live_on_off_refresh")
  wifi = upstream.Network.wifi
  state = case.run_loop([{'network': wifi, 'metered': False}, {'network': wifi, 'offline': True},
                         {'network': wifi, 'offline': True}, {'network': wifi, 'metered': False}])
  assert state.calls == [(1, False), (1, False)]          # nothing scanned while offline


def test_the_flag_is_offline_modes(tmp_path, monkeypatch):
  assert offline_uploads.FLAG == offline.FLAG
  monkeypatch.setattr(offline_uploads, "FLAG", str(tmp_path / "offline"))
  assert not offline_uploads.offline_mode_on()
  (tmp_path / "offline").write_text("")
  assert offline_uploads.offline_mode_on()
