"""Keep "Big Model Loading" until the big model runs at normal speed (fork fix, remove if upstream fixes it).

modeld cleared ChestnutLoading as soon as the big model loaded, but its first passes on the camera's real buffers are
still slow: on the road one took ~1 s, the whole comma stalled with it and 29 frames were missed, 3-4 s after loading.
selfdrived only waits 5 s after loading, so "Driving Model Lagging" showed while the drop count faded, and openpilot
could have been engaged right into that stall. modeld now keeps ChestnutLoading (engagement held by bigModelLoading,
drops not counted) until the big model has run FAST_RUNS passes in a row under FAST_S with no missed frame, or MAX_S
has passed (after that the normal frame-drop alert decides, as before).
"""

FAST_S = 0.060     # a normal big-model pass is ~42 ms; frames come every 50 ms
FAST_RUNS = 20     # one second of normal passes in a row
MAX_S = 15.0       # never hold engagement longer than this


class BigModelWarmup:
  def __init__(self, now: float):
    self.start = now
    self.runs = self.streak = self.missed = 0
    self.slowest = 0.
    self.failed = False

  def record(self, exec_s: float, dropped_frames: int) -> None:
    self.runs += 1
    if self.runs == 1:
      dropped_frames = 0   # modeld's first pass counts every frame since the camera started (~2000), not a miss
    self.slowest = max(self.slowest, exec_s)
    self.missed += max(0, dropped_frames)
    self.streak = self.streak + 1 if exec_s < FAST_S and dropped_frames <= 0 else 0

  @property
  def steady(self) -> bool:
    return self.streak >= FAST_RUNS

  def finished(self, now: float) -> bool:
    return self.steady or self.failed or now - self.start >= MAX_S

  def summary(self, now: float) -> dict:
    return {"seconds": round(now - self.start, 2), "runs": self.runs, "slowest_ms": round(self.slowest * 1000),
            "missed_frames": self.missed, "outcome": "steady" if self.steady else "failed" if self.failed else "max_time"}
