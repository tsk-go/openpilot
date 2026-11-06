"""StarView fork: a changed alert volume plays its alert once on the comma (volume_preview.py, soundd, sounds_owner)."""
import json
import os
from types import SimpleNamespace

import numpy as np

from openpilot.selfdrive.ui.soundd import PREVIEW_SOUNDS, AudibleAlert, Soundd
from openpilot.starpilot.audio import volume_preview as vp
from openpilot.starpilot.audio.alert_volume import AUTO, SPECS


def test_request_and_poll(tmp_path):
  path, off = str(tmp_path / "req"), str(tmp_path / "off")
  r = vp.PreviewReader(path, wall=lambda: 100.0)
  assert r.poll() is None
  assert vp.request("EngageVolume", 40, path=path, wall=lambda: 100.0, off_path=off)
  assert r.poll() == ("EngageVolume", 40)
  assert r.poll() is None                                   # once per request
  assert vp.request("EngageVolume", 45, path=path, wall=lambda: 90.0, off_path=off)
  os.utime(path, ns=(5, 5))
  assert r.poll() is None                                   # 10 s old: never plays
  assert not [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]


def test_switch_off_stops_requests(tmp_path):
  path, off = str(tmp_path / "req"), str(tmp_path / "x" / "off")
  assert vp.enabled(off)
  assert vp.set_enabled(False, off) and not vp.enabled(off)
  assert not vp.request("EngageVolume", 40, path=path, off_path=off) and not os.path.exists(path)
  assert vp.set_enabled(True, off) and vp.enabled(off)
  assert vp.request("EngageVolume", 40, path=path, off_path=off)
  assert json.loads(open(path).read())["value"] == 40


def test_old_request_at_start_is_ignored(tmp_path):
  path = str(tmp_path / "req")
  vp.request("EngageVolume", 40, path=path, off_path=str(tmp_path / "off"))
  assert vp.PreviewReader(path).poll() is None


def test_every_volume_has_a_preview_sound():
  assert set(PREVIEW_SOUNDS) == set(SPECS)


class _Reader:
  def __init__(self, reqs):
    self.reqs = list(reqs)

  def poll(self):
    return self.reqs.pop(0) if self.reqs else None


class _VolParams:
  def __init__(self, d):
    self.d = d

  def get_param_path(self, key=None):
    return str(self.d / key) if key else str(self.d)


def make_soundd(tmp_path, reqs, saved=None):
  for k, v in (saved or {}).items():
    (tmp_path / k).write_text(str(v))
  s = Soundd.__new__(Soundd)
  s.volume_params = _VolParams(tmp_path)
  s.volume_read_at = 0.0
  s.saved_volumes = {}
  s.current_alert = AudibleAlert.none
  s.current_sound = AudibleAlert.none
  s.current_sound_frame = 0
  s.pending_stop = False
  s.current_volume = 0.3
  s.ramp_start_volume = 0.3
  s.ramp_start_time = 0.0
  s.native_audio = None
  s.loaded_sounds = {AudibleAlert.engage: np.ones(1000, dtype=np.float32),
                     AudibleAlert.warningSoft: np.full(3000, 0.5, dtype=np.float32),
                     AudibleAlert.warningImmediate: np.full(2000, 0.5, dtype=np.float32)}
  s.pack_loader = SimpleNamespace(is_builtin=lambda data: False)
  s.preview_reader = _Reader(reqs)
  s.preview_read_at = -1.0
  s.previewing = False
  return s


def play(s, blocks=10, frames=512):
  return np.concatenate([s.get_sound_data(frames) for _ in range(blocks)])


def test_one_pass_of_the_chime_at_the_saved_level(tmp_path):
  s = make_soundd(tmp_path, [("EngageVolume", 40)], saved={"EngageVolume": 40})
  s.update_preview(0.0)
  assert s.current_alert == AudibleAlert.engage and s.previewing and s.pending_stop
  out = play(s)
  played = out[out != 0]
  assert len(played) == 1000 and np.allclose(played, 0.40)     # the whole track once, at 40 %
  assert s.current_alert == AudibleAlert.none
  s.update_preview(0.3)
  assert not s.previewing


def test_a_looping_warning_plays_one_pass_only(tmp_path):
  s = make_soundd(tmp_path, [("WarningSoftVolume", 60)], saved={"WarningSoftVolume": 60})
  s.update_preview(0.0)
  out = play(s, blocks=20)
  played = out[out != 0]
  assert len(played) == 3000 and np.allclose(played, 0.5 * 0.60)
  assert s.current_alert == AudibleAlert.none


def test_auto_uses_the_ambient_level_and_no_ramp(tmp_path):
  s = make_soundd(tmp_path, [("WarningImmediateVolume", AUTO)])
  s.update_preview(0.0)
  s.update_critical_sound(10.0)                                   # no ramp toward full volume
  assert s.current_volume == 0.3
  out = play(s, blocks=2)
  assert np.isclose(out.max(), 0.5 * 0.3)


def test_onroad_none_updates_dont_cut_it_short(tmp_path):
  s = make_soundd(tmp_path, [("EngageVolume", 40)], saved={"EngageVolume": 40})
  s.update_preview(0.0)
  first = s.get_sound_data(512)
  s.update_alert(AudibleAlert.none)                               # selfdriveState says no alert, as it does onroad
  rest = play(s)
  assert np.count_nonzero(np.concatenate([first, rest])) == 1000
  s = make_soundd(tmp_path, [("WarningSoftVolume", 60)], saved={"WarningSoftVolume": 60})
  s.update_preview(0.0)
  first = s.get_sound_data(512)
  s.update_alert(AudibleAlert.none)
  assert s.pending_stop
  assert np.count_nonzero(np.concatenate([first, play(s, blocks=20)])) == 3000


def test_a_real_alert_wins(tmp_path):
  s = make_soundd(tmp_path, [("EngageVolume", 40)])
  s.current_alert = s.current_sound = AudibleAlert.warningSoft    # a real alert sounding: no preview
  s.update_preview(0.0)
  assert not s.previewing and s.current_alert == AudibleAlert.warningSoft
  s = make_soundd(tmp_path, [("EngageVolume", 40)])
  s.update_preview(0.0)
  s.get_sound_data(256)
  s.update_alert(AudibleAlert.warningImmediate)                   # a real alert arrives mid-preview: it takes over
  assert s.current_alert == AudibleAlert.warningImmediate and not s.previewing and not s.pending_stop
  assert s.current_sound_frame == 0


def test_a_second_change_restarts_the_preview(tmp_path):
  s = make_soundd(tmp_path, [("EngageVolume", 40), ("EngageVolume", 50)], saved={"EngageVolume": 50})
  s.native_audio = SimpleNamespace(previous_alert=AudibleAlert.engage)
  s.update_preview(0.0)
  s.get_sound_data(256)
  s.native_audio.previous_alert = AudibleAlert.engage
  s.update_preview(0.3)
  assert s.current_sound_frame == 0 and s.native_audio.previous_alert is None and s.previewing


def test_requests_are_read_every_quarter_second(tmp_path):
  s = make_soundd(tmp_path, [("EngageVolume", 40), ("DisengageVolume", 50)])
  s.update_preview(0.0)
  s.update_preview(0.1)
  assert s.current_alert == AudibleAlert.engage
  s.update_preview(0.3)
  assert s.current_alert == AudibleAlert.disengage


class _Params:
  def __init__(self, d):
    self.d = d

  def get_param_path(self, key=None):
    return str(self.d / key) if key else str(self.d)

  def put(self, key, value, block=False):
    (self.d / key).write_text(str(value))


def test_sounds_page_switch_and_volume_change(tmp_path, monkeypatch):
  from openpilot.starpilot.ui.feature_settings_state import FeatureSettingsRequest, row_default
  from openpilot.starpilot.ui.sounds_owner import PREVIEW_KEY, SoundsOwner
  monkeypatch.setattr(vp, "SWITCH_OFF", str(tmp_path / "off"))
  monkeypatch.setattr(vp, "PREVIEW", str(tmp_path / "req"))
  owner = SoundsOwner(_Params(tmp_path), lambda: True)

  def switch():
    return next(r for r in owner.snapshot().rows if r.key == PREVIEW_KEY)
  r = switch()
  assert (r.label, r.value, r.choices, r.default_value, r.available) == ("Sound Preview", "On", ("Off", "On"), "On", True)
  # a volume change asks soundd for a preview
  assert owner.apply(FeatureSettingsRequest(key="EngageVolume", expected=None, value="40%"))
  assert json.loads((tmp_path / "req").read_text())["key"] == "EngageVolume"
  # switched off: saved, and the next change is silent
  assert owner.apply(FeatureSettingsRequest(key=PREVIEW_KEY, expected=b"1", value="Off"))
  assert switch().value == "Off" and (tmp_path / "off").exists()
  (tmp_path / "req").unlink()
  assert owner.apply(FeatureSettingsRequest(key="EngageVolume", expected=b"40", value="45%"))
  assert not (tmp_path / "req").exists()
  # a stale screen can't flip it; Default puts it back on
  assert not owner.apply(FeatureSettingsRequest(key=PREVIEW_KEY, expected=b"1", value="On"))
  assert owner.apply(row_default(switch()))
  assert switch().value == "On" and not (tmp_path / "off").exists()
