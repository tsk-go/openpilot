import os
import pty
import time

import pytest

from openpilot.starpilot.system.starview.starviewd import PicoBlinker


def _read(fd, wait=0.0):
  time.sleep(wait)
  out = b''
  while True:
    try:
      out += os.read(fd, 1024)
    except (BlockingIOError, OSError):
      return out


def _pair():
  master, slave = pty.openpty()
  os.set_blocking(master, False)
  return master, os.ttyname(slave)


def test_held_side_is_repeated_and_released_on_off():
  master, path = _pair()
  b = PicoBlinker(path)
  assert b.set("left")["side"] == "left"
  for _ in range(4):                       # the tablet repeats every 250 ms while held
    time.sleep(0.25)
    b.set("left")
  got = _read(master)
  assert got.count(b'L') >= 4 and b'0' not in got
  b.set("off")
  assert _read(master).endswith(b'000')


def test_released_when_the_tablet_stops_asking():
  master, path = _pair()
  b = PicoBlinker(path)
  b.set("right")
  _read(master)
  got = _read(master, wait=1.2)            # no more requests: let go after 0.6 s
  assert b'000' in got and got.rstrip(b'0').count(b'R') <= 4
  assert b.side == "0"


def test_switching_sides_never_holds_both():
  master, path = _pair()
  b = PicoBlinker(path)
  b.set("left")
  b.set("right")
  b.set("off")
  got = _read(master, wait=0.1)
  assert got.startswith(b'L') and b'R' in got and got.endswith(b'000')


def test_unplugged_mid_hold_keeps_the_thread_alive():
  master, path = _pair()
  b = PicoBlinker(path)
  b.set("left")
  os.close(master)                          # writes now fail (EIO), like the Pico being pulled out
  time.sleep(0.5)
  assert b.thread.is_alive() and b.fd is None and b.side == "0"
  assert b.set("off")["side"] == "off"      # no crash on an already dropped port


def test_only_a_pico_is_picked(monkeypatch):
  import glob
  monkeypatch.setattr(glob, "glob", lambda pat: ["/dev/ttyACM0"] if "ttyACM" in pat else [])
  monkeypatch.setattr(PicoBlinker, "_is_pico", staticmethod(lambda tty: False))
  b = PicoBlinker()
  with pytest.raises(RuntimeError):
    b._port()
  monkeypatch.setattr(PicoBlinker, "_is_pico", staticmethod(lambda tty: True))
  assert b._port() == "/dev/ttyACM0"


def test_why_is_published_while_held_and_cleared_on_release(tmp_path):
  master, path = _pair()
  sig = tmp_path / "starview_signal"
  b = PicoBlinker(path, signal_path=str(sig))
  assert b.set("left", "lane")["signal"] is True
  why, side, t0 = sig.read_text().split()
  assert (why, side) == ("lane", "left") and abs(float(t0) - time.monotonic()) < 0.5
  time.sleep(0.05)
  b.set("left", "lane")                    # repeated request: freshly stamped
  assert float(sig.read_text().split()[2]) > float(t0)
  b.set("right", "turn")
  assert sig.read_text().split()[:2] == ["turn", "right"]
  b.set("off")
  assert not sig.exists()
  _read(master)


def test_manual_hold_and_timeout_leave_no_signal(tmp_path):
  master, path = _pair()
  sig = tmp_path / "starview_signal"
  b = PicoBlinker(path, signal_path=str(sig))
  b.set("left", "bogus")                   # only turn / lane are published
  assert not sig.exists()
  b.set("left", "turn")
  assert sig.exists()
  time.sleep(1.2)                          # the tablet stopped asking: released, and the reason with it
  assert b.side == "0" and not sig.exists()
  _read(master)


def test_unplugged_clears_the_signal(tmp_path):
  master, path = _pair()
  sig = tmp_path / "starview_signal"
  b = PicoBlinker(path, signal_path=str(sig))
  b.set("left", "lane")
  os.close(master)
  time.sleep(0.5)
  assert b.fd is None and not sig.exists()


def test_window_relay_is_held_while_asked_and_released_after():
  master, path = _pair()
  b = PicoBlinker(path)
  assert b.window(True) == {"ok": True, "held": True}
  for _ in range(3):                       # StarLock repeats every 250 ms while the button is held
    time.sleep(0.25)
    b.window(True)
  got = _read(master)
  assert got.count(b'W') >= 4 and b'0' not in got
  assert b.set("off")["side"] == "off"     # the tablet letting go of a blinker doesn't let go of the window
  assert b'0' not in _read(master, 0.3)
  time.sleep(PicoBlinker.WINDOW_KEEP_S + 0.3)  # StarLock stopped asking: let go
  assert _read(master).endswith(b'000') and b.side == "0"


def test_window_let_go_and_never_over_a_blinker():
  master, path = _pair()
  b = PicoBlinker(path)
  b.window(True)
  assert b.window(False) == {"ok": True, "held": False}
  assert _read(master).endswith(b'W000')
  b.set("left")
  assert b.window(True) == {"ok": False, "error": "a turn signal is on"}
  assert b.side == "L"
  b.set("off")
