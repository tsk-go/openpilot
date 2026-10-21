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
  assert r.feed_rtcm(b"\xd3\x00\x04RTCMcrc")["ok"]
  r.step(timeout=0.01)
  time.sleep(0.05)
  assert b"\xd3\x00\x04RTCMcrc" in os.read(master, 4096)
  assert r.status()["rtcmBytes"] == 10 and r.status()["rtcmAgeS"] == 0.0
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


def esf_status_payload(i1=0, i2=0, mode=0, sensors=()):
  p = bytearray(16 + 4 * len(sensors))
  p[4], p[5], p[6], p[12], p[15] = 2, i1, i2, mode, len(sensors)
  for k, sens in enumerate(sensors):
    p[16 + 4 * k:20 + 4 * k] = bytes(sens)
  return bytes(p)


def mon_ver_payload(sw="EXT CORE 1.00 (a1c2e4)", exts=("ROM BASE 0x118B2060", "FWVER=HPS 1.30", "PROTVER=33.30", "MOD=ZED-F9R")):
  p = sw.encode().ljust(30, b"\0") + b"00190000".ljust(10, b"\0")
  return p + b"".join(e.encode().ljust(30, b"\0") for e in exts)


def test_fusion_steps_and_sensors_in_plain_words():
  st = rtk.parse_esf_status(esf_status_payload(
    i1=2 | (1 << 2) | (2 << 5), i2=2, mode=1,
    sensors=[(5 | 0x40 | 0x80, 3, 50, 0), (16 | 0x80, 1, 50, 0), (11 | 0x40 | 0x80, 2 | (3 << 2), 10, 4 | 8)]))
  assert st["fusion"] == "on" and st["imuInit"] == "done" and st["insInit"] == "done"
  assert st["mountInit"] == "initializing" and st["speedInit"] == "done"
  assert st["sensors"][0] == {"type": "gyro z", "used": True, "ready": True, "calib": "calibrated", "hz": 50, "faults": []}
  assert st["sensors"][1]["type"] == "accel x" and st["sensors"][1]["calib"] == "calibrating" and not st["sensors"][1]["used"]
  assert st["sensors"][2]["type"] == "speed" and st["sensors"][2]["faults"] == ["missing measurements", "noisy measurements"]
  # the IMU at 0 Hz, nothing started: what HPS 1.00 on an F9R-03B looked like
  bare = rtk.parse_esf_status(esf_status_payload(i2=1))
  assert bare["fusion"] == "initializing" and bare["imuInit"] == "initializing" and bare["sensors"] == []


def test_firmware_and_module():
  assert rtk.parse_mon_ver(mon_ver_payload()) == {"firmware": "HPS 1.30", "module": "ZED-F9R"}
  assert rtk.parse_mon_ver(mon_ver_payload(exts=()))["firmware"] == "EXT CORE 1.00 (a1c2e4)"
  assert rtk.parse_mon_ver(b"short") is None


def test_speed_message_layout():
  frame = rtk.esf_speed(13.456, 1_234_567)
  assert frame[:6] == b"\xb5\x62\x10\x02\x0c\x00"
  tag, flags, ident, data = struct.unpack_from("<IHHI", frame, 6)
  assert tag == 1_234_567 and flags >> 11 == 1 and ident == 0
  assert data >> 24 == 11 and data & 0xFFFFFF == 13_456
  back = struct.unpack_from("<I", rtk.esf_speed(-1.5, 0), 6 + 8)[0]
  assert back >> 24 == 11 and (back & 0xFFFFFF) - (1 << 24) == -1500    # backing up: negative, 24-bit two's complement
  assert rtk.restart("cold")[6:10] == b"\xff\xff\x02\x00" and rtk.restart("hot")[6:10] == b"\x00\x00\x02\x00"
  assert rtk.FACTORY[6:19] == struct.pack("<IIIB", 0xFFFF, 0, 0xFFFF, 0x17)
  assert rtk.SAVE[6:10] == b"\x00\x07\x00\x00" and rtk.SETUP[6:10] == b"\x00\x01\x00\x00"
  assert len(rtk.SAVE_FRAMES) == 1 + len(rtk.PORTS_OFF) and rtk.valset_ram(((0x10740002, 0, 1),)) in rtk.SETUP   # UART1 NMEA off
  assert rtk.REALIGN == b"\xb5\x62\x10\x13\x00\x00\x23\x79"


def test_only_whole_rtcm_frames_go_out():
  one = b"\xd3\x00\x02ab123"
  assert rtk.rtcm_whole(one + one) == 16
  assert rtk.rtcm_whole(one + one[:4]) == 8                # half a frame waits for the next chunk
  assert rtk.rtcm_whole(b"zz" + one + b"\xd3\x00") == 10   # junk passes, a frame head waits
  assert rtk.rtcm_whole(b"") == 0


def _reads(master):
  time.sleep(0.03)
  try:
    return os.read(master, 65536)
  except BlockingIOError:
    return b""


def _receiver(tmp_path, now, **kw):
  master, slave = os.openpty()
  os.set_blocking(master, False)
  link = tmp_path / "usb-u-blox_AG_-_www.u-blox.com_u-blox_GNSS_receiver-if00"
  link.symlink_to(os.ttyname(slave))
  r = rtk.Rtk(port_glob=str(tmp_path / "*u-blox*"), clock=lambda: now[0], handoff_path=tmp_path / "handoff.json",
              settings_path=tmp_path / "rtk.json", **kw)
  r.step(timeout=0.01)
  sent = _reads(master)
  assert sent.startswith(rtk.SETUP + rtk.MON_VER)
  return master, r, sent


def test_tablet_tools_wait_for_the_receivers_answer(tmp_path):
  now = [100.0]
  master, r, _ = _receiver(tmp_path, now)
  assert r.action("bogus")["ok"] is False
  assert r.action("cold", moving=True) == {"ok": False, "error": "Stop the car first"}
  assert r.action("factory", moving=True)["ok"] is False
  # a tool waits for the RTCM frame being written to finish
  r.feed_rtcm(b"\xd3\x00\x02ab1")                       # the tablet's chunk ends mid-frame
  assert r.action("realign") == {"ok": True}
  r.step(timeout=0.01)
  sent = _reads(master)
  assert rtk.REALIGN in sent and b"\xd3" not in sent
  assert r.status()["action"] == {"op": "realign", "state": "sent", "ageS": 0.0}
  r.feed_rtcm(b"23\xd3\x00\x01z")
  r.step(timeout=0.01)
  assert _reads(master) == b"\xd3\x00\x02ab123"           # only the whole frame; the next one waits too
  os.write(master, rtk.ubx(0x05, 0x01, b"\x10\x13"))
  r.step(timeout=0.05)
  assert r.status()["action"]["state"] == "done"
  # factory: cleared, ours written back to RAM + BBR + flash, firmware asked again
  r.action("factory")
  r.step(timeout=0.01)
  sent = _reads(master)
  assert sent.startswith(rtk.FACTORY + rtk.SAVE + rtk.MON_VER)
  os.write(master, rtk.ubx(0x05, 0x01, b"\x06\x09") + rtk.ubx(0x0A, 0x04, mon_ver_payload()))
  r.step(timeout=0.05)
  st = r.status()
  assert st["action"]["state"] == "sent" and st["firmware"] == "HPS 1.30" and st["module"] == "ZED-F9R"
  os.write(master, rtk.ubx(0x05, 0x01, b"\x06\x8a") * len(rtk.SAVE_FRAMES))   # each VALSET answers on its own
  r.step(timeout=0.05)
  assert r.status()["action"]["state"] == "done"
  r.action("save")
  r.step(timeout=0.01)
  assert rtk.SAVE in _reads(master)
  os.write(master, rtk.ubx(0x05, 0x00, b"\x06\x8a"))
  r.step(timeout=0.05)
  assert r.status()["action"]["state"] == "refused"
  r.action("warm")
  r.step(timeout=0.01)
  assert rtk.restart("warm") in _reads(master)
  assert r.status()["action"]["state"] == "done"          # a restart has no answer to wait for
  r.action("save")
  now[0] += 3.5
  assert r.status()["action"]["state"] == "no answer"
  os.close(master)


def test_speed_feed(tmp_path):
  now = [100.0]
  mono = [50_000_000_000]
  master, r, sent = _receiver(tmp_path, now, mono_ns=lambda: mono[0])
  assert rtk.SPEED_ON not in sent
  assert r.status()["speedFeed"] == {"on": False} and not r.wants_speed()
  assert r.action("speed_on") == {"ok": True}
  assert json.loads((tmp_path / "rtk.json").read_text()) == {"speedFeed": True}
  r.step(timeout=0.01)
  assert rtk.SPEED_ON in _reads(master)
  for _ in range(25):                                     # 2.5 s of carState at 10 Hz, sent as it comes
    assert r.wants_speed()
    r.speed(20.0, False, mono[0] - 12_000_000)
    assert not r.wants_speed()                            # at most 10 a second
    r.step(timeout=0.01)
    sent = _reads(master)
    assert rtk.esf_speed(20.0, (mono[0] - 12_000_000) // 1_000_000) in sent
    now[0] += 0.1
    mono[0] += 100_000_000
  feed = r.status()["speedFeed"]
  assert feed["on"] and 9.5 <= feed["hz"] <= 10.5 and feed["delayMs"] == 12
  r.speed(1.2, True, mono[0])                             # reverse: negative
  r.step(timeout=0.01)
  assert rtk.esf_speed(-1.2, mono[0] // 1_000_000) in _reads(master)
  r.speed(3.0, False, mono[0])
  now[0] += 0.2                                           # stale by the time it could go out: dropped, never late
  r.step(timeout=0.01)
  assert b"\x10\x02" not in _reads(master)
  now[0] += 3.1
  assert r.status()["speedFeed"]["hz"] == 0.0             # the tablet (and its carState) went away
  assert rtk.Rtk(port_glob="/nonexistent/*", settings_path=tmp_path / "rtk.json").speed_on   # kept across restarts
  assert r.action("speed_off")["ok"] and json.loads((tmp_path / "rtk.json").read_text()) == {"speedFeed": False}
  r.step(timeout=0.01)
  assert rtk.SPEED_OFF in _reads(master) and not r.wants_speed()
  os.close(master)


def test_reconnect_sends_the_speed_settings_again(tmp_path):
  (tmp_path / "rtk.json").write_text('{"speedFeed": true}')
  now = [100.0]
  master, r, sent = _receiver(tmp_path, now)
  assert sent == rtk.SETUP + rtk.MON_VER + rtk.SPEED_ON + rtk.POLLS
  os.close(master)


def test_tablet_rtk_tools_action(monkeypatch):
  from openpilot.starpilot.system.starview import starviewd
  hub = starviewd.Hub.__new__(starviewd.Hub)
  got = []
  hub.rtk = type("R", (), {"action": lambda self, op, moving=False: got.append((op, moving)) or {"ok": True}})()
  hub.last_raw = {}
  assert hub.control({"action": "rtk_action", "op": "realign"}) == {"ok": True}
  assert got == [("realign", False)]


def test_calibration_timeline_and_what_the_drive_gave_it():
  clock = [1000.0]
  cal = rtk.Calibration(clock=lambda: clock[0])
  t = 0.0
  heading = 0.0

  def drive(seconds, speed, turn_rate=0.0):
    nonlocal t, heading
    for _ in range(int(seconds * 10)):
      t += 0.1
      clock[0] += 0.1
      heading = (heading + turn_rate * 0.1) % 360
      cal.pvt({"fixType": "3D", "speedMs": speed, "headingDeg": heading, "carHeadingDeg": None}, t)

  cal.esf({"fusion": "initializing", "imuInit": "initializing", "insInit": "off", "mountInit": "off", "speedInit": "off", "sensors": []})
  drive(25, 0.0)                                   # the stop with the engine on
  cal.esf({"fusion": "initializing", "imuInit": "done", "insInit": "off", "mountInit": "initializing", "speedInit": "off", "sensors": []})
  drive(30, 12.0)                                  # straight at 27 mph
  drive(9, 9.0, turn_rate=10.0)                    # a 90 degree right at 20 mph
  drive(10, 12.0)
  drive(9, 5.0, turn_rate=-10.0)                   # a 90 degree left at 11 mph
  drive(5, 1.0, turn_rate=40.0)                    # crawling in a lot: not a road turn
  cal.alg({"mount": "learning heading"})
  cal.alg({"mount": "coarse"})
  st = cal.status()
  d = st["drive"]
  assert (d["right"], d["left"], d["rightFast"], d["leftFast"]) == (1, 1, 1, 0)
  assert d["longestStillS"] == 25 and 45 <= d["fastS"] <= 51 and d["stillNowS"] == 0
  assert [(e["k"], e["from"], e["to"]) for e in st["events"]] == [
    ("imuInit", "initializing", "done"), ("mountInit", "off", "initializing"), ("mount", "learning heading", "coarse")]
  assert abs(st["events"][0]["agoS"] - 63.0) < 0.05 and abs(d["sinceAgoS"] - 88) <= 1   # 25 s stop, then 63 s more
  # the speed sensor's health over the last minute; recalibrating starts the drive counters over
  for bad in (True, False, False, False):
    cal.esf({"sensors": [{"type": "speed", "calib": "calibrating", "faults": ["bad measurements"] if bad else []}]})
  assert cal.status()["speedBadPct"] == 25
  cal.tool("realign")
  assert cal.status()["drive"]["right"] == 0 and cal.status()["events"][-1]["to"] == "realign"


def test_mount_angles_and_errors():
  p = bytearray(16)
  p[5], p[6] = 1 | (2 << 1), 2
  struct.pack_into("<Ihh", p, 8, 27760, 200, -2660)
  alg = rtk.parse_esf_alg(bytes(p))
  assert alg == {"mountAuto": True, "mount": "learning heading", "mountYawDeg": 277.6, "mountPitchDeg": 2.0, "mountRollDeg": -26.6,
                 "mountErrors": ["yaw"]}


def test_fast_fix_for_the_tablet():
  now = [100.0]
  r = rtk.Rtk(port_glob="/nonexistent/*", clock=lambda: now[0])
  assert r.fast() is None
  r.handle(0x01, 0x07, pvt_payload(carr=2, hacc_mm=20))
  f = r.fast()
  assert f["type"] == "rtk" and f["seq"] == 1 and f["rtk"] == "fixed" and f["hAccM"] == 0.02 and f["ageMs"] == 0
  now[0] += 0.05
  r.handle(0x01, 0x07, pvt_payload())
  assert r.fast()["seq"] == 2 and r.fast()["ageMs"] == 0
  now[0] += 2.5
  assert r.fast() is None                                  # stale: nothing sent
  r.handle(0x01, 0x07, pvt_payload(fix=0, ok=False))
  assert r.fast() is None                                  # no fix
