import base64
import json
import os
import struct
import time

from openpilot.starpilot.system.starview import rtk


def pvt_payload(fix=3, carr=0, used=12, lat=40.7128, lon=-74.006, hacc_mm=3480, age_idx=0, headveh=None, head_acc=2.5,
                when=(2026, 10, 21, 14, 30, 5), ok=True):
  p = bytearray(92)
  struct.pack_into("<HBBBBBB", p, 4, *when, 0x07)
  struct.pack_into("<i", p, 16, 250_000_000)
  struct.pack_into("<II", p, 68, 120, round(head_acc * 1e5))
  p[20], p[21], p[22], p[23] = fix, int(ok) | (carr << 6) | (0x20 if headveh is not None else 0), 0x80, used
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


def test_fix_handed_to_navigation_in_the_phone_format():
  pvt = rtk.parse_pvt(pvt_payload(hacc_mm=1500))
  assert pvt["unixMs"] == 1_792_593_005_250 and pvt["speedAccMs"] == 0.12 and pvt["headingAccDeg"] == 2.5
  gps = rtk.handoff_fix(pvt, 5_000_000_000)
  assert gps["sourceMonoTime"] == 5_000_000_000 and gps["hasFix"] and gps["horizontalAccuracy"] == 1.5
  assert abs(gps["latitude"] - 40.7128) < 1e-7 and gps["speed"] == 13.4 and gps["bearingDeg"] == 90.0
  assert gps["bearingAccuracyDeg"] == 2.5 and gps["unixTimestampMillis"] == 1_792_593_005_250
  # only a real fix that the comma's own GPS checks would accept too
  assert rtk.handoff_fix(rtk.parse_pvt(pvt_payload(fix=2)), 1) is None             # 2D
  assert rtk.handoff_fix(rtk.parse_pvt(pvt_payload(fix=1)), 1) is None             # dead reckoning only
  assert rtk.handoff_fix(rtk.parse_pvt(pvt_payload(ok=False)), 1) is None          # gnssFixOK off
  assert rtk.handoff_fix(rtk.parse_pvt(pvt_payload(hacc_mm=25_100)), 1) is None    # worse than 25 m
  assert rtk.handoff_fix(rtk.parse_pvt(pvt_payload(fix=4)), 1) is not None         # GNSS + dead reckoning
  # no heading yet (parked, fusion not aligned): the position counts, the heading doesn't
  import math
  from openpilot.starpilot.gps.source import bearing
  still = rtk.handoff_fix(rtk.parse_pvt(pvt_payload(head_acc=180.)), 1)
  assert still is not None and math.isnan(still["bearingAccuracyDeg"]) and bearing(type("G", (), still)) is None
  assert bearing(type("G", (), gps)) == 90.0
  # no valid date: still a position, without a wall-clock time
  assert rtk.handoff_fix(rtk.parse_pvt(pvt_payload(when=(0, 0, 0, 0, 0, 0))), 1)["unixTimestampMillis"] == 0


def test_navigation_uses_it_only_without_a_comma_or_car_fix(tmp_path):
  from types import SimpleNamespace
  from openpilot.starpilot.gps.phone import read_phone_gps
  from openpilot.starpilot.gps.source import select_source
  path = tmp_path / "starpilot_phone_gps.json"
  mono = [7_000_000_000]
  now = [100.0]
  r = rtk.Rtk(port_glob="/nonexistent/*", clock=lambda: now[0], handoff_path=path, mono_ns=lambda: mono[0])
  r.handle(0x01, 0x07, pvt_payload(hacc_mm=900))
  fix = read_phone_gps(7_400_000_000, path=path)
  assert fix is not None and fix[0] == 7_000_000_000 and fix[1].horizontalAccuracy == 0.9

  class NoGps:  # the comma's GPS and the car's have nothing
    valid = logMonoTime = {}
    def __getitem__(self, key):
      raise KeyError(key)
  assert select_source(NoGps(), 7_400_000_000, mode="backup", phone_fix=fix)[0] == "phone"
  assert select_source(NoGps(), 7_400_000_000, mode="comma", phone_fix=fix) is None   # Galaxy's "comma only" still wins

  class CommaGps(NoGps):
    valid = {"gpsLocation": True}
    logMonoTime = {"gpsLocation": 7_300_000_000}
    def __getitem__(self, key):
      if key != "gpsLocation":
        raise KeyError(key)
      return SimpleNamespace(hasFix=True, latitude=40.7, longitude=-74.0, horizontalAccuracy=8., source="qcomdiag")
  assert select_source(CommaGps(), 7_400_000_000, mode="backup", phone_fix=fix)[0] == "comma"

  # at most 5 a second; an unusable fix leaves the last good one to age out
  path.unlink()
  now[0] += 0.1
  r.handle(0x01, 0x07, pvt_payload())
  assert not path.exists()
  now[0] += 0.2
  r.handle(0x01, 0x07, pvt_payload(fix=2))
  assert not path.exists()
  now[0] += 0.2
  r.handle(0x01, 0x07, pvt_payload())
  assert path.exists()


def test_end_to_end_over_a_serial_line(tmp_path):
  master, slave = os.openpty()
  link = tmp_path / "usb-u-blox_AG_-_www.u-blox.com_u-blox_GNSS_receiver-if00"
  link.symlink_to(os.ttyname(slave))
  now = [100.0]
  r = rtk.Rtk(port_glob=str(tmp_path / "*u-blox*"), clock=lambda: now[0], handoff_path=tmp_path / "handoff.json")
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
  assert json.loads((tmp_path / "handoff.json").read_text())["horizontalAccuracy"] == 0.12   # handed to navigation
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
