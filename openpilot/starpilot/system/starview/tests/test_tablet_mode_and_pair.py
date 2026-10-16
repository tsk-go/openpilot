import os
import sys
import time
import types
from types import SimpleNamespace

import numpy as np

from openpilot.starpilot.system.starview.tablet_mode import CRITICAL, StarViewTabletMode

NORMAL = 0


class FakeDevice:
  def __init__(self):
    self._awake = True
    self.wake_calls = 0
    self.resets = 0

  def _update_wakefulness(self):
    self.wake_calls += 1
    self._set_awake(True)

  def _set_awake(self, on):
    self._awake = on

  def _reset_interactive_timeout(self):
    self.resets += 1


class FakeSM(dict):
  def __init__(self, alert_status):
    super().__init__(selfdriveState=SimpleNamespace(alertStatus=alert_status))
    self.valid = {"selfdriveState": True}
    self.alive = {"selfdriveState": True}


def make(tmp_path, started=True, alert=NORMAL):
  dev = FakeDevice()
  ui_state = SimpleNamespace(started=started, sm=FakeSM(alert))
  flag = tmp_path / "starview_tablet"
  return StarViewTabletMode(dev, ui_state, flag_path=str(flag)), dev, ui_state, flag


def test_screen_off_while_tablet_connected_and_back_when_it_leaves(tmp_path):
  mode, dev, _, flag = make(tmp_path)
  flag.write_text("1")
  mode.update(10.0)
  assert mode.active and not dev._awake
  dev._update_wakefulness()                 # the normal wake logic must not light the screen while active
  assert not dev._awake and dev.wake_calls == 0
  old = time.time() - 10  # noqa: TID251  file mtimes are wall clock
  os.utime(flag, (old, old))                # the tablet stopped refreshing the flag
  mode.update(11.0)
  assert not mode.active and dev._awake and dev.resets == 1
  dev._update_wakefulness()
  assert dev.wake_calls == 1


def test_critical_alert_always_lights_the_comma_screen(tmp_path):
  mode, dev, ui_state, flag = make(tmp_path)
  flag.write_text("1")
  mode.update(10.0)
  assert mode.active
  ui_state.sm = FakeSM(CRITICAL)
  mode.update(10.1)                         # checked every frame, not once a second
  assert not mode.active and dev._awake


def test_offroad_never_enters_tablet_mode(tmp_path):
  mode, dev, _, flag = make(tmp_path, started=False)
  flag.write_text("1")
  mode.update(10.0)
  assert not mode.active and dev._awake


def test_terminal_qr_decodes_to_the_pairing_link():
  try:
    import pyray  # noqa: F401  common/qrcode imports raylib for its UI textures
  except ImportError:                        # off the device: the QR encoder itself doesn't need it
    class _Raylib(types.ModuleType):
      def __getattr__(self, name):
        return object
    sys.modules["pyray"] = _Raylib("pyray")
  from openpilot.common import qrcode
  from openpilot.starpilot.system.starview.pair import qr_lines
  uri = "starview://pair?k=0123456789abcdef0123456789abcdef&p=8090&d=abcdef0123456789&h=192.168.42.129"
  lines = qr_lines(uri)
  # back to modules: a space is two dark modules, the half blocks one, a full block none (dark terminal)
  rows = []
  for line in lines:
    top = [ch in (" ", "▄") for ch in line]
    bottom = [ch in (" ", "▀") for ch in line]
    rows += [top, bottom]
  m = np.array(rows, dtype=bool)
  img = np.where(np.pad(m, 4), 0, 255).astype(np.uint8)
  img = np.repeat(np.repeat(img, 6, axis=0), 6, axis=1)
  assert qrcode.decode(img) == uri
