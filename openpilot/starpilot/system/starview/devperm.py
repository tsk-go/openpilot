"""StarView's own USB devices, usable by starviewd again after AGNOS 20.5.2.

AGNOS 20.5.2 (upstream 5817fccf8) dropped the udev rules that opened serial and USB device nodes up to the comma user;
upstream had to chgrp its own modem ports (1c1a3c033 "Recover modem ports after AGNOS udev removal"). starviewd runs
as the comma user (service.py --uid), so the Pico relay box (/dev/ttyACM*: blinker relays, window close) came up
"Permission denied", and so would the RTK receiver, the fob radio dongle and the tablet over adb. NetworkManager also
leaves the tablet's USB tethering link "strictly unmanaged" now, so starviewd addresses it itself (address_tether_links).

Before opening one of its own devices starviewd now hands that one node to its own user with `sudo -n chown`, as offline
mode and hub_power already use sudo -n. Only nodes it already picked by USB vendor (Pico 2e8a, u-blox 1546, RTL-SDR
0bda:2838) or by the adb interface (the tablet), and only when it can't use them already: when it can, this is one
access() call. A replugged device comes back root-only and is handed over again at the next open.
"""
from __future__ import annotations

import glob
import os
import subprocess
import time

from openpilot.common.swaglog import cloudlog

ADB_CLASS = ("ff", "42", "01")   # Android's adb interface: vendor class, subclass 0x42, protocol 1
_last: dict[str, float] = {}


def grant(path: str) -> bool:
  """True when starviewd can read and write `path` (after handing it over if it couldn't)."""
  if os.access(path, os.R_OK | os.W_OK):
    return True
  now = time.monotonic()
  if now - _last.get(path, -1e9) < 5.:       # a refused sudo isn't asked again every call
    return False
  _last[path] = now
  try:
    subprocess.run(["sudo", "-n", "chown", str(os.getuid()), path], capture_output=True, timeout=5)
    subprocess.run(["sudo", "-n", "chmod", "u+rw", path], capture_output=True, timeout=5)
  except (OSError, subprocess.SubprocessError) as e:
    cloudlog.warning(f"starview: device access {path}: {e}")
    return False
  ok = os.access(path, os.R_OK | os.W_OK)
  cloudlog.info(f"starview: device access {path}: {'handed over' if ok else 'still refused'}")
  return ok


def _read(path: str) -> str:
  with open(path) as f:
    return f.read(64).strip().lower()


def usb_node(device_dir: str) -> str | None:
  """/dev/bus/usb/BBB/DDD of a /sys/bus/usb/devices/<device> folder."""
  try:
    return f"/dev/bus/usb/{int(_read(device_dir + '/busnum')):03d}/{int(_read(device_dir + '/devnum')):03d}"
  except (OSError, ValueError):
    return None


def _devices():
  return [d for d in glob.glob("/sys/bus/usb/devices/*") if ":" not in os.path.basename(d) and os.path.exists(d + "/idVendor")]


def grant_usb(vendor: str, product: str | None = None) -> None:
  """Hands over the USB nodes of the devices with this vendor (and product)."""
  for d in _devices():
    try:
      if _read(d + "/idVendor") != vendor or (product is not None and _read(d + "/idProduct") != product):
        continue
    except OSError:
      continue
    node = usb_node(d)
    if node:
      grant(node)


def grant_adb() -> None:
  """Hands over the USB nodes of devices with an adb interface (the tablet), for starviewd's adb server. At most every
  10 s (adb runs every few seconds at most)."""
  now = time.monotonic()
  if now - _last.get("adb", -1e9) < 10.:
    return
  _last["adb"] = now
  for d in _devices():
    for interface in glob.glob(d + "/" + os.path.basename(d) + ":*"):
      try:
        kind = tuple(_read(f"{interface}/bInterface{k}") for k in ("Class", "SubClass", "Protocol"))
      except OSError:
        continue
      if kind == ADB_CLASS:
        node = usb_node(d)
        if node:
          grant(node)
        break


TETHER_DRIVERS = ("rndis_host", "cdc_ether", "cdc_ncm")   # a phone / tablet sharing its connection over USB


def tether_links(drivers=TETHER_DRIVERS) -> list[str]:
  """Network interfaces of USB tethering devices plugged into the comma (the tablet's rndis link)."""
  out = []
  for path in sorted(glob.glob("/sys/class/net/*")):
    try:
      if os.path.basename(os.path.realpath(path + "/device/driver")) in drivers:
        out.append(os.path.basename(path))
    except OSError:
      continue
  return out



def tablet_addrs(ip_output: str) -> list[str]:
  """The tablet's own addresses on its USB tethering interfaces, from its `ip -4 -o addr show` (adb)."""
  out = []
  for line in (ip_output or "").splitlines():
    parts = line.split()
    if len(parts) >= 4 and parts[2] == "inet" and parts[1].rstrip(":").startswith(("rndis", "ncm", "usb")):
      out.append(parts[3])
  return out


def comma_addr(tablet_cidr: str) -> str | None:
  """An address for the comma on the tablet's tethering network: host .200 of it (Android hands out low ones)."""
  import ipaddress
  try:
    iface = ipaddress.ip_interface(tablet_cidr)
  except ValueError:
    return None
  net = iface.network
  if net.prefixlen > 24 or net.version != 4:
    return None
  for host in (200, 201):
    addr = net.network_address + host
    if addr != iface.ip:
      return f"{addr}/{net.prefixlen}"
  return None


def address_tether_links(tablet_cidrs: list[str], log=cloudlog.warning) -> list[str]:
  """AGNOS 20.5.2: NetworkManager leaves a newly plugged USB tethering link "strictly unmanaged" (no udev to tell it
  the device is ready), so the tablet said rndis and the link never got an address (Nov 16). Puts the comma on the
  tablet's tethering network itself: the tablet's own address (adb) -> host .200 of that network on the first tethering
  link (rndis_host / cdc_ncm) that has no IPv4 address, and the link up. No default route: the comma's internet stays
  as it was (Mapbox goes through the tablet's relay, navigation/relay.py). Returns the links it set."""
  if not tablet_cidrs:
    return []
  try:
    r = subprocess.run(["ip", "-4", "-o", "addr"], capture_output=True, text=True, timeout=5)
    have = {line.split()[1] for line in r.stdout.splitlines() if len(line.split()) > 3}
  except (OSError, subprocess.SubprocessError):
    return []
  links = [link for link in tether_links(("rndis_host", "cdc_ncm")) if link not in have]
  mine = comma_addr(tablet_cidrs[0])
  if not links or mine is None:
    return []
  link = links[0]
  try:
    subprocess.run(["sudo", "-n", "ip", "addr", "replace", mine, "dev", link], capture_output=True, timeout=5)
    subprocess.run(["sudo", "-n", "ip", "link", "set", link, "up"], capture_output=True, timeout=5)
  except (OSError, subprocess.SubprocessError) as e:
    log(f"starview: tether link {link}: {e}")
    return []
  log(f"starview: tether link {link} had no address (tablet {tablet_cidrs[0]}); set {mine}")
  return [link]
