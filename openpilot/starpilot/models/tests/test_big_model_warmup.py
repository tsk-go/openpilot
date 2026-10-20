from openpilot.starpilot.models.warmup import FAST_RUNS, MAX_S, BigModelWarmup


def test_stays_loading_through_the_slow_first_passes():
  # the drive that showed "Driving Model Lagging": a 96 ms pass, a 992 ms pass, then 29 missed frames at 47 ms
  w = BigModelWarmup(0.)
  # the first pass's count is every frame since the camera started (logged 1990 on the car): not counted
  for exec_s, dropped in [(0.096, 1990), (0.06, 6), (0.992, 0), (0.047, 29), (0.045, 4)]:
    w.record(exec_s, dropped)
    assert not w.finished(3.)
  for _ in range(FAST_RUNS - 1):
    w.record(0.042, 0)
  assert not w.finished(4.)
  w.record(0.042, 0)
  assert w.finished(4.)
  assert w.summary(4.) == {"seconds": 4.0, "runs": 5 + FAST_RUNS, "slowest_ms": 992, "missed_frames": 39, "outcome": "steady"}


def test_a_missed_frame_restarts_the_count():
  w = BigModelWarmup(0.)
  for _ in range(FAST_RUNS - 1):
    w.record(0.042, 0)
  w.record(0.042, 1)
  assert not w.steady
  for _ in range(FAST_RUNS):
    w.record(0.042, 0)
  assert w.steady


def test_never_holds_engagement_past_the_limit_or_after_a_failure():
  w = BigModelWarmup(10.)
  assert not w.finished(10. + MAX_S - 0.1)
  assert w.finished(10. + MAX_S)          # even with no frames at all
  assert w.summary(10. + MAX_S)["outcome"] == "max_time"
  f = BigModelWarmup(0.)
  f.failed = True
  assert f.finished(0.) and f.summary(0.)["outcome"] == "failed"
