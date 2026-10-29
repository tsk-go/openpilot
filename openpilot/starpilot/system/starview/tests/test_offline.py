import io
import json
import os
import urllib.request
from types import SimpleNamespace

import pytest

from openpilot.starpilot.system.starview import offline


class FakeIp:
  """The bits of `sudo ip` / sysctl / mount / systemctl offline.py uses, kept as a rule list."""

  def __init__(self):
    self.rules = {"-4": [], "-6": []}
    self.default_route = True
    self.calls = []

  def __call__(self, argv, **kw):
    stdin = kw.get("input")
    assert argv[:2] == ["sudo", "-n"]
    cmd = argv[2:]
    self.calls.append(cmd)
    out = ""
    if cmd[0] == "ip" and "-batch" in cmd:
      fam = cmd[1]
      for line in (stdin or "").splitlines():
        self._rule(fam, line.split())
    elif cmd[:4] in (["ip", "-4", "rule", "show"], ["ip", "-6", "rule", "show"]):
      out = "\n".join(f"{p}:\tfrom all {rest}" for p, rest in self.rules[cmd[1]]) + "\n"
    elif cmd[:3] == ["ip", "-4", "route"]:
      out = "default via 10.0.0.1 dev wlan0\n" if self.default_route else ""
    elif cmd[0] == "ip" and cmd[2] == "rule":
      self._rule(cmd[1], cmd[2:])
    return SimpleNamespace(returncode=0, stdout=out, stderr="")

  def _rule(self, fam, words):
    assert words[0] == "rule"
    prio = int(words[words.index("priority") + 1])
    rest = " ".join(words[words.index("priority") + 2:])
    if words[1] == "add":
      self.rules[fam].append((prio, rest))
    elif words[1] == "del":
      for i, (p, _) in enumerate(self.rules[fam]):
        if p == prio:
          del self.rules[fam][i]
          break

  def prio(self, p, fam="-4"):
    return [rest for q, rest in self.rules[fam] if q == p]


@pytest.fixture
def ip(tmp_path, monkeypatch):
  fake = FakeIp()
  monkeypatch.setattr(offline, "RUN", fake)
  monkeypatch.setattr(offline, "FLAG", str(tmp_path / "offline"))
  monkeypatch.setattr(offline, "CF_CACHE", str(tmp_path / "offline_cloudfront"))
  monkeypatch.setattr(offline, "DOOR_SETTINGS", str(tmp_path / "offline_door.json"))
  monkeypatch.setattr(offline, "DOOR_STATE", str(tmp_path / "door_state.json"))
  monkeypatch.setattr(offline, "DOOR_LOCK", str(tmp_path / "door.lock"))
  monkeypatch.setattr(offline, "UNIT", str(tmp_path / "sv-offline.service"))
  monkeypatch.setattr(offline, "cloudfront", lambda: ["13.32.0.0/15"])
  addrs = {"github.com": ["140.82.112.3"], "api.mapbox.com": ["13.32.1.1"], "huggingface.co": ["3.167.112.38"],
           "us.aws.cdn.hf.co": ["98.90.123.60", "32.193.91.216"]}
  monkeypatch.setattr(offline, "resolve", lambda hosts, wait=10: {h: addrs[h] for h in hosts if h in addrs})
  fake.addrs = addrs
  return fake


def test_on_lets_github_mapbox_and_the_local_networks_through_and_blocks_the_rest(ip):
  offline.on()
  assert "to 140.82.112.0/20 lookup main" in ip.prio(9000)
  assert "to 13.32.0.0/15 lookup main" in ip.prio(9000)
  assert ip.prio(9100) == ["lookup main suppress_prefixlength 0"]
  assert ip.prio(9200) == ["unreachable"]
  assert ip.prio(9200, "-6") == ["unreachable"]
  assert offline.enabled() and offline.active()
  assert not offline.door_status()["open"]
  offline.on()                                           # twice: same rules, not doubled
  assert ip.prio(9200) == ["unreachable"]
  offline.off()
  assert ip.rules == {"-4": [], "-6": []} and not offline.enabled()


def test_the_door_opens_only_with_offline_on(ip):
  assert offline.door_open("models") is False           # internet open anyway
  assert ip.prio(9050) == []
  offline.on()
  assert offline.door_open("models") is True
  assert sorted(ip.prio(9050)) == ["to 3.167.112.38 lookup main", "to 32.193.91.216 lookup main",
                                   "to 98.90.123.60 lookup main"]
  assert offline.door_status()["downloads"] == ["models"]


def test_new_addresses_are_added_once_and_the_door_closes_after_the_download(ip):
  offline.on()
  offline.door_open("models")
  ip.addrs["us.aws.cdn.hf.co"] = ["98.90.123.60", "100.50.185.240"]    # the CDN rotated
  assert offline.allow_hosts(offline.DOOR_HOSTS) == 1
  assert offline.allow_hosts(offline.DOOR_HOSTS) == 0
  offline.door_done("models")
  assert ip.prio(9050) == [] and not offline.door_status()["open"]
  assert offline.allow_hosts(offline.DOOR_HOSTS) == 0    # closed: nothing let through any more
  assert ip.prio(9200) == ["unreachable"]                 # the rest of offline mode untouched


def test_with_auto_close_off_it_stays_open_until_closed_or_an_hour(ip, monkeypatch):
  offline.on()
  offline.set_auto_close(False)
  offline.door_open("models")
  offline.door_done("models")
  st = offline.door_status()
  assert st["open"] and st["autoClose"] is False and 3590 <= st["closesIn"] <= 3600
  assert ip.prio(9050)
  assert offline.door_expire() is False
  t = offline.time.monotonic()
  assert offline.door_expire(now=t + 3601) is True
  assert ip.prio(9050) == [] and not offline.door_status()["open"]
  offline.door_open("sounds")
  offline.door_close()                                    # "Close now"
  assert ip.prio(9050) == [] and not offline.door_status()["open"]


def test_two_downloads_keep_it_open_until_both_end(ip):
  offline.on()
  offline.door_open("models")
  offline.door_open("sounds")
  offline.door_done("models")
  assert offline.door_status()["open"] and offline.door_status()["downloads"] == ["sounds"]
  offline.door_done("sounds")
  assert not offline.door_status()["open"]


def test_a_download_that_died_does_not_keep_it_open(ip):
  offline.on()
  offline.door_open("models")
  d = json.load(open(offline.DOOR_STATE))
  d["jobs"][0]["pid"] = 2 ** 22 + 12345                    # no such process
  json.dump(d, open(offline.DOOR_STATE, "w"))
  assert offline.door_expire() is True
  assert ip.prio(9050) == []


def test_off_and_a_restart_close_the_door(ip):
  offline.on()
  offline.door_open("models")
  offline.off()
  assert ip.rules["-4"] == [] and not offline.door_status()["open"]
  offline.on()
  offline.door_open("models")
  offline.clear()                                         # what a restart looks like: rules and /dev/shm gone, flag kept
  os.remove(offline.DOOR_STATE)
  ip.default_route = False
  offline.boot()
  assert ip.prio(9050) == [] and ip.prio(9200) == ["unreachable"] and not offline.door_status()["open"]
  assert not os.path.exists(offline.DOOR_STATE)          # boot runs as root: leaves /dev/shm to the comma user


def test_download_door_context(ip, monkeypatch):
  offline.on()
  with offline.download_door("models") as door:
    assert door.opened and offline.door_status()["open"]
  assert not offline.door_status()["open"]
  offline.off()
  with offline.download_door("models") as door:          # offline off: nothing to do
    assert not door.opened


def test_urlopen_lets_the_host_and_its_redirect_through(ip, monkeypatch):
  seen = []
  monkeypatch.setattr(offline, "allow_hosts", lambda hosts, wait=5: seen.append(list(hosts)) or 0)

  class Opener:
    def __init__(self, handler):
      self.handler = handler

    def open(self, url, timeout=None):
      req = urllib.request.Request(url)
      self.handler().redirect_request(req, io.BytesIO(), 302, "Found", {}, "https://us.aws.cdn.hf.co/xet/abc")
      return io.BytesIO(b"ok")

  monkeypatch.setattr(offline.urllib.request, "build_opener", lambda handler: Opener(handler))
  monkeypatch.setattr(offline.urllib.request, "urlopen", lambda url, timeout=None: io.BytesIO(b"plain"))
  url = "https://huggingface.co/buckets/StarPilot-Driving/StarPilot-Resources/resolve/manifests/x.json"
  assert offline.urlopen(url, timeout=5).read() == b"plain"           # door closed: plain urllib
  offline.on()
  offline.door_open("models")
  assert offline.urlopen(url, timeout=5).read() == b"ok"
  assert seen[-2:] == [["huggingface.co"], ["us.aws.cdn.hf.co"]]


def test_only_hugging_face_goes_through_the_door():
  assert offline._door_host("https://huggingface.co/x") == "huggingface.co"
  assert offline._door_host("https://us.aws.cdn.hf.co/x") == "us.aws.cdn.hf.co"
  assert offline._door_host("https://api.commadotai.com/x") is None
  assert offline._door_host("https://evilhf.co/x") is None


def test_boot_service_runs_this_file(ip):
  assert not offline.boot_installed()
  offline.install()
  open(offline.UNIT, "w").write(offline.unit_text())     # tee went to the fake
  assert offline.boot_installed()
  assert f"ExecStart=/usr/bin/python3 {offline.SCRIPT} boot" in offline.unit_text()
  open(offline.UNIT, "w").write(offline.unit_text("/data/tools/offline.py"))
  assert not offline.boot_installed()                    # the old /data/tools copy: starviewd reinstalls
  assert ["systemctl", "enable", "sv-offline.service"] in ip.calls
  assert os.path.basename(offline.SCRIPT) == "offline.py"
