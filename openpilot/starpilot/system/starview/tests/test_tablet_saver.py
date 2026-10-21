import subprocess

from openpilot.starpilot.system.starview import tablet_saver as ts

SURVEY = """KEEP com.google.android.inputmethod.latin/com.android.inputmethod.latin.LatinIME
KEEP com.android.launcher3/.uioverlay.TaskbarActivity
KEEP com.starpilot.starview
KEEP null
KEEP com.google.android.googlequicksearchbox/com.google.android.voicesearch.serviceapi.GoogleRecognitionService
SET global wifi_scan_always_enabled 1
SET global ble_scan_always_enabled null
USER com.starpilot.starview
USER com.server.auditor.ssh.client
USER com.spotify.music
USER com.whatsapp
SYS android
SYS com.google.android.gms
SYS com.google.android.youtube
SYS com.android.vending
SYS com.google.android.googlequicksearchbox
"""


class FakeAdb:
  def __init__(self):
    self.calls = []
    self.up = True

  def __call__(self, *args, timeout=10):
    if not self.up:
      return None
    script = args[1]
    self.calls.append(script)
    if script.startswith('echo "KEEP'):
      out = SURVEY
    elif script.startswith("for p in"):
      pk = script.split("for p in ", 1)[1].split("; do", 1)[0].split()
      modes = {"com.whatsapp": "RUN_ANY_IN_BACKGROUND: allow; time=+1d", "com.android.vending": "No operations."}
      out = "".join(f"OLD {p} {modes.get(p, 'RUN_ANY_IN_BACKGROUND: ignore')} | {'30' if p != 'com.spotify.music' else '45'}\n" for p in pk)
      out += "DONE\n"
    else:
      out = "DONE\n"
    return subprocess.CompletedProcess(args, 0, out, "")


def test_on_off(tmp_path):
  adb = FakeAdb()
  t = [0.0]
  s = ts.TabletSaver(adb, state_path=str(tmp_path / "s.json"), keep_path=str(tmp_path / "keep"), clock=lambda: t[0])
  r = s.set(True)
  assert r["ok"] and r["on"]
  quiet = adb.calls[1]
  pk = quiet.split("for p in ", 1)[1].split("; do", 1)[0].split()
  # the user's apps and the heavy preinstalled ones; never StarView, Termius, the keyboard, voice, Play services
  assert pk == ["com.spotify.music", "com.whatsapp", "com.android.vending", "com.google.android.youtube"]
  assert "settings put global wifi_scan_always_enabled 0" in quiet and "deviceidle whitelist +com.starpilot.starview" in quiet
  assert s.state["old"]["com.whatsapp"] == {"op": "allow", "bucket": "30"}
  assert s.state["old"]["com.android.vending"]["op"] == "default"
  # asked again at the next connection: nothing done within 10 minutes
  assert s.set(True).get("already")
  assert len(adb.calls) == 2
  # later: applied again, but what we go back to stays the first value seen
  t[0] = 700.0
  s.set(True)
  assert s.state["old"]["com.whatsapp"]["op"] == "allow"
  # survives a comma restart
  s2 = ts.TabletSaver(adb, state_path=str(tmp_path / "s.json"), keep_path=str(tmp_path / "keep"))
  assert s2.status()["on"]
  r = s2.set(False)
  assert r["ok"] and not r["on"] and r["restored"] == 4
  back = adb.calls[-1]
  assert "cmd appops set com.whatsapp RUN_ANY_IN_BACKGROUND allow" in back
  assert "am set-standby-bucket com.spotify.music 45" in back
  assert "settings put global wifi_scan_always_enabled 1" in back
  assert "settings delete global ble_scan_always_enabled" in back


def test_keep_file_and_no_tablet(tmp_path):
  (tmp_path / "keep").write_text("com.whatsapp\n# not a package\n")
  adb = FakeAdb()
  s = ts.TabletSaver(adb, state_path=str(tmp_path / "s.json"), keep_path=str(tmp_path / "keep"))
  s.set(True)
  assert "com.whatsapp" not in adb.calls[1].split("; do", 1)[0]
  adb.up = False
  s2 = ts.TabletSaver(adb, state_path=str(tmp_path / "x.json"), keep_path=str(tmp_path / "keep"))
  r = s2.set(True)
  assert not r["ok"] and "adb" in r["error"]
  # off with the tablet gone: kept on, so switching off again later still restores
  r = s.set(False)
  assert not r["ok"] and s.status()["on"]
