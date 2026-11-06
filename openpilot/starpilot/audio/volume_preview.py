"""Hear an alert volume on the comma when it's changed (Galaxy, StarView's tablet, the comma's own settings).

SoundsOwner.apply saves a volume and calls request(); soundd polls the file with its other slow reads (every 0.25 s)
and plays that alert at the saved level - the one-time chimes once, the repeating warnings 3 times like the real
alert - through its normal alert path, so the native mixer plays it too. Onroad or offroad, parked or driving, as
long as no real alert is sounding (a real alert also takes over). The "Sound Preview" switch on the Sounds & Alerts
page turns it off (SWITCH_OFF exists = off; on by default). Nothing in Params: /dev/shm for the request,
/data/starview for the switch.
"""
import json
import os
import time

PREVIEW = "/dev/shm/starpilot_volume_preview"
MAX_AGE_S = 2.0              # an old request (soundd restarted, a slow write) never plays
SWITCH_OFF = "/data/starview/sound_preview_off"


def enabled(off_path: str | None = None) -> bool:
  return not os.path.exists(off_path or SWITCH_OFF)


def set_enabled(on: bool, off_path: str | None = None) -> bool:
  off_path = off_path or SWITCH_OFF
  try:
    if on:
      if os.path.exists(off_path):
        os.unlink(off_path)
    else:
      os.makedirs(os.path.dirname(off_path), exist_ok=True)
      with open(off_path, "w") as f:
        f.write("off\n")
    return enabled(off_path) == on
  except OSError:
    return False


def request(key: str, value: int, path: str | None = None, wall=time.time, off_path: str | None = None) -> bool:  # noqa: TID251
  """Ask soundd to play `key`'s alert at `value` (0-100, or alert_volume.AUTO) - if the switch is on. Never raises."""
  if not enabled(off_path):
    return False
  path = path or PREVIEW
  tmp = f"{path}.{os.getpid()}.tmp"
  try:
    with open(tmp, "w") as f:
      json.dump({"key": key, "value": int(value), "t": wall()}, f)
    os.replace(tmp, path)
    return True
  except (OSError, TypeError, ValueError) as e:
    try:
      os.unlink(tmp)
    except OSError:
      pass
    try:
      from openpilot.common.swaglog import cloudlog
      cloudlog.warning(f"volume preview: couldn't ask soundd ({e})")
    except Exception:
      pass
    return False


class PreviewReader:
  """soundd's side: a new request since the last poll, or None. Only stats the file when nothing changed."""

  def __init__(self, path: str = PREVIEW, wall=time.time):  # noqa: TID251  wall: across processes
    self.path = path
    self.wall = wall
    self._mtime = None
    try:
      self._mtime = os.stat(path).st_mtime_ns     # whatever is there at start is old
    except OSError:
      pass

  def poll(self):
    try:
      m = os.stat(self.path).st_mtime_ns
    except OSError:
      return None
    if m == self._mtime:
      return None
    self._mtime = m
    try:
      with open(self.path) as f:
        d = json.load(f)
      key, value, t = str(d["key"]), int(d["value"]), float(d["t"])
    except (OSError, ValueError, KeyError, TypeError):
      return None
    if abs(self.wall() - t) > MAX_AGE_S:
      return None
    return key, value
