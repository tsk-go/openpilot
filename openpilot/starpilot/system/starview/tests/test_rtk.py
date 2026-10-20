import base64
import os
import struct
import time

from openpilot.starpilot.system.starview import rtk


def pvt_payload(fix=3, carr=0, used=12, lat=40.7128, lon=-74.006, hacc_mm=3480, age_idx=0, headveh=None):
  p = bytearray(92)
  p[20], p[21], p[22], p[23] = fix, 0x01 | (carr << 6) | (0x20 if headveh is not None else 0), 0x80, used
  struct.pack_into("<iiiiII", p, 24, round(lon * 1e7), round(lat * 1e7), 10_000, 5_000, hacc_mm, 5000)
  struct.pack_into("<ii", p, 60, 13_400, 9_000_000)
  struct.pack_into("<H", p, 76, 150)
  struct.pack_into("<H", p, 78, age_idx << 1)
  struct.pack_into("<i", p, 84, round((headveh or 0) * 1e5))
  return bytes(p)


def sat_payload(sats):
  p = bytearray(8 + 12 * len(sats))
  p[4], p[5] = 1, len(sats)
  for k, (cno, used, corr) in enumerate(sats):
    p[8 + 12 * k + 2] = cno
    struct.pack_into("<I", p, 8 + 12 * k + 8, (0x08 if used else 0) | (0x40 if corr else 0))
  return bytes(p)


def test_parser_keeps_ubx_frames_and_skips_everything_else():
  parser = rtk.UbxParser()
  frame = rtk.ubx(0x01, 0x07, pvt_payload())
  stream = b"$GNGGA,junk*00\r\n" + frame[:30]
  assert parser.feed(stream) == []                      # half a frame: wait for the rest
  bad = bytearray(rtk.ubx(0x10, 0x10, bytes(16)))
  bad[-1] ^= 0xFF                                       # broken checksum: dropped
  out = parser.feed(frame[30:] + b"\xd3\x00\x13RTCM-ish" + bytes(bad) + rtk.ubx(0x01, 0x35, sat_payload([(40, 1, 0)])))
  assert [(c, m) for c, m, _ in out] == [(0x01, 0x07), (0x01, 0x35)]


def test_position_rtk_and_correction_age():
  p = rtk.parse_pvt(pvt_payload(fix=3, carr=2, hacc_mm=14, age_idx=2, headveh=91.5))
  assert p["rtk"] == "fixed" and p["fixType"] == "3D" and p["used"] == 12
  assert abs(p["lat"] - 40.7128) < 1e-7 and abs(p["lon"] + 74.006) < 1e-7
  assert p["hAccM"] == 0.014 and p["correctionAgeS"] == 2 and p["carHeadingDeg"] == 91.5
  assert rtk.parse_pvt(pvt_payload(fix=1))["fixType"] == "dead reckoning"
  assert rtk.parse_pvt(pvt_payload(carr=1))["rtk"] == "float"
  assert rtk.parse_pvt(b"short") is None


def test_satellites_heard_used_and_corrected():
  assert rtk.parse_sat(sat_payload([(40, 1, 1), (35, 1, 0), (20, 0, 0), (0, 0, 0)])) == {"heard": 3, "usedSats": 2, "corrected": 1}


def test_corrections_only_while_the_receiver_is_there_and_capped():
  r = rtk.Rtk(port_glob="/nonexistent/*")
  assert r.status() is None                             # never seen: the tablet hides the RTK part
  assert r.feed_rtcm(b"x") == {"ok": False, "error": "RTK receiver not connected"}
  r.fd, r.port = 99, "/dev/fake-u-blox"
  for _ in range(5):
    assert r.feed_rtcm(bytes(20_000)) == {"ok": True}
  assert len(r.rtcm) == rtk.RTCM_MAX and r.dropped == 100_000 - rtk.RTCM_MAX


def test_end_to_end_over_a_serial_line(tmp_path):
  master, slave = os.openpty()
  link = tmp_path / "usb-u-blox_AG_-_www.u-blox.com_u-blox_GNSS_receiver-if00"
  link.symlink_to(os.ttyname(slave))
  now = [100.0]
  r = rtk.Rtk(port_glob=str(tmp_path / "*u-blox*"), clock=lambda: now[0])
  r.step(timeout=0.05)                                  # finds it, sets it up, asks for the 1 Hz reports
  time.sleep(0.05)
  sent = os.read(master, 4096)
  assert sent.startswith(rtk.SETUP) and rtk.POLLS in sent
  os.write(master, rtk.ubx(0x01, 0x07, pvt_payload(carr=1, hacc_mm=120)) + rtk.ubx(0x01, 0x35, sat_payload([(44, 1, 1)])) +
           rtk.ubx(0x10, 0x10, bytes(12) + b"\x01" + bytes(3)) + rtk.ubx(0x10, 0x14, bytes(5) + bytes([1 | (4 << 1)]) + bytes(10)))
  for _ in range(5):
    r.step(timeout=0.05)
  st = r.status()
  assert st["connected"] and st["fresh"] and st["rtk"] == "float" and st["hAccM"] == 0.12
  assert st["usedSats"] == 1 and st["fusion"] == "on" and st["mount"] == "fine" and st["mountAuto"]
  assert r.feed_rtcm(b"\xd3\x00\x04RTCM")["ok"]
  r.step(timeout=0.01)
  time.sleep(0.05)
  assert b"\xd3\x00\x04RTCM" in os.read(master, 4096)
  assert r.status()["rtcmBytes"] == 7 and r.status()["rtcmAgeS"] == 0.0
  now[0] += 3.0
  assert r.status()["fresh"] is False and "lat" not in r.status()   # an old fix is never shown as current
  os.close(master)
  for _ in range(3):
    r.step(timeout=0.05)
  assert r.status()["connected"] is False                # unplugged: tablet sees it, comma retries every 5 s


def test_tablet_corrections_action(monkeypatch):
  from openpilot.starpilot.system.starview import starviewd
  hub = starviewd.Hub.__new__(starviewd.Hub)
  got = []
  hub.rtk = type("R", (), {"feed_rtcm": lambda self, data: got.append(data) or {"ok": True}})()
  assert hub.control({"action": "rtk_rtcm", "b64": base64.b64encode(b"\xd3abc").decode()}) == {"ok": True}
  assert got == [b"\xd3abc"]
  assert hub.control({"action": "rtk_rtcm", "b64": "not base64!"})["ok"] is False
  assert hub.control({"action": "rtk_rtcm"})["ok"] is False
