"""StarView fork: a changed alert volume plays on the comma for 3 s (volume_preview.py, soundd, sounds_owner)."""
import json
import os
from types import SimpleNamespace

import numpy as np

from openpilot.selfdrive.ui.soundd import PREVIEW_SOUNDS, SAMPLE_RATE, AudibleAlert, Soundd
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


def make_soundd(reqs):
  s = Soundd.__new__(Soundd)
  s.current_alert = AudibleAlert.none
  s.current_volume = 0.3
  s.saved_volumes = {}
  s.loaded_sounds = {AudibleAlert.engage: np.ones(1000, dtype=np.float32),
                     AudibleAlert.warningImmediate: np.full(500, 0.5, dtype=np.float32)}
  s.pack_loader = SimpleNamespace(is_builtin=lambda data: False)
  s.preview_reader = _Reader(reqs)
  s.preview_read_at = -1.0
  s.preview_sound = AudibleAlert.none
  s.preview_gain = 0.0
  s.preview_frame = 0
  s.preview_left = 0
  s.pending_stop = False
  return s


def test_preview_plays_three_seconds_at_the_new_level_then_stops():
  s = make_soundd([("EngageVolume", 40)])
  s.update_preview(0.0)
  out = np.concatenate([s.get_sound_data(4096) for _ in range(40)])
  played = out[np.abs(out) > 0]
  assert len(played) == int(3.0 * SAMPLE_RATE)               # exactly 3 s
  assert np.isclose(played[:1000].max(), 0.40)              # the engage chime, looped, at 40 %
  assert played[-1] < 0.40 * 0.01                           # faded out, no click
  assert not out[int(3.0 * SAMPLE_RATE):].any()


def test_auto_plays_at_the_ambient_level():
  s = make_soundd([("WarningImmediateVolume", AUTO)])
  s.update_preview(0.0)
  out = s.get_sound_data(400)
  assert np.isclose(out.max(), 0.5 * 0.3)                    # Auto: today's ambient volume (0.3), no ramp


def test_a_real_alert_wins():
  s = make_soundd([("EngageVolume", 40)])
  s.current_alert = AudibleAlert.engage                       # an alert already sounding: no preview
  s.update_preview(0.0)
  assert s.preview_left == 0
  s = make_soundd([("EngageVolume", 40)])
  s.update_preview(0.0)
  s.get_sound_data(1000)
  s.current_sound = AudibleAlert.none
  s.current_sound_frame = 0
  s.update_alert(AudibleAlert.engage)                         # a real alert arrives mid-preview: it stops
  assert s.preview_left == 0


def test_requests_are_read_every_quarter_second():
  s = make_soundd([("EngageVolume", 40), ("EngageVolume", 50)])
  s.update_preview(0.0)
  s.update_preview(0.1)
  assert s.preview_gain == 0.40
  s.update_preview(0.3)
  assert s.preview_gain == 0.50


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
