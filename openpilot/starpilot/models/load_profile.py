"""Where the Chestnut big-model load spends its time.

While modeld's loader thread runs, a sampler looks at its Python stack four times
a second. When the load ends (done, failed or timed out), one cloudlog event
`chestnut.load_profile` lists the functions seen most: `inclusive` counts a
function once per sample if it is anywhere on the stack (time spent in it and
below), `leaf` counts only the innermost frame. Sampling only reads frames; it
never pauses the loader.
"""
import sys
import threading
import time
from collections import Counter

from openpilot.common.swaglog import cloudlog

INTERVAL_S = 0.25
TOP = 30


def _name(frame) -> str:
  code = frame.f_code
  parts = code.co_filename.replace("\\", "/").split("/")
  return f"{'/'.join(parts[-2:])}:{code.co_name}"


class LoadProfiler:
  def __init__(self, thread: threading.Thread, interval: float = INTERVAL_S):
    self.thread = thread
    self.interval = interval
    self.inclusive: Counter = Counter()
    self.leaf: Counter = Counter()
    self.samples = 0
    self.started = time.monotonic()
    self._stop = threading.Event()
    self._sampler = threading.Thread(target=self._run, name="chestnut-load-profile", daemon=True)

  def start(self) -> "LoadProfiler":
    self.started = time.monotonic()
    self._sampler.start()
    return self

  def sample(self) -> None:
    frame = sys._current_frames().get(self.thread.ident)
    if frame is None:
      return
    self.leaf[_name(frame)] += 1
    seen = set()
    while frame is not None:
      seen.add(_name(frame))
      frame = frame.f_back
    self.inclusive.update(seen)
    self.samples += 1

  def _run(self) -> None:
    while not self._stop.wait(self.interval):
      if not self.thread.is_alive():
        break
      try:
        self.sample()
      except Exception:
        pass

  def report(self, outcome: str) -> dict:
    self._stop.set()
    seconds = round(time.monotonic() - self.started, 1)
    per = self.interval if self.samples else 0.
    packet = {"outcome": outcome, "seconds": seconds, "samples": self.samples,
              "inclusive": [f"{n * per:.1f}s {name}" for name, n in self.inclusive.most_common(TOP)],
              "leaf": [f"{n * per:.1f}s {name}" for name, n in self.leaf.most_common(TOP // 2)]}
    try:
      cloudlog.event("chestnut.load_profile", **packet)
    except Exception:
      pass
    return packet


def watch(thread: threading.Thread) -> LoadProfiler | None:
  try:
    return LoadProfiler(thread).start()
  except Exception:
    return None
