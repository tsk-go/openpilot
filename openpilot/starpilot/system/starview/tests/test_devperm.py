"""AGNOS 20.5.2 brings serial / USB nodes up root-only: starviewd hands its own devices to itself (devperm.py)."""
import os

from openpilot.starpilot.system.starview import devperm


def test_usable_device_needs_no_sudo(tmp_path, monkeypatch):
  calls = []
  monkeypatch.setattr(devperm.subprocess, "run", lambda *a, **k: calls.append(a[0]))
  node = tmp_path / "ttyACM1"
  node.write_text("")
  assert devperm.grant(str(node))
  assert calls == []


def test_locked_device_is_handed_over_once_per_5_s(tmp_path, monkeypatch):
  node = str(tmp_path / "ttyACM1")
  ok = {node: False}
  calls = []

  def run(cmd, **kwargs):
    calls.append(cmd)
    if cmd[2] == "chmod":
      ok[node] = True

  monkeypatch.setattr(devperm.subprocess, "run", run)
  monkeypatch.setattr(devperm.os, "access", lambda path, mode: ok.get(path, False))
  devperm._last.clear()
  assert devperm.grant(node)
  assert calls == [["sudo", "-n", "chown", str(os.getuid()), node], ["sudo", "-n", "chmod", "u+rw", node]]
  ok[node] = False                      # refused again (sudo said no): not asked again within 5 s
  assert not devperm.grant(node)
  assert len(calls) == 2


def test_usb_nodes_by_vendor_and_adb_interface(tmp_path, monkeypatch):
  def device(name, vendor, product, bus, dev, adb=False):
    d = tmp_path / name
    d.mkdir()
    for k, v in (("idVendor", vendor), ("idProduct", product), ("busnum", bus), ("devnum", dev)):
      (d / k).write_text(v + "\n")
    i = d / f"{name}:1.0"
    i.mkdir()
    for k, v in zip(("Class", "SubClass", "Protocol"), ("ff", "42", "01") if adb else ("02", "02", "01"), strict=True):
      (i / f"bInterface{k}").write_text(v + "\n")
  device("1-1.1", "0bda", "2838", "1", "7")
  device("1-1.2", "17ef", "201c", "1", "9", adb=True)
  device("1-1.3", "2e8a", "0005", "1", "12")
  monkeypatch.setattr(devperm.glob, "glob", lambda pattern: sorted(str(p) for p in tmp_path.glob(pattern.replace(str(tmp_path) + "/", "")))
                      if pattern.startswith(str(tmp_path)) else sorted(str(p) for p in tmp_path.iterdir()))
  granted = []
  monkeypatch.setattr(devperm, "grant", granted.append)
  devperm.grant_usb("0bda", "2838")
  assert granted == ["/dev/bus/usb/001/007"]
  granted.clear()
  devperm._last.clear()
  devperm.grant_adb()
  assert granted == ["/dev/bus/usb/001/009"]


def test_rtk_found_by_vendor_without_the_by_id_links(monkeypatch):
  from openpilot.starpilot.system.starview import rtk
  r = rtk.Rtk.__new__(rtk.Rtk)
  r.port_glob = rtk.PORT_GLOB
  monkeypatch.setattr(rtk.glob, "glob", lambda pattern: ["/dev/ttyACM0", "/dev/ttyACM1"] if pattern == "/dev/ttyACM*" else [])
  monkeypatch.setattr(rtk.Rtk, "_is_ublox_tty", staticmethod(lambda path: path == "/dev/ttyACM1"))
  assert r._find() == "/dev/ttyACM1"
  r.port_glob = "/tmp/test-ports/*"          # a test's own ports: never the real ttyACM nodes
  assert r._find() is None
