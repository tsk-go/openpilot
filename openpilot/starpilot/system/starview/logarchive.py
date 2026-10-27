#!/usr/bin/env python3
"""
StarView log archive: copies finished drives from the comma's internal storage to the USB stick - ONLY while parked.

Why: openpilot must never write its live logs to a USB stick. When a stick stalls or drops off the hub, loggerd
gets I/O errors and crashes, which trips "Process Not Running" / "Communication Issue" take-over alerts. So loggerd
always records to internal storage, and this script mirrors the finished segments onto the stick afterwards:

  * runs only while offroad (IsOffroad = 1; unknown counts as the car on) and stops within 1 MB if the car turns on
  * copies at most 20 MB/s: the stick shares the comma's one USB link with the eGPU
  * mounts the EXTDATA stick on its own folder (/data/extstorage/mnt), copies, syncs and UNMOUNTS again
  * never deletes anything on internal storage (openpilot's deleter keeps managing that, uploads keep working)
  * when the stick gets full, the oldest drives ON THE STICK are removed (keeps ~10 % free)
  * any stick error: unmount and give up until next time - nothing else is affected
  * while it runs, its progress is in /dev/shm (RAM, no flash writes) for the tablet's storage card

starviewd starts it by itself every few minutes while parked (turn that off: touch /data/starview/no_log_archive).
By hand:
    python3 /data/starview/logarchive.py --status
    python3 /data/starview/logarchive.py --once        (parked only)
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

LABEL = "EXTDATA"
SRC = "/data/media/0/realdata"
MNT = "/data/extstorage/mnt"
STATUS = "/data/starview/log_archive_status.json"
LOCK = "/dev/shm/starview_logarchive.lock"
PROGRESS = "/dev/shm/starview_logarchive_progress.json"
PROGRESS_EVERY_S = 2.0
KEEP_FREE = 0.10


def sh(cmd, timeout=120):
  if os.geteuid() != 0:
    cmd = "sudo -n " + cmd
  p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
  return p.returncode, (p.stdout + p.stderr).strip()


PARAMS_DIRS = ("/data/params/d", "/dev/shm/params/d")
MAX_BYTES_PER_S = 20 * 1024 * 1024   # the stick shares the comma's one USB link with the eGPU: never flood it


def _flag(name):
  """A bool param: True / False, or None when it can't be read."""
  for d in PARAMS_DIRS:
    try:
      return open(f"{d}/{name}", "rb").read().strip() in (b"1", b"\x01")
    except FileNotFoundError:
      continue
    except Exception:
      return None
  return None


def onroad():
  """The car is on, or we can't tell: then the stick is not touched.
  StarPilot 7 sets only IsOffroad (its IsOnroad no longer exists, so reading IsOnroad alone said 'parked' while driving)."""
  if _flag("IsOnroad"):
    return True
  return _flag("IsOffroad") is not True


def stick():
  p = f"/dev/disk/by-label/{LABEL}"
  if os.path.exists(p):
    return os.path.realpath(p)
  rc, o = sh(f"blkid -L {LABEL}", timeout=15)
  return o.strip() if rc == 0 and o.strip().startswith("/dev/") else None


def mounted(mp):
  try:
    return any(l.split()[1] == mp for l in open("/proc/mounts"))
  except Exception:
    return False


class Progress:
  """Live progress of this run for the tablet: one small JSON in /dev/shm, rewritten at most every 2 s."""
  def __init__(self):
    self.p = {"pid": os.getpid(), "started": time.time(), "phase": "starting",  # noqa: TID251  shown as a time on the tablet
              "total_bytes": 0, "done_bytes": 0, "total_files": 0, "done_files": 0, "segment": ""}
    self.last = 0.0
    self.rate_t0 = None

  def set(self, force=False, **kw):
    self.p.update(kw)
    now = time.monotonic()
    if not force and now - self.last < PROGRESS_EVERY_S:
      return
    self.last = now
    if self.p["phase"] == "copying":
      if self.rate_t0 is None:
        self.rate_t0 = (now, self.p["done_bytes"])
      dt = now - self.rate_t0[0]
      rate = (self.p["done_bytes"] - self.rate_t0[1]) / dt if dt > 1 else 0.0
      self.p["rate_MBps"] = round(rate / 1e6, 1)
      left = self.p["total_bytes"] - self.p["done_bytes"]
      self.p["eta_s"] = round(left / rate) if rate > 0 else None
    try:
      with open(PROGRESS + ".tmp", "w") as f:
        json.dump(self.p, f)
      os.replace(PROGRESS + ".tmp", PROGRESS)
    except Exception:
      pass

  @staticmethod
  def clear():
    try:
      os.unlink(PROGRESS)
    except Exception:
      pass


def read_progress():
  """This run's progress, or None when no copy is running (a file left by a killed run doesn't count)."""
  try:
    p = json.load(open(PROGRESS))
    os.kill(int(p["pid"]), 0)
    return p
  except Exception:
    return None


def save(st):
  st["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
  try:
    os.makedirs(os.path.dirname(STATUS), exist_ok=True)
    with open(STATUS + ".tmp", "w") as f:
      json.dump(st, f, indent=1)
    os.replace(STATUS + ".tmp", STATUS)
  except Exception:
    pass


def unmount():
  if mounted(MNT):
    sh("sync", timeout=120)
    rc, _ = sh(f"umount {MNT}", timeout=60)
    if rc != 0:
      sh(f"umount -l {MNT}", timeout=30)


def prune(st):
  """Oldest drives on the stick go first when it's nearly full."""
  u = shutil.disk_usage(MNT)
  if u.free / u.total >= KEEP_FREE:
    return
  dirs = sorted((os.path.getmtime(os.path.join(MNT, d)), d) for d in os.listdir(MNT)
                if os.path.isdir(os.path.join(MNT, d)) and d != "lost+found")
  for _, d in dirs:
    if onroad():
      return
    shutil.rmtree(os.path.join(MNT, d), ignore_errors=True)
    st["pruned"] = st.get("pruned", 0) + 1
    u = shutil.disk_usage(MNT)
    if u.free / u.total >= KEEP_FREE + 0.05:
      return


def plan():
  """What still has to go to the stick: [(segment, name, size)], and how many files are already there."""
  todo, skipped = [], 0
  for seg in sorted(os.listdir(SRC)):
    sp = os.path.join(SRC, seg)
    if not os.path.isdir(sp):
      continue
    dp = os.path.join(MNT, seg)
    for name in sorted(os.listdir(sp)):
      s = os.path.join(sp, name)
      if not os.path.isfile(s) or name.endswith(".lock") or name.startswith("."):
        continue
      size = os.path.getsize(s)
      d = os.path.join(dp, name)
      if os.path.exists(d) and os.path.getsize(d) == size:
        skipped += 1
      else:
        todo.append((seg, name, size))
  return todo, skipped


def copy_all(st, prog=None):
  prog = prog or Progress()
  copied = 0
  files = 0
  prog.set(force=True, phase="looking for new drives")
  todo, skipped = plan()
  prog.set(force=True, phase="copying", total_bytes=sum(t[2] for t in todo), total_files=len(todo))
  for seg, name, size in todo:
    if onroad():
      st["stopped"] = "car turned on"
      return copied, files
    sp, dp = os.path.join(SRC, seg), os.path.join(MNT, seg)
    s, d = os.path.join(sp, name), os.path.join(dp, name)
    if not os.path.isfile(s) or os.path.getsize(s) != size:   # deleted or still growing since the plan
      continue
    u = shutil.disk_usage(MNT)
    if u.free < size + 256 * 1024 * 1024:
      prune(st)
      if shutil.disk_usage(MNT).free < size + 256 * 1024 * 1024:
        st["stopped"] = "stick full"
        return copied, files
    os.makedirs(dp, exist_ok=True)
    tmp = d + ".part"
    with open(s, "rb") as fi, open(tmp, "wb") as fo:
      t0, sent = time.monotonic(), 0
      while True:
        b = fi.read(1024 * 1024)
        if not b:
          break
        fo.write(b)
        sent += len(b)
        prog.set(done_bytes=copied + sent, done_files=files, segment=seg)
        ahead = sent / MAX_BYTES_PER_S - (time.monotonic() - t0)
        if ahead > 0:
          time.sleep(ahead)
        if onroad():
          break
    if onroad():
      os.remove(tmp)
      st["stopped"] = "car turned on"
      return copied, files
    os.replace(tmp, d)
    try:  # keep the drive's own times, so "newest on the stick" means the newest drive, not the newest copy
      sst = os.stat(s)
      os.utime(d, (sst.st_atime, sst.st_mtime))
      pst = os.stat(sp)
      os.utime(dp, (pst.st_atime, pst.st_mtime))
    except OSError:
      pass
    copied += size
    files += 1
    prog.set(done_bytes=copied, done_files=files, segment=seg)
  st["already_there"] = skipped
  return copied, files


def run_once():
  if onroad():
    print("onroad: not touching the stick while driving")
    return 0
  try:
    fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
  except FileExistsError:
    try:
      pid = int(open(LOCK).read())
      os.kill(pid, 0)
      print("already running")
      return 0
    except Exception:
      os.unlink(LOCK)
      return run_once()
  st = {"result": "?"}
  prog = Progress()
  try:
    dev = stick()
    if not dev:
      st["result"] = "no EXTDATA stick"
      print(st["result"])
      return 0
    st["device"] = dev
    os.makedirs(MNT, exist_ok=True)
    if not mounted(MNT):
      prog.set(force=True, phase="checking the stick")
      sh(f"e2fsck -p {dev}", timeout=600)       # clean up after a power cut / the earlier drop-outs
      rc, o = sh(f"mount -t ext4 -o noatime,nodiratime,errors=remount-ro {dev} {MNT}", timeout=60)
      if rc != 0:
        st["result"] = f"mount failed: {o[-200:]}"
        print(st["result"])
        return 1
      sh(f"chown 1000:1000 {MNT}", timeout=15)
    t0 = time.time()  # noqa: TID251  wall-clock run times, shown on the tablet
    copied, files = copy_all(st, prog)
    prog.set(force=True, phase="making room" if not st.get("stopped") else "stopping")
    prune(st)
    # what's on the stick now: count and the newest / oldest drive, for the tablet's storage card
    segs = [e for e in os.scandir(MNT) if e.is_dir() and e.name != "lost+found"]
    st["stick_segments"] = len(segs)
    if segs:
      st["stick_newest_time"] = max(e.stat().st_mtime for e in segs)
      st["stick_oldest_time"] = min(e.stat().st_mtime for e in segs)
    try:
      prev = json.load(open(STATUS))
    except Exception:
      prev = {}
    st["last_copy_time"] = time.time() if files > 0 else prev.get("last_copy_time")  # noqa: TID251
    st["last_copy_MB"] = round(copied / 1e6) if files > 0 else prev.get("last_copy_MB")
    st["run_time"] = time.time()  # noqa: TID251
    u = shutil.disk_usage(MNT)
    st.update(result=st.get("stopped", "ok"), copied_MB=round(copied / 1e6), files=files,
              seconds=round(time.time() - t0),  # noqa: TID251
              stick_free_GB=round(u.free / 1e9, 1), stick_size_GB=round(u.total / 1e9, 1))
    print(json.dumps(st))
    return 0
  except Exception as e:
    st["result"] = f"error: {e}"
    print(st["result"])
    return 1
  finally:
    prog.set(force=True, phase="finishing (sync and unmount)")
    unmount()
    save(st)
    Progress.clear()
    try:
      os.unlink(LOCK)
    except Exception:
      pass


def status():
  print(f"stick ({LABEL}) : {stick() or 'not found'}")
  print(f"internal logs   : {SRC}  (openpilot records here; the stick is never in the recording path)")
  print(f"stick mounted   : {'yes (copying)' if mounted(MNT) else 'no (only mounted while copying)'}")
  print(f"auto archive    : {'OFF (/data/starview/no_log_archive)' if os.path.exists('/data/starview/no_log_archive') else 'on, while parked'}")
  p = read_progress()
  if p:
    tot = max(1, p.get("total_bytes", 0))
    print(f"copying now     : {p.get('phase')}  {100 * p.get('done_bytes', 0) // tot}%  "
          f"({p.get('done_bytes', 0) / 1e9:.1f} of {p.get('total_bytes', 0) / 1e9:.1f} GB, "
          f"{p.get('done_files', 0)}/{p.get('total_files', 0)} files, {p.get('rate_MBps', 0)} MB/s)")
  try:
    print("last run        :", open(STATUS).read().strip())
  except Exception:
    print("last run        : never")


if __name__ == "__main__":
  ap = argparse.ArgumentParser()
  ap.add_argument("--once", action="store_true")
  ap.add_argument("--status", action="store_true")
  a = ap.parse_args()
  if a.once:
    sys.exit(run_once())
  status()
