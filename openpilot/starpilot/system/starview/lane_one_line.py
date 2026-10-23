"""Lane Centering with one good line (patch 37), switched on from StarView's tablet.

StarPilot's Lane Centering steers to the middle of the lane only while both inner lines are good. With this on,
lane_centering.py also steers by one good line (+/- the lane width remembered from both lines) at half strength.
Off (no file, the default): StarPilot's Lane Centering exactly as it is. The tablet shows the switch on Galaxy's
Lane Centering page and sends it with starviewd's "lane_one_line_set" {on}; it is kept in PATH (no params key).
"""
import os

PATH = "/data/starview/lane_one_line"


def write(on, path: str = PATH) -> bool:
  if not isinstance(on, bool):
    raise ValueError("on must be true or false")
  if not on:
    try:
      os.unlink(path)
    except FileNotFoundError:
      pass
    return False
  os.makedirs(os.path.dirname(path), exist_ok=True)
  tmp = f"{path}.tmp"
  with open(tmp, "w") as f:
    f.write("1")
  os.replace(tmp, path)
  return True


def read(path: str = PATH) -> bool:
  try:
    with open(path) as f:
      return f.read(4).strip() == "1"
  except OSError:
    return False
