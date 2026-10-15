import os
import pty
import time

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
