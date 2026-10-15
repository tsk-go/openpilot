#!/usr/bin/env python3
"""blink.py - drive the Sienna turn signals through the Pico relay box (comma side, stdlib only).
  blink.py tap-left | tap-right        lane-change tap (TL/TR closed 0.6 s -> meter does its 3 blinks)
  blink.py left  [SECS] | right [SECS] latched signal (TL/TR + CR) for SECS (default 5), Ctrl-C stops early
  blink.py test                        left 4 s, pause, right 4 s, pause, tap-left, tap-right
  blink.py off                         release everything
"""
import glob
import os
import sys
import termios
import time

def port():
  cands = sorted(glob.glob('/dev/serial/by-id/*MicroPython*')) + sorted(glob.glob('/dev/ttyACM*'))
  if not cands:
    sys.exit('Pico not found (no /dev/ttyACM*). Is it plugged into the comma?')
  return cands[0]

def open_port(path):
  fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
  a = termios.tcgetattr(fd)
  a[0] = a[1] = a[3] = 0                                   # raw: no input/output processing, no echo
  a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
  termios.tcsetattr(fd, termios.TCSANOW, a)
  return fd

def hold(fd, ch, secs):
  """send ch every 0.2 s for secs (the Pico drops everything if it hears nothing for 1 s)"""
  end = time.monotonic() + secs
  while time.monotonic() < end:
    os.write(fd, ch.encode())
    time.sleep(0.2)

def off(fd):
  for _ in range(3):
    os.write(fd, b'0')
    time.sleep(0.05)

def main(argv):
  if len(argv) < 2 or argv[1] not in ('tap-left', 'tap-right', 'left', 'right', 'test', 'off'):
    print(__doc__)
    return 2
  cmd, p = argv[1], port()
  fd = open_port(p)
  print(f'using {p}')
  try:
    if cmd == 'tap-left':
      hold(fd, 'l', 0.6)
    elif cmd == 'tap-right':
      hold(fd, 'r', 0.6)
    elif cmd in ('left', 'right'):
      secs = float(argv[2]) if len(argv) > 2 else 5.0
      print(f'{cmd} signal for {secs:g}s (Ctrl-C to stop)')
      hold(fd, 'L' if cmd == 'left' else 'R', secs)
    elif cmd == 'test':
      for label, ch, secs in (('LEFT latched', 'L', 4), ('off', '0', 2), ('RIGHT latched', 'R', 4), ('off', '0', 2),
                              ('tap LEFT', 'l', 0.6), ('off', '0', 4), ('tap RIGHT', 'r', 0.6), ('off', '0', 1)):
        print(f'  {label}')
        hold(fd, ch, secs)
  except KeyboardInterrupt:
    pass
  finally:
    off(fd)
    os.close(fd)
    print('released')
  return 0

if __name__ == '__main__':
  sys.exit(main(sys.argv))
