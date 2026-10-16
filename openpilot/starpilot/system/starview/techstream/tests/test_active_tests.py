"""Active Tests: request building (against the rules in kaikozlov/toyota-diagnostics executor.py), the one-at-a-time
runner (extended session, TesterPresent, stop on release / silence / time limit), the API, and the Toyota settings merge."""
import pytest

from openpilot.starpilot.system.starview.techstream import active_tests, api, catalog
from openpilot.starpilot.system.starview.techstream.link import DiagLink, EcuRejectedError

from .fakes import FakeEcu, FakePanda

HORN = {"ecu": "750/40", "id": "dX", "name": "Vehicle Horn", "kind": "direct", "did": "2802", "mode": 0, "bitStart": 0, "bitEnd": 7,
        "start": "2f280203", "stop": "2f280200", "records": [{"bit": 1, "offset": 0, "length": 1, "mode": 0}],
        "choices": [{"label": "OFF", "value": 0}, {"label": "ON", "value": 1}],
        "physical": {"mul": 1, "div": 1, "offset": 0, "decimal_point_count": 0, "unit": None}}
SPEEDO = {"ecu": "7C0", "id": "dY", "name": "Speedometer Operation", "kind": "direct", "did": "2801", "mode": 1, "bitStart": 8,
          "bitEnd": 15, "start": "2f280103", "stop": "2f280100", "records": [{"bit": 0, "offset": 0, "length": 0, "mode": 1}],
          "choices": [{"label": "OFF", "value": 0}, {"label": "40", "value": 64}],
          "physical": {"mul": 1, "div": 1, "offset": 0, "decimal_point_count": 0, "unit": None}}
PSD = {"ecu": "750/A7", "id": "rZ", "name": "PSD Motor (Open)", "kind": "routine", "start": "3101110100", "stop": "31021101"}


class TestRequests:
  def test_mode0_horn(self):
    start, stop = active_tests.direct_requests(HORN, 1, "ON")
    assert start == bytes.fromhex("2f2802030180") and stop == bytes.fromhex("2f28020080")

  def test_mode1_speedometer(self):
    start, stop = active_tests.direct_requests(SPEEDO, 4, "40")
    assert start == bytes.fromhex("2f28010300400000") and stop == bytes.fromhex("2f28010000ff")

  def test_bad_choice_and_short_block(self):
    with pytest.raises(active_tests.TestError):
      active_tests.direct_requests(HORN, 1, "LOUD")
    with pytest.raises(active_tests.TestError):
      active_tests.direct_requests(SPEEDO, 1, "40")

  def test_every_shipped_test_builds(self):
    for t in active_tests.load()["tests"]:
      if t["kind"] != "direct":
        assert t["start"][:4] == "3101"
        continue
      length = t["bitEnd"] // 8 + 1
      for c in t["choices"]:
        start, stop = active_tests.direct_requests(t, length, c["label"])
        assert start[:3] == bytes.fromhex("2f") + bytes.fromhex(t["did"]) and start[3] == 3 and stop[3] == 0


class Clock:
  def __init__(self):
    self.t = 100.0

  def __call__(self):
    return self.t


def car(extra=None):
  """A Main Body that knows the horn (DID 2802, 1 byte) and answers sessions / TesterPresent."""
  def handle(req: bytes):
    if req[:1] == b"\x10":
      return bytes([0x50, req[1]])
    if req == b"\x3e\x00":
      return b"\x7e\x00"
    if req == bytes.fromhex("222802"):
      return bytes.fromhex("62280200")
    if req[:3] == bytes.fromhex("2f2802"):
      return bytes.fromhex("6f2802") + req[3:5]
    return (extra or {}).get(req, b"\x7f" + req[:1] + b"\x31")
  ecu = FakeEcu(handler=handle)
  panda = FakePanda({(0x750, 0x40): ecu})
  link = DiagLink(panda, elm327_mode=3, heartbeat_thread=False, timeout=0.02, pending_timeout=0.1)
  return ecu, link


class TestRunner:
  def make(self):
    ecu, link = car()
    clock = Clock()
    runner = active_tests.Runner(lambda fn: fn(link), clock=clock)
    runner._loop = lambda: None          # tick by hand
    return ecu, runner, clock

  def test_start_hold_stop(self):
    ecu, runner, clock = self.make()
    st = runner.start(HORN, "ON")
    assert st["active"]["name"] == "Vehicle Horn"
    assert ecu.requests == [b"\x10\x03", bytes.fromhex("222802"), bytes.fromhex("2f2802030180")]
    clock.t += 1.6
    runner.ping()
    runner.tick()
    assert ecu.requests[-1] == b"\x3e\x00"
    runner.stop()
    assert ecu.requests[-2:] == [bytes.fromhex("2f28020080"), b"\x10\x01"] and runner.active is None

  def test_page_silence_stops_it(self):
    ecu, runner, clock = self.make()
    runner.start(HORN, "ON")
    clock.t += active_tests.PING_TIMEOUT_S + 0.1
    runner.tick()
    assert runner.active is None and "checking in" in runner.status()["error"]
    assert bytes.fromhex("2f28020080") in ecu.requests

  def test_time_limit(self):
    _, runner, clock = self.make()
    runner.start(HORN, "ON")
    for _ in range(int(active_tests.MAX_RUN_S) + 2):
      clock.t += 1.0
      runner.ping()
      runner.tick()
    assert runner.active is None

  def test_starting_another_stops_the_first(self):
    ecu, runner, _ = self.make()
    runner.start(HORN, "ON")
    runner.start(HORN, "OFF")
    assert ecu.requests.count(bytes.fromhex("2f28020080")) == 1 and runner.active["label"] == "OFF"

  def test_module_without_it(self):
    ecu, runner, _ = self.make()
    with pytest.raises(EcuRejectedError):
      runner.start(SPEEDO | {"ecu": "750/40", "did": "2899"}, "40")
    assert runner.active is None and ecu.requests[-1] == b"\x10\x01"


class TestCheck:
  def mb(self):
    return [t for t in active_tests.load()["tests"] if t["ecu"] == "750/40"]

  def test_per_did_reads(self):
    _, link = car()                     # no bitmap: only the horn DID (2802) reads
    r = active_tests.check(link, "750/40")
    direct = [t["id"] for t in self.mb() if t["kind"] == "direct" and t["id"] in r["have"]]
    horn = next(t for t in self.mb() if t["name"] == "Vehicle Horn")
    assert r["status"] == "ok" and direct == [horn["id"]]
    assert all(t["id"] in r["have"] for t in self.mb() if t["kind"] == "routine")

  def test_bitmap(self):
    bitmap = bytearray(32)
    bitmap[0] |= 0x40                   # DID 2802
    _, link = car({bytes.fromhex("222800"): bytes.fromhex("622800") + bytes(bitmap)})
    r = active_tests.check(link, "750/40")
    horn = next(t for t in self.mb() if t["name"] == "Vehicle Horn")
    assert [i for i in r["have"] if i.startswith("d")] == [horn["id"]]

  def test_offline(self):
    link = DiagLink(FakePanda({}), elm327_mode=3, heartbeat_thread=False, timeout=0.02, pending_timeout=0.1)
    assert active_tests.check(link, "750/40") == {"ecu": "750/40", "status": "offline", "have": []}


class FakeSession:
  def __init__(self, link):
    self.link = link

  def run(self, op):
    return op(self.link)


class TestApi:
  def test_listing_and_errors(self, monkeypatch, tmp_path):
    _, link = car()
    a = api.TechStreamApi(FakeSession(link), str(tmp_path))
    a.tests._loop = lambda: None
    assert a.tests_check({"ecu": "nope"})[0] == 404
    assert a.tests_check({"ecu": "750/40"})[1]["status"] == "ok"
    status, body = a.tests_list()
    assert status == 200 and body["tests"] and "start" not in body["tests"][0]
    assert a.test_start({"ecu": "750/40", "id": "nope"})[0] == 404
    horn = next(t for t in active_tests.load()["tests"] if t["ecu"] == "750/40" and t["name"] == "Vehicle Horn")
    status, body = a.test_start({"ecu": "750/40", "id": horn["id"], "choice": "ON"})
    assert status == 200 and body["active"]["name"] == "Vehicle Horn"
    assert a.test_stop({})[1]["active"] is None
    fog = next(t for t in active_tests.load()["tests"] if t["ecu"] == "750/40" and t["name"] == "Rear Fog Light")
    status, body = a.test_start({"ecu": "750/40", "id": fog["id"], "choice": fog["choices"][-1]["label"]})
    assert status == 404 and "doesn't have this test" in body["error"]


class TestToyotaSettings:
  @pytest.mark.toyota_extras
  def test_merged_into_catalog(self):
    data = catalog.load_sienna()
    keys = [s["key"] for s in data["settings"]]
    ecus = {e["id"] for e in data["ecus"]}
    cats = {c["id"] for c in data["categories"]}
    toyota = [s for s in data["settings"] if s.get("source") == "toyota"]
    assert len(keys) == len(set(keys)) and len(toyota) > 500
    assert all(s["ecu"] in ecus and s["category"] in cats and s["unverified"] for s in toyota)
    assert all(s["options"] or s["numeric"] for s in toyota)
    # the fob window-close item Toyota defines for this Main Body is already in toyopilot's list (not duplicated)
    assert not any(s["ecu"] == "750/40" and s["did"] == "224C" for s in toyota)

  @pytest.mark.toyota_extras
  def test_scan_lists_only_what_the_module_has(self, tmp_path):
    from openpilot.starpilot.system.starview.techstream import customization
    from .fakes import PROBE, FakeUdsEcu
    body = FakeUdsEcu.from_probe(PROBE, "750", "40")
    link = DiagLink(FakePanda({(0x750, 0x40): body}), elm327_mode=3, heartbeat_thread=False, timeout=0.02, pending_timeout=0.1)
    ecu = catalog.ecu("750/40")
    settings = [s for s in catalog.load_sienna()["settings"] if s["ecu"] == "750/40"]
    report = customization.scan_ecu(link, ecu, settings)
    listed = {i["key"] for i in report["items"]}
    toyota = [s for s in settings if s.get("source") == "toyota"]
    assert report["status"] == "ok" and len(settings) > 300
    # every listed Toyota item is one whose DID the (recorded) module really has
    for s in toyota:
      if s["key"] in listed:
        assert int(s["did"], 16) in body.memory
