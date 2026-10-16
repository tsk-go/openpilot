#!/usr/bin/env python3
"""Pair a StarView tablet from a terminal (SSH), without the comma's screen.

  python3 -m openpilot.starpilot.system.starview.pair            # QR code to scan with the StarView app
  python3 -m openpilot.starpilot.system.starview.pair --unpair   # new key: every paired tablet must scan again
  python3 -m openpilot.starpilot.system.starview.pair --usb-key on|off
                                                                 # does a tablet on the USB tether need the key too

The QR holds the same starview://pair link as the one on the comma's screen (pairing.py).
"""
import argparse
import sys

from openpilot.starpilot.system.starview import pairing


def qr_lines(text: str) -> list[str]:
  """The QR code as terminal text: two modules per character row (upper/lower half blocks), dark on light."""
  from openpilot.common.qrcode import _Qr, _capacity
  raw = text.encode()
  version = next((v for v in range(1, 21) if 4 + (8 if v <= 9 else 16) + len(raw) * 8 <= _capacity(v) * 8), None)
  if version is None:
    raise ValueError("pairing link too long for a QR code")
  m = _Qr(version, raw).modules
  n, border = len(m), 2
  def dark(x, y):
    return 0 <= x < n and 0 <= y < n and m[y][x]
  out = []
  for y in range(-border, n + border, 2):
    row = []
    for x in range(-border, n + border):
      top, bottom = dark(x, y), dark(x, y + 1)
      row.append(" " if top and bottom else "▄" if top else "▀" if bottom else "█")
    out.append("".join(row))
  return out


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("--unpair", action="store_true")
  ap.add_argument("--usb-key", choices=("on", "off"))
  a = ap.parse_args(argv)
  if a.unpair:
    pairing.rotate_key()
    print("New pairing key: every StarView tablet has to scan the QR code again.")
  if a.usb_key:
    pairing.set_usb_requires_key(a.usb_key == "on")
    print(f"USB tether needs the key: {a.usb_key}")
  if a.unpair or a.usb_key:
    return 0
  try:
    from openpilot.common.params import Params
    dongle = Params().get("DongleId") or ""
  except Exception:
    dongle = ""
  uri = pairing.pairing_uri(dongle)
  print("\n".join(qr_lines(uri)))
  print("\nScan with StarView (Settings > Pair). Link:", uri.split("k=")[0] + "k=…")
  return 0


if __name__ == "__main__":
  sys.exit(main())
