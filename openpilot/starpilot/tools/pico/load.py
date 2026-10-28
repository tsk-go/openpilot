"""Load the relay box's program onto the Pico from the comma (MicroPython raw REPL, stdlib only), keeping the one it
had as main_old.py, then restart it. Checks the copy before switching; does nothing when the Pico already has it.
  python3 starpilot/tools/pico/load.py [starpilot/tools/pico/main.py]      |      python3 .../load.py --restore
"""
import glob
import os
import sys
import termios
import time


def is_pico(tty):
  try:
    dev = os.path.realpath(f"/sys/class/tty/{os.path.basename(tty)}/device")
    with open(os.path.join(os.path.dirname(dev), "idVendor")) as f:
      return f.read().strip().lower() == "2e8a"
  except OSError:
    return False


cands = sorted(glob.glob("/dev/serial/by-id/*MicroPython*")) + [t for t in sorted(glob.glob("/dev/ttyACM*")) if is_pico(t)]
if not cands:
  raise SystemExit("Pico not found - is it plugged into the comma's hub?")
fd = os.open(cands[0], os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
a = termios.tcgetattr(fd)
a[0] = a[1] = a[3] = 0
a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
termios.tcsetattr(fd, termios.TCSANOW, a)


def read_until(marker, secs=5):
  out, end = b"", time.monotonic() + secs
  while marker not in out:
    if time.monotonic() > end:
      raise SystemExit(f"Pico didn't answer (got {out[-200:]!r}) - nothing was changed unless it says so above")
    try:
      out += os.read(fd, 4096)
    except BlockingIOError:
      time.sleep(0.02)
  return out


def run(code):
  """Run code in the raw REPL; returns its printed output, raises on a Python error."""
  data = code.encode()
  for i in range(0, len(data), 256):
    os.write(fd, data[i:i + 256])
    time.sleep(0.01)
  os.write(fd, b"\x04")
  out = read_until(b"\x04>", 10)
  body = out.split(b"OK", 1)[-1]
  stdout, err = body.split(b"\x04")[0], body.split(b"\x04")[1]
  if err.strip():
    raise SystemExit("Pico error: " + err.decode(errors="replace"))
  return stdout.decode(errors="replace")


os.write(fd, b"0\x03\x03")
time.sleep(0.3)
os.write(fd, b"\x01")                       # raw REPL
read_until(b"raw REPL; CTRL-B to exit\r\n>")
try:
  if sys.argv[1:] == ["--restore"]:
    run("import os\nos.rename('main_old.py','main.py')\nprint('ok')")
    print("old main.py is back")
  else:
    new = open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")).read()
    if run("print(open('main.py').read(),end='')").replace("\r\n", "\n") == new:
      raise SystemExit("the Pico already has this main.py - nothing changed")
    run("f=open('main_new.py','w')")
    for i in range(0, len(new), 200):
      run(f"f.write({new[i:i + 200]!r})")
    run("f.close()")
    back = run("print(open('main_new.py').read(),end='')").replace("\r\n", "\n")
    if back != new:
      raise SystemExit("copy on the Pico doesn't match - old main.py left in place")
    run("import os\ntry:\n os.remove('main_old.py')\nexcept OSError:\n pass\n" +
        "os.rename('main.py','main_old.py')\nos.rename('main_new.py','main.py')\nprint('ok')")
    print(f"new main.py loaded ({len(new.splitlines())} lines, checked); the old one is kept as main_old.py")
finally:
  os.write(fd, b"\x02")                     # back to the normal prompt
  time.sleep(0.2)
  os.write(fd, b"\x04")                     # soft reset: main.py runs
  time.sleep(1)
  os.close(fd)
print("Pico restarted")
