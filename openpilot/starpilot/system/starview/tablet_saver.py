"""Tablet battery saver: the comma quiets the tablet over adb, StarView itself keeps running exactly as before.

The tablet's StarView switch (QUICK › Battery saver, the SAVER pill, or "battery saver on" by voice) sends
{"action": "tablet_saver", "on": true|false}. Uses the adb pairing of auto-tethering (/data/starview/adbhome).

On:
  * every other app stopped (am force-stop), cached background processes killed (am kill-all)
  * those apps kept from running in the background: app-op RUN_ANY_IN_BACKGROUND=ignore and the "restricted" standby
    bucket (no jobs, alarms, syncs) - the user's own apps plus the big preinstalled ones (YouTube, Chrome, Photos,
    Gmail, Play Store...); the core of Android and Google Play services are left alone
  * Wi-Fi and Bluetooth "scanning always on" off (the tablet's location scans; its Wi-Fi itself stays connected)
  * StarView on Android's battery-optimisation allow list, so the quieter tablet never throttles it
Never touched: StarView, the keyboard, the home screen, the speech / voice-typing services, Termius, anything listed in
/data/starview/saver_keep (one package per line), Wi-Fi, Bluetooth, the screen.
Off: every app and setting back to what it was (kept in /data/starview/tablet_saver.json, so a comma reboot in between
doesn't lose it). While on, the tablet asks again at every connection: apps installed or opened since are quieted too.
"""
import json
import os
import re
import time

STATE = "/data/starview/tablet_saver.json"
KEEP_FILE = "/data/starview/saver_keep"
OURS = "com.starpilot.starview"
ALWAYS_KEEP = {OURS, "com.server.auditor.ssh.client"}   # StarView; Termius (SSH from the tablet)
# preinstalled apps that wake up on their own (sync, backups, updates, prefetch): quieted when present
HEAVY_SYSTEM = {
  "com.google.android.youtube", "com.google.android.apps.youtube.music", "com.google.android.apps.youtube.kids",
  "com.android.chrome", "com.google.android.gm", "com.google.android.apps.photos", "com.google.android.apps.docs",
  "com.google.android.apps.maps", "com.google.android.videos", "com.google.android.apps.tachyon",
  "com.google.android.apps.magazines", "com.google.android.keep", "com.google.android.calendar", "com.android.vending",
  "com.google.android.apps.subscriptions.red", "com.google.android.apps.walletnfcrel", "com.google.android.apps.books",
  "com.google.android.apps.podcasts", "com.google.android.play.games", "com.google.android.apps.kids.home",
  "com.google.android.apps.docs.editors.docs", "com.google.android.apps.docs.editors.sheets",
  "com.google.android.apps.docs.editors.slides", "com.netflix.mediaclient", "com.amazon.avod.thirdpartyclient",
}
SETTINGS = (("global", "wifi_scan_always_enabled", "0"), ("global", "ble_scan_always_enabled", "0"))
PKG = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")
REAPPLY_S = 600.0


def _pkg_of(component: str) -> str:
  c = (component or "").strip()
  return c.split("/")[0] if "/" in c else c


def survey_script() -> str:
  return "; ".join([
    'echo "KEEP $(settings get secure default_input_method)"',
    'echo "KEEP $(cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME | tail -1)"',
    'echo "KEEP $(settings get secure tts_default_synth)"',
    'echo "KEEP $(settings get secure voice_recognition_service)"',
    'echo "KEEP $(settings get secure assistant)"',
    'echo "KEEP $(settings get secure voice_interaction_service)"',
    *[f'echo "SET {ns} {k} $(settings get {ns} {k})"' for ns, k, _ in SETTINGS],
    'for p in $(pm list packages -3); do echo "USER ${p#package:}"; done',
    'for p in $(pm list packages -s); do echo "SYS ${p#package:}"; done',
  ])


def parse_survey(out: str):
  keep, user, system, settings = set(), [], set(), {}
  for ln in out.splitlines():
    parts = ln.strip().split(" ")
    if len(parts) < 2:
      continue
    if parts[0] == "KEEP":
      p = _pkg_of(parts[1])
      if PKG.match(p):
        keep.add(p)
    elif parts[0] == "USER" and PKG.match(parts[1]):
      user.append(parts[1])
    elif parts[0] == "SYS" and PKG.match(parts[1]):
      system.add(parts[1])
    elif parts[0] == "SET" and len(parts) >= 4:
      settings[f"{parts[1]} {parts[2]}"] = parts[3]
  return keep, user, system, settings


def targets(keep: set, user: list, system: set, extra_keep: set) -> list:
  skip = keep | ALWAYS_KEEP | extra_keep
  out = [p for p in user if p not in skip]
  out += sorted(p for p in HEAVY_SYSTEM & system if p not in skip and p not in out)
  return out


def quiet_script(pkgs: list) -> str:
  """Prints "OLD <pkg> <appop line> | <bucket>" for each, then quiets it."""
  lst = " ".join(pkgs)
  loop = ("for p in " + lst + "; do "
          + 'echo "OLD $p $(cmd appops get $p RUN_ANY_IN_BACKGROUND 2>&1 | head -1) | $(am get-standby-bucket $p 2>&1)"; '
          + "cmd appops set $p RUN_ANY_IN_BACKGROUND ignore; am set-standby-bucket $p restricted; am force-stop $p; done")
  rest = [f"settings put {ns} {k} {v}" for ns, k, v in SETTINGS]
  return "; ".join([loop, "am kill-all", *rest, f"dumpsys deviceidle whitelist +{OURS} >/dev/null", "echo DONE"])


def parse_old(out: str) -> dict:
  """{pkg: {"op": allow|ignore|deny|default, "bucket": "10"...}} from quiet_script's output."""
  old = {}
  for ln in out.splitlines():
    m = re.match(r"^OLD (\S+) (.*) \| (.*)$", ln.strip())
    if not m:
      continue
    op_line, bucket = m.group(2), m.group(3).strip()
    op = "default"
    mo = re.search(r"RUN_ANY_IN_BACKGROUND: (\w+)", op_line)
    if mo and not op_line.startswith("Uid mode"):
      op = mo.group(1)
    old[m.group(1)] = {"op": op, "bucket": bucket if bucket.isdigit() else ""}
  return old


def restore_script(old: dict, settings: dict) -> str:
  cmds = []
  for p, o in old.items():
    if not PKG.match(p):
      continue
    cmds.append(f"cmd appops set {p} RUN_ANY_IN_BACKGROUND {o.get('op') or 'default'}")
    b = o.get("bucket") or ""
    cmds.append(f"am set-standby-bucket {p} {b if b.isdigit() and b != '5' else 'active'}")
  for key, v in settings.items():
    ns, k = key.split(" ", 1)
    cmds.append(f"settings delete {ns} {k}" if v in ("null", "") else f"settings put {ns} {k} {v}")
  cmds.append("echo DONE")
  return "; ".join(cmds)


class TabletSaver:
  def __init__(self, adb, state_path=STATE, keep_path=KEEP_FILE, clock=time.monotonic):
    self.adb = adb            # adb(*args, timeout=) -> CompletedProcess | None (no tablet)
    self.state_path = state_path
    self.keep_path = keep_path
    self.clock = clock
    self.state = self._load()
    self.applied_at = -1e9

  def _load(self) -> dict:
    try:
      with open(self.state_path) as f:
        s = json.load(f)
      if isinstance(s, dict):
        return s
    except Exception:
      pass
    return {"on": False, "old": {}, "settings": {}}

  def _save(self):
    try:
      os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
      tmp = self.state_path + ".tmp"
      with open(tmp, "w") as f:
        json.dump(self.state, f)
      os.replace(tmp, self.state_path)
    except Exception:
      pass

  def _extra_keep(self) -> set:
    try:
      with open(self.keep_path) as f:
        return {ln.strip() for ln in f if PKG.match(ln.strip())}
    except Exception:
      return set()

  def status(self) -> dict:
    return {"ok": True, "on": bool(self.state.get("on")), "quieted": len(self.state.get("old", {})),
            "apps": sorted(self.state.get("old", {}))}

  def set(self, on: bool, force: bool = False) -> dict:
    try:
      return self._on(force) if on else self._off()
    except Exception as e:   # adb timeouts: the tablet asleep, busy or unplugged
      return {"ok": False, "error": f"tablet: {e}"}

  def _on(self, force: bool) -> dict:
    if self.state.get("on") and not force and self.clock() - self.applied_at < REAPPLY_S:
      return dict(self.status(), already=True)
    r = self.adb("shell", survey_script(), timeout=30)
    if r is None:
      return {"ok": False, "error": "The comma can't reach the tablet over adb (USB debugging off, or this comma not allowed yet)."}
    keep, user, system, settings = parse_survey(r.stdout)
    if not user and not system:
      return {"ok": False, "error": "The tablet didn't list its apps."}
    pkgs = targets(keep, user, system, self._extra_keep())
    q = self.adb("shell", quiet_script(pkgs), timeout=120)
    if q is None or "DONE" not in q.stdout:
      return {"ok": False, "error": "The tablet stopped answering halfway; try again."}
    old = parse_old(q.stdout)
    # the first value seen is the one to go back to: a re-apply must not record our own "ignore"/"restricted"
    prev = self.state.get("old", {}) if self.state.get("on") else {}
    for p, o in old.items():
      prev.setdefault(p, o)
    prev_set = self.state.get("settings", {}) if self.state.get("on") else {}
    for k, v in settings.items():
      prev_set.setdefault(k, v)
    self.state = {"on": True, "old": prev, "settings": prev_set}
    self._save()
    self.applied_at = self.clock()
    return dict(self.status(), stopped=len(pkgs), kept=sorted((keep | ALWAYS_KEEP) & (set(user) | system)))

  def _off(self) -> dict:
    if not self.state.get("on"):
      return self.status()
    r = self.adb("shell", restore_script(self.state.get("old", {}), self.state.get("settings", {})), timeout=120)
    if r is None or "DONE" not in r.stdout:
      return {"ok": False, "error": "The comma can't reach the tablet over adb; it will put things back when you switch it off again."}
    n = len(self.state.get("old", {}))
    self.state = {"on": False, "old": {}, "settings": {}}
    self._save()
    return dict(self.status(), restored=n)
