#!/usr/bin/env python3
"""Comma offline: no connection to the internet, except GitHub (software updates), Mapbox (maps, routes, live traffic)
and - only while a model / sound download runs - Hugging Face (the "download door"). The tablet (USB), the phone
(hotspot / Bluetooth) and anything else on the local networks still work.

  python3 offline.py on | off | status | install | uninstall | boot
  python3 offline.py door open | close | status | auto on | auto off

How: routing rules (the comma's kernel has no nf_tables - iptables 1.8 answers "Could not fetch rule set generation id").
Before the normal routing: (9000) GitHub's ranges and Amazon CloudFront's (Mapbox sits behind it) use the normal
routes, (9050) the download door's addresses, (9100) every route except the default one (USB link, hotspot, Wi-Fi's
own network, loopback), (9200) everything else is unreachable at once. IPv6 the same, or switched off when the kernel
has no IPv6 rules. Comma's own servers (Microsoft), error reports (Google) and uploads stay blocked.

Remembered in /data/starview/offline; "boot" puts it back after a restart: "install" adds the sv-offline boot service
that runs it before openpilot starts. An AGNOS update removes that service (system partition): starviewd puts it back.

The download door (models/manager.py, audio/downloads.py): with offline mode on, a download job opens it - Hugging
Face's current addresses (they rotate) are let through, looked up again before every request, after every redirect and
every 20 s while the job runs. When the last job ends it closes again, or - with "close after downloads" off - stays
open until "door close" or DOOR_HOLD_S. Nothing runs while no download is going on. Standard library only: the boot
service runs this file before openpilot is up.
"""
import fcntl
import ipaddress
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

FLAG = "/data/starview/offline"
CF_CACHE = "/data/starview/offline_cloudfront"   # Amazon's latest CloudFront list, saved by "on" for the boot
DOOR_SETTINGS = "/data/starview/offline_door.json"   # {"autoClose": bool}
DOOR_STATE = "/dev/shm/starview_offline_door.json"   # {"open", "since", "until", "jobs": [{"pid", "reason", "t"}]}
# (times: monotonic, the same clock for every process; /dev/shm starts empty at every boot)
DOOR_LOCK = "/dev/shm/starview_offline_door.lock"
UNIT = "/etc/systemd/system/sv-offline.service"
SCRIPT = os.path.realpath(__file__)


def unit_text(script: str = SCRIPT) -> str:
  return f"""[Unit]
Description=StarView offline - no internet except GitHub and Mapbox ({script})
DefaultDependencies=no
After=local-fs.target
Before=network-pre.target comma.service
Wants=network-pre.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 {script} boot
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
"""


PRIO_ALLOW, PRIO_DOOR, PRIO_LOCAL, PRIO_BLOCK = 9000, 9050, 9100, 9200
LOOKUP_S = 10   # "on" never waits longer than this for the lookups
DOOR_HOLD_S = 3600   # with "close after downloads" off, the door still closes this long after the last download
DOOR_KEEPALIVE_S = 20
# GitHub (software updates): its published ranges, plus whatever its update hosts resolve to right now
GITHUB4 = ["140.82.112.0/20", "143.55.64.0/20", "192.30.252.0/22", "185.199.108.0/22"]
GITHUB_HOSTS = ["github.com", "codeload.github.com", "objects.githubusercontent.com", "raw.githubusercontent.com",
                "media.githubusercontent.com", "github-cloud.githubusercontent.com", "lfs.github.com"]
# Mapbox (maps, routes with live traffic, search, road tiles - all api.mapbox.com) sits behind Amazon CloudFront: its
# address changes every minute and by location, so CloudFront's published ranges are allowed.
MAPBOX_HOSTS = ["api.mapbox.com"]
CF_URL = "https://ip-ranges.amazonaws.com/ip-ranges.json"
# Hugging Face (StarPilot's models and sound packs): huggingface.co redirects every file to its CDN on plain Amazon
# servers (us.aws.cdn.hf.co, rotating) - only let through while a download runs
DOOR_HOSTS = ["huggingface.co", "us.aws.cdn.hf.co", "cdn-lfs.hf.co", "cdn-lfs-us-1.hf.co", "cas-bridge.xethub.hf.co",
              "transfer.xethub.hf.co"]
DOOR_DOMAINS = ("huggingface.co", "hf.co")   # redirects are only followed (and let through) inside these
# CloudFront IPv4 ranges, Amazon's list of 2026-10-28 (merged); "on" refreshes it from CF_URL when it can
CLOUDFRONT4 = """
3.10.17.128/25 3.11.53.0/24 3.29.40.64/26 3.29.40.128/25 3.29.57.0/26 3.35.130.128/25 3.101.158.0/23
3.107.43.128/25 3.107.44.0/24 3.128.93.0/24 3.134.215.0/24 3.146.232.0/22 3.147.164.0/22 3.147.244.0/22
3.160.0.0/13 3.168.0.0/14 3.172.0.0/17 3.173.0.0/16 3.174.0.0/15 3.231.2.0/25 3.234.232.224/27 3.236.48.0/23
3.236.169.192/26 13.32.0.0/15 13.35.0.0/16 13.54.63.128/26 13.59.250.0/26 13.113.196.64/26 13.113.203.0/24
13.124.199.0/24 13.134.24.0/23 13.134.94.0/23 13.203.133.0/26 13.210.67.128/26 13.224.0.0/14 13.228.69.0/24
13.233.177.192/26 13.249.0.0/16 15.158.0.0/16 15.188.184.0/24 15.207.13.128/25 15.207.213.128/25 18.64.0.0/14
18.68.0.0/16 18.154.0.0/15 18.160.0.0/15 18.164.0.0/15 18.172.0.0/15 18.175.65.0/24 18.175.66.0/23
18.192.142.0/23 18.199.68.0/22 18.199.72.0/21 18.200.212.0/23 18.216.170.128/25 18.229.220.192/26
18.230.229.0/24 18.230.230.0/25 18.238.0.0/15 18.244.0.0/15 23.91.0.0/19 23.228.212.0/23 23.228.214.0/24
23.228.220.0/22 23.228.244.0/24 23.228.246.0/23 23.228.248.0/22 23.234.192.0/18 24.110.32.0/19 24.110.128.0/17
34.195.252.0/24 34.216.51.0/25 34.223.12.224/27 34.223.80.192/26 34.226.14.0/24 35.93.168.0/22 35.93.172.0/23
35.158.136.0/24 35.162.63.192/26 35.167.191.128/26 36.103.232.0/25 36.103.232.128/26 43.218.56.64/26
43.218.56.128/25 43.218.71.0/26 44.220.194.0/23 44.220.196.0/22 44.220.200.0/22 44.222.66.0/24 44.227.178.0/24
44.234.90.252/30 44.234.108.128/25 47.129.82.0/23 47.129.84.0/24 51.44.234.0/23 51.44.236.0/22 51.74.20.0/23
51.74.22.0/24 51.74.192.0/18 52.15.127.128/26 52.46.0.0/18 52.47.139.0/24 52.52.191.128/26 52.56.127.0/25
52.57.254.0/24 52.66.194.128/26 52.78.247.128/26 52.82.128.0/19 52.84.0.0/15 52.124.128.0/17 52.199.127.192/26
52.212.248.0/26 52.220.191.0/26 52.222.128.0/17 54.182.0.0/16 54.192.0.0/16 54.230.0.0/17 54.230.128.0/18
54.230.200.0/21 54.230.208.0/20 54.230.224.0/19 54.233.255.128/26 54.239.128.0/18 54.239.192.0/19
54.240.128.0/18 56.125.46.0/24 56.125.47.0/32 56.125.48.0/24 57.182.253.0/24 57.183.42.0/25 58.254.138.0/25
58.254.138.128/26 64.252.64.0/18 64.252.128.0/18 65.8.0.0/16 65.9.0.0/17 65.9.128.0/18 70.132.0.0/18
71.152.0.0/17 99.79.169.0/24 99.84.0.0/16 99.86.0.0/16 108.138.0.0/15 108.156.0.0/14 111.13.171.128/25
111.13.185.32/27 111.13.185.64/27 116.129.226.0/25 116.129.226.128/26 118.193.97.64/26 118.193.97.128/25
119.147.182.0/25 119.147.182.128/26 120.52.12.64/26 120.52.22.96/27 120.52.39.128/27 120.52.153.192/26
120.232.236.0/25 120.232.236.128/26 120.253.240.192/26 120.253.241.160/27 120.253.245.128/26 120.253.245.192/27
130.176.0.0/17 130.176.128.0/18 130.176.192.0/19 130.176.224.0/20 143.204.0.0/16 144.220.0.0/16 180.163.57.0/25
180.163.57.128/26 204.246.164.0/22 204.246.168.0/21 204.246.176.0/20 205.251.202.0/23 205.251.204.0/22
205.251.208.0/20 205.251.249.0/24 205.251.250.0/23 205.251.252.0/23 205.251.254.0/24 216.137.32.0/19
""".split()

RUN = subprocess.run   # tests replace it


def sh(*args, check=True, stdin=None):
  r = RUN(["sudo", "-n", *args], input=stdin, capture_output=True, text=True)
  if check and r.returncode != 0:
    raise RuntimeError(f"{' '.join(args)}: {(r.stderr or r.stdout).strip()}")
  return r


def batch(fam, lines, force=False):
  """Many ip commands in one go (one sudo, one ip)."""
  if not lines:
    return
  r = RUN(["sudo", "-n", "ip", fam, *(["-force"] if force else []), "-batch", "-"], input="\n".join(lines) + "\n",
          capture_output=True, text=True)
  if r.returncode != 0 and not force:
    raise RuntimeError(f"ip {fam} -batch: {(r.stderr or r.stdout).strip()}")


def rules(fam="-4"):
  return sh("ip", fam, "rule", "show", check=False).stdout.splitlines()


# ---- CloudFront list --------------------------------------------------------------------------------------------------

def cloudfront():
  """Amazon's current list when it can be fetched (saved for the boot), else the saved one, else the built-in one."""
  try:
    with urllib.request.urlopen(CF_URL, timeout=LOOKUP_S) as r:
      d = json.load(r)
    nets = sorted({str(n) for n in ipaddress.collapse_addresses(ipaddress.ip_network(p["ip_prefix"]) for p in d["prefixes"]
                                                                  if p.get("service") == "CLOUDFRONT")})
    if len(nets) > 50:
      os.makedirs(os.path.dirname(CF_CACHE), exist_ok=True)
      with open(CF_CACHE + ".tmp", "w") as f:
        f.write("\n".join(nets) + "\n")
      os.replace(CF_CACHE + ".tmp", CF_CACHE)
      return nets
  except Exception:
    pass
  return cloudfront_saved()


def cloudfront_saved():
  try:
    with open(CF_CACHE) as f:
      nets = [str(ipaddress.ip_network(x)) for x in f.read().split()]
    if len(nets) > 50:
      return nets
  except (OSError, ValueError):
    pass
  return CLOUDFRONT4


def resolve(hosts, wait=LOOKUP_S):
  """{host: [IPv4 addresses]}, all looked up at once and never longer than `wait` (a hung lookup is left behind)."""
  out = {}

  def look(h):
    try:
      out[h] = sorted({i[4][0] for i in socket.getaddrinfo(h, 443, socket.AF_INET, socket.SOCK_STREAM)})
    except OSError:
      pass

  threads = [threading.Thread(target=look, args=(h,), daemon=True) for h in hosts]
  for t in threads:
    t.start()
  end = time.monotonic() + wait
  for t in threads:
    t.join(max(0., end - time.monotonic()))
  return dict(out)


def allowed_now():
  """GitHub + Mapbox: the published ranges plus whatever the hosts resolve to right now (if not already in them).
  With no internet route at all, the saved lists straight away."""
  if not sh("ip", "-4", "route", "show", "default", check=False).stdout.strip():
    return GITHUB4 + cloudfront_saved()
  out = {}
  t = threading.Thread(target=lambda: out.setdefault("cf", cloudfront()), daemon=True)
  t.start()
  found = resolve(GITHUB_HOSTS + MAPBOX_HOSTS)
  t.join(LOOKUP_S)
  base = GITHUB4 + out.get("cf", cloudfront_saved())
  nets = [ipaddress.ip_network(c) for c in base]
  extra = {f"{ip}/32" for addrs in found.values() for ip in addrs
           if not any(ipaddress.ip_address(ip) in n for n in nets)}
  return base + sorted(extra)


# ---- offline on / off -------------------------------------------------------------------------------------------------

def clear():
  for fam in ("-4", "-6"):
    shown = rules(fam)
    dels = [f"rule del priority {prio}" for prio in (PRIO_ALLOW, PRIO_DOOR, PRIO_LOCAL, PRIO_BLOCK)
            for line in shown if line.startswith(f"{prio}:")]
    batch(fam, dels, force=True)


def on(resolve_hosts=True):
  # look up before the door closes (not at boot: no network yet - the saved lists then)
  allowed = allowed_now() if resolve_hosts else GITHUB4 + cloudfront_saved()
  clear()
  if resolve_hosts:   # not at boot (root): /dev/shm is empty then, and a root-owned file there would lock the comma user out
    _door_write({"open": False, "jobs": []})
  v6 = "rules"
  try:
    batch("-4", [f"rule add priority {PRIO_ALLOW} to {net} lookup main" for net in allowed] +
          [f"rule add priority {PRIO_LOCAL} lookup main suppress_prefixlength 0",
           f"rule add priority {PRIO_BLOCK} unreachable"])
    try:
      sh("ip", "-6", "rule", "add", "priority", str(PRIO_LOCAL), "lookup", "main", "suppress_prefixlength", "0")
      sh("ip", "-6", "rule", "add", "priority", str(PRIO_BLOCK), "unreachable")
    except RuntimeError:
      # no IPv6 routing rules in this kernel: switch IPv6 off instead (back on with "off")
      sh("ip", "-6", "rule", "del", "priority", str(PRIO_LOCAL), check=False)
      sh("sysctl", "-q", "-w", "net.ipv6.conf.all.disable_ipv6=1")
      v6 = "sysctl"
  except RuntimeError:
    clear()                      # never leave half of it in place
    raise
  os.makedirs(os.path.dirname(FLAG), exist_ok=True)
  with open(FLAG, "w") as f:
    f.write(v6)


def off():
  clear()
  _door_write({"open": False, "jobs": []})
  try:
    with open(FLAG) as f:
      if f.read().strip() == "sysctl":
        sh("sysctl", "-q", "-w", "net.ipv6.conf.all.disable_ipv6=0", check=False)
  except OSError:
    pass
  if os.path.exists(FLAG):
    os.remove(FLAG)


def enabled() -> bool:
  """Offline mode switched on (one stat; the rules come with it, also after a restart)."""
  return os.path.exists(FLAG)


def active() -> bool:
  return any(line.startswith(f"{PRIO_BLOCK}:") for line in rules())


def boot_installed() -> bool:
  """The boot service is there and runs this file."""
  try:
    with open(UNIT) as f:
      return f.read() == unit_text()
  except OSError:
    return False


def install():
  sh("mount", "-o", "remount,rw", "/")
  try:
    sh("tee", UNIT, stdin=unit_text())
    sh("systemctl", "daemon-reload")
    sh("systemctl", "enable", "sv-offline.service")
  finally:
    sh("mount", "-o", "remount,ro", "/", check=False)


def uninstall():
  sh("systemctl", "disable", "sv-offline.service", check=False)
  sh("mount", "-o", "remount,rw", "/")
  try:
    sh("rm", "-f", UNIT)
    sh("systemctl", "daemon-reload", check=False)
  finally:
    sh("mount", "-o", "remount,ro", "/", check=False)


def boot():
  """After a restart: put it back if it was on (no lookups, nothing's up yet)."""
  if enabled() and not active():
    on(resolve_hosts=False)


# ---- the download door ------------------------------------------------------------------------------------------------

def auto_close() -> bool:
  try:
    with open(DOOR_SETTINGS) as f:
      return bool(json.load(f).get("autoClose", True))
  except (OSError, ValueError, AttributeError):
    return True


def set_auto_close(on_: bool) -> None:
  os.makedirs(os.path.dirname(DOOR_SETTINGS), exist_ok=True)
  with open(DOOR_SETTINGS + ".tmp", "w") as f:
    json.dump({"autoClose": bool(on_)}, f)
  os.replace(DOOR_SETTINGS + ".tmp", DOOR_SETTINGS)


def _door_read() -> dict:
  try:
    with open(DOOR_STATE) as f:
      d = json.load(f)
    if isinstance(d, dict) and isinstance(d.get("jobs"), list):
      return d
  except (OSError, ValueError):
    pass
  return {"open": False, "jobs": []}


def _door_write(d: dict) -> None:
  try:
    with open(DOOR_STATE + ".tmp", "w") as f:
      json.dump(d, f)
    os.replace(DOOR_STATE + ".tmp", DOOR_STATE)
  except OSError:
    pass


class _locked:
  """One door change at a time across processes (Galaxy's model manager, the comma UI's, starviewd)."""

  def __enter__(self):
    self.f = open(DOOR_LOCK, "a")
    fcntl.flock(self.f, fcntl.LOCK_EX)
    return self

  def __exit__(self, *exc):
    fcntl.flock(self.f, fcntl.LOCK_UN)
    self.f.close()


def _alive(pid) -> bool:
  try:
    os.kill(int(pid), 0)
    return True
  except (OSError, ValueError, TypeError):
    return False


def _live_jobs(d: dict) -> list:
  now = time.monotonic()
  return [j for j in d.get("jobs", []) if _alive(j.get("pid")) and now - j.get("t", 0) < 4 * 3600]


def _door_ips() -> set:
  """The door's addresses now (ip prints a /32 without the "/32")."""
  return {line.split(" to ")[1].split()[0].removesuffix("/32") for line in rules()
          if line.startswith(f"{PRIO_DOOR}:") and " to " in line}


def _close_rules() -> None:
  batch("-4", [f"rule del priority {PRIO_DOOR}" for line in rules() if line.startswith(f"{PRIO_DOOR}:")], force=True)


def door_is_open() -> bool:
  return enabled() and bool(_door_read().get("open"))


def allow_hosts(hosts, wait=5) -> int:
  """Let the door's hosts through at their current addresses (only while the door is open). Returns how many new."""
  if not door_is_open():
    return 0
  want = {ip for addrs in resolve(hosts, wait).values() for ip in addrs}
  new = sorted(want - _door_ips())
  batch("-4", [f"rule add priority {PRIO_DOOR} to {ip} lookup main" for ip in new], force=True)
  return len(new)


def door_open(reason: str) -> bool:
  """A download starts. False (and nothing done) when offline mode is off - the internet is open anyway."""
  if not enabled():
    return False
  with _locked():
    d = _door_read()
    jobs = _live_jobs(d) + [{"pid": os.getpid(), "reason": reason, "t": time.monotonic()}]
    _door_write({"open": True, "since": d.get("since") if d.get("open") else time.monotonic(), "until": None, "jobs": jobs})
  allow_hosts(DOOR_HOSTS)
  return True


def _settle(d: dict, jobs: list) -> dict:
  """After the last download: close (auto) or hold until DOOR_HOLD_S."""
  if jobs:
    return {**d, "jobs": jobs}
  if auto_close():
    _close_rules()
    return {"open": False, "jobs": []}
  return {**d, "jobs": [], "until": d.get("until") or time.monotonic() + DOOR_HOLD_S}


def door_done(reason: str) -> None:
  with _locked():
    d = _door_read()
    jobs, mine = [], False
    for j in _live_jobs(d):
      if not mine and j.get("pid") == os.getpid() and j.get("reason") == reason:
        mine = True
        continue
      jobs.append(j)
    if d.get("open"):
      _door_write(_settle(d, jobs))


def door_close() -> None:
  """"Close now" - also cuts a download that's still running."""
  with _locked():
    _close_rules()
    _door_write({"open": False, "jobs": []})


def door_expire(now=None) -> bool:
  """starviewd's 30 s check: close a held door after DOOR_HOLD_S, or one whose download died. True when it closed."""
  if not os.path.exists(DOOR_STATE):
    return False
  d = _door_read()
  if not d.get("open"):
    return False
  now = time.monotonic() if now is None else now
  with _locked():
    d = _door_read()
    jobs = _live_jobs(d)
    if not jobs and d.get("jobs"):
      d = _settle(d, [])          # its download process went away without saying so
      _door_write(d)
    if d.get("open") and not d.get("jobs") and d.get("until") and now >= d["until"]:
      _close_rules()
      d = {"open": False, "jobs": []}
      _door_write(d)
  return not d.get("open")


def door_status() -> dict:
  """{"open", "downloads": [what's downloading], "closesIn": seconds left when held open, "autoClose"}."""
  d = _door_read() if enabled() else {"open": False, "jobs": []}
  until = d.get("until") if d.get("open") else None
  return {"open": bool(d.get("open")), "downloads": [j.get("reason") for j in _live_jobs(d)],
          "closesIn": max(0, round(until - time.monotonic())) if until else None, "autoClose": auto_close()}


class download_door:
  """with download_door("models"): ... - the door is open (and kept up to date) while the block runs."""

  def __init__(self, reason: str):
    self.reason = reason
    self.stop = threading.Event()
    self.opened = False

  def _keep(self):
    while not self.stop.wait(DOOR_KEEPALIVE_S):
      try:
        allow_hosts(DOOR_HOSTS)
      except Exception:
        pass

  def __enter__(self):
    try:
      self.opened = door_open(self.reason)
    except Exception:
      self.opened = False
    if self.opened:
      threading.Thread(target=self._keep, name="offline-door", daemon=True).start()
    return self

  def __exit__(self, *exc):
    self.stop.set()
    if self.opened:
      try:
        door_done(self.reason)
      except Exception:
        pass
    return False


def _door_host(url: str) -> str | None:
  host = (urllib.parse.urlsplit(url).hostname or "").lower()
  return host if any(host == dom or host.endswith("." + dom) for dom in DOOR_DOMAINS) else None


class _DoorRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self, req, fp, code, msg, headers, newurl):
    host = _door_host(newurl)
    if host:
      allow_hosts([host])
    return super().redirect_request(req, fp, code, msg, headers, newurl)


def urlopen(url, timeout=None):
  """urllib's urlopen, with the door's host (and every redirect's) let through first while the door is open."""
  if not door_is_open():
    return urllib.request.urlopen(url, timeout=timeout)
  host = _door_host(url if isinstance(url, str) else url.full_url)
  if host:
    allow_hosts([host])
  return urllib.request.build_opener(_DoorRedirect).open(url, timeout=timeout)


# ---- command line -----------------------------------------------------------------------------------------------------

def status_text() -> str:
  saved, on_now = enabled(), active()
  passes = sum(1 for line in rules() if line.startswith(f"{PRIO_ALLOW}:"))
  door = door_status()
  text = f"offline: {'ON' if on_now else 'off'}"
  if on_now != saved:
    text += f"  (saved setting: {'on' if saved else 'off'})"
  if on_now:
    text += f"  ·  GitHub + Mapbox: {passes} ranges let through"
    text += f"  ·  download door: {'OPEN' if door['open'] else 'closed'}"
    if door["downloads"]:
      text += f" ({', '.join(door['downloads'])})"
  return text + f"  ·  boot service: {'installed' if boot_installed() else 'not installed'}"


def main(argv):
  cmd = argv[0] if argv else "status"
  if cmd == "on":
    on()
  elif cmd == "off":
    off()
  elif cmd == "install":
    install()
    print("boot service installed: offline comes back by itself after a restart (when it's on)")
  elif cmd == "uninstall":
    uninstall()
    print("boot service removed")
  elif cmd == "boot":
    boot()
  elif cmd == "door":
    sub = argv[1] if len(argv) > 1 else "status"
    if sub == "open":
      print("door open" if door_open("command line") else "offline mode is off - nothing to open")
    elif sub == "close":
      door_close()
    elif sub == "auto" and len(argv) > 2 and argv[2] in ("on", "off"):
      set_auto_close(argv[2] == "on")
    elif sub != "status":
      sys.exit(__doc__)
    print(json.dumps(door_status()))
    return
  elif cmd != "status":
    sys.exit(__doc__)
  print(status_text())


if __name__ == "__main__":
  main(sys.argv[1:])
