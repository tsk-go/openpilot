"""Keep the Chestnut model's compiled GPU programs between drives.

The Chestnut artifact ships kernel graphs, not GPU binaries: every modeld start
turned them into programs again on the comma's CPU, and with the CPU busy that
took about a minute, right at modeld's Big load limit. tinygrad already keeps
finished programs in to_program_cache, keyed by the kernel graph's hash, the
renderer and the codegen settings, but only in memory. This file keeps them on
/data, so the next start only reads them back.

A cache entry is only used for the exact kernel it was made from, and the file
is checked against its own digest before use. Any problem here means "compile
as before", never a failed start.
"""
import hashlib
import os
import pickle
import re
import time
from pathlib import Path

from openpilot.common.swaglog import cloudlog

CACHE_DIR = Path("/data/starview/model_cache")
MAGIC = b"SPPC1\n"
KEEP_FILES = 3
MAX_BYTES = 512 * 1024 * 1024
_on_disk = 0  # programs the file already holds, so an unchanged cache is not rewritten


def _codegen():
  import tinygrad.codegen as codegen
  return codegen


def _manifest() -> str:
  try:
    from openpilot.starpilot.models.runtime_bridge.runtime import MANIFEST_SHA256
    return MANIFEST_SHA256[:16]
  except Exception:
    return "runtime"


def path_for(model: str | None, root: Path | None = None) -> Path:
  tag = re.sub(r"[^A-Za-z0-9_.-]", "_", model or "bundled")[:64] or "bundled"
  return (root or CACHE_DIR) / f"{_manifest()}-{tag}.programs"


def preload(model: str | None, root: Path | None = None) -> int:
  """Put saved programs into tinygrad's cache; returns how many were added."""
  global _on_disk
  path = path_for(model, root)
  try:
    data = path.read_bytes()
  except OSError:
    return 0
  started = time.monotonic()
  try:
    head = len(MAGIC)
    if data[:head] != MAGIC or hashlib.sha256(data[head + 32:]).digest() != data[head:head + 32]:
      raise ValueError("program cache digest mismatch")
    entries = pickle.loads(data[head + 32:])
    cache = _codegen().to_program_cache
    added = 0
    for blob in entries:
      try:
        key, program = pickle.loads(blob)
      except Exception:
        continue
      if key not in cache:
        cache[key] = program
        added += 1
    _on_disk = len(cache)
  except Exception:
    cloudlog.exception("chestnut program cache unreadable; compiling instead")
    forget(model, root)
    return 0
  cloudlog.event("chestnut.program_cache", action="loaded", programs=added, bytes=len(data),
                 seconds=round(time.monotonic() - started, 2))
  return added


def save(model: str | None, root: Path | None = None) -> int:
  """Write every program tinygrad has made so far; returns how many were written."""
  path = path_for(model, root)
  started = time.monotonic()
  try:
    snapshot = dict(_codegen().to_program_cache)
    if len(snapshot) <= _on_disk:
      return 0
    entries = []
    for item in snapshot.items():
      try:
        entries.append(pickle.dumps(item, protocol=pickle.HIGHEST_PROTOCOL))
      except Exception:
        continue
    if not entries:
      return 0
    payload = pickle.dumps(entries, protocol=pickle.HIGHEST_PROTOCOL)
    if len(payload) > MAX_BYTES:
      cloudlog.warning("chestnut program cache too large to keep: %d bytes", len(payload))
      return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    with open(tmp, "wb") as f:
      f.write(MAGIC + hashlib.sha256(payload).digest() + payload)
      f.flush()
      os.fsync(f.fileno())
    os.replace(tmp, path)
    _trim(path)
  except Exception:
    cloudlog.exception("chestnut program cache not saved")
    return 0
  cloudlog.event("chestnut.program_cache", action="saved", programs=len(entries), bytes=len(payload),
                 seconds=round(time.monotonic() - started, 2))
  return len(entries)


def forget(model: str | None, root: Path | None = None) -> None:
  try:
    path_for(model, root).unlink(missing_ok=True)
  except OSError:
    pass


def _trim(keep: Path) -> None:
  files = sorted(keep.parent.glob("*.programs"), key=lambda p: p.stat().st_mtime, reverse=True)
  for old in files[KEEP_FILES:]:
    if old != keep:
      old.unlink(missing_ok=True)
  for tmp in keep.parent.glob("*.programs.tmp*"):  # left by a start that was killed mid-write; only one modeld writes
    tmp.unlink(missing_ok=True)
