import os
import threading
import time

import pytest

from openpilot.starpilot.system.starview.techstream.session import DIAG_FLAG, FLAG_FRESH_S, DiagSession, SessionError, flag_fresh


class FakeLink:
  def __init__(self):
    self.closed = False

  def close(self):
    self.closed = True


class Harness:
  """Every outside dependency of the session under control: when pandad exits, the clock, the link, the flag file."""

  def __init__(self, tmp_path, offroad=True, parked=False, pandad_exits_after=1):
    self.offroad = offroad
    self.parked = parked
    self.pandad_polls = 0
    self.pandad_exits_after = pandad_exits_after
    self.on_pandad_poll = None
    self.now = 1000.0
    self.links: list[FakeLink] = []
    self.flag = tmp_path / "starview_diag"
    self.session = DiagSession(
      open_link=self._open_link, pandad_running=self._pandad_running,
      is_offroad=lambda: self.offroad, is_parked=lambda: self.parked, clock=lambda: self.now, sleep=self._sleep,
      idle_timeout_s=900, pandad_stop_timeout_s=15, flag_path=str(self.flag),
    )

  def _open_link(self):
    self.links.append(FakeLink())
    return self.links[-1]

  def _pandad_running(self):
    self.pandad_polls += 1
    if self.on_pandad_poll:
      self.on_pandad_poll()
    return self.pandad_exits_after is None or self.pandad_polls <= self.pandad_exits_after

  def _sleep(self, seconds):
    self.now += seconds

  def make_flag_old(self, age_s=60):
    old = time.time() - age_s  # noqa: TID251  file mtimes are wall clock
    os.utime(self.flag, (old, old))


def test_default_flag_path_is_what_pandad_run_checks():
  assert DIAG_FLAG == "/dev/shm/starview_diag" and FLAG_FRESH_S == 20


class TestEnter:
  def test_offroad_enter_stops_pandad_then_opens_link(self, tmp_path):
    h = Harness(tmp_path, offroad=True)
    flag_while_waiting = []
    h.on_pandad_poll = lambda: flag_while_waiting.append(h.flag.exists())
    h.session.enter()
    # the flag is up before we wait for pandad, so manager stops it; it stays up while active
    assert flag_while_waiting == [True, True]
    assert h.flag.exists() and flag_fresh(str(h.flag))
    assert not (tmp_path / "starview_diag.tmp").exists()
    assert len(h.links) == 1
    assert h.session.snapshot()["state"] == "active"

  def test_onroad_requires_park(self, tmp_path):
    h = Harness(tmp_path, offroad=False, parked=False)
    with pytest.raises(SessionError) as err:
      h.session.enter()
    assert err.value.status == 409 and "driving" in err.value.message
    assert not h.flag.exists()
    assert h.links == [] and h.pandad_polls == 0
    assert h.session.snapshot()["state"] == "idle"

  def test_onroad_parked_is_allowed(self, tmp_path):
    h = Harness(tmp_path, offroad=False, parked=True)
    h.session.enter()
    assert h.session.snapshot()["state"] == "active"
    assert h.flag.exists()

  def test_pandad_that_never_stops_rolls_back(self, tmp_path):
    h = Harness(tmp_path, pandad_exits_after=None)
    with pytest.raises(SessionError) as err:
      h.session.enter()
    assert err.value.status == 504
    # rolled back: the flag is gone so manager keeps pandad, and the panda isn't opened
    assert not h.flag.exists()
    assert h.links == []
    snap = h.session.snapshot()
    assert snap["state"] == "idle" and "pandad" in snap["error"]
    assert h.now > 1000.0 + 15   # it waited the whole timeout

  def test_open_link_failure_rolls_back(self, tmp_path):
    h = Harness(tmp_path)

    def broken():
      raise OSError("spi busy")
    h.session._open_link = broken
    with pytest.raises(SessionError) as err:
      h.session.enter()
    assert err.value.status == 500 and "spi busy" in err.value.message
    assert not h.flag.exists()
    assert h.session.snapshot()["state"] == "idle"

  def test_enter_twice_is_idempotent(self, tmp_path):
    h = Harness(tmp_path)
    h.session.enter()
    h.session.enter()
    assert len(h.links) == 1

  def test_error_is_cleared_by_the_next_enter(self, tmp_path):
    h = Harness(tmp_path, offroad=False)
    with pytest.raises(SessionError):
      h.session.enter()
    assert "error" in h.session.snapshot()
    h.offroad = True
    h.session.enter()
    assert "error" not in h.session.snapshot()


class TestExit:
  def test_exit_closes_link_and_restores_pandad(self, tmp_path):
    h = Harness(tmp_path)
    h.session.enter()
    h.session.exit()
    assert h.links[0].closed
    assert not h.flag.exists()
    assert h.session.snapshot()["state"] == "idle"

  def test_exit_clears_flag_even_if_close_fails(self, tmp_path):
    h = Harness(tmp_path)
    h.session.enter()

    def broken_close():
      raise OSError("usb gone")
    h.links[0].close = broken_close
    with pytest.raises(OSError):
      h.session.exit()
    assert not h.flag.exists()
    assert h.session.snapshot()["state"] == "idle"

  def test_exit_when_idle_is_harmless(self, tmp_path):
    h = Harness(tmp_path)
    h.session.exit()
    assert not h.flag.exists() and h.session.snapshot()["state"] == "idle"

  def test_idle_timeout_exits(self, tmp_path):
    h = Harness(tmp_path)
    h.session.enter()
    h.now += 899
    h.session.expire_if_idle()
    assert h.session.snapshot()["state"] == "active"
    h.now += 2
    h.session.expire_if_idle()
    assert h.session.snapshot()["state"] == "idle"
    assert h.links[0].closed
    assert not h.flag.exists()

  def test_snapshot_reports_remaining_idle_time(self, tmp_path):
    # the device gives the remaining seconds, so the page doesn't subtract the device clock from the browser's
    h = Harness(tmp_path)
    assert "idleRemainingS" not in h.session.snapshot()
    h.session.enter()
    h.now += 100
    assert h.session.snapshot()["idleRemainingS"] == 800

  def test_reset_on_startup_clears_stale_flag(self, tmp_path):
    # after a starviewd crash and restart the flag may still be there; if it isn't cleared pandad stays off
    h = Harness(tmp_path)
    h.flag.write_text("1\n")
    h.session.reset_on_startup()
    assert not h.flag.exists()
    h.session.reset_on_startup()   # no flag: no error


class TestKeepalive:
  def test_does_nothing_while_idle(self, tmp_path):
    h = Harness(tmp_path)
    h.session.keepalive()
    assert not h.flag.exists()

  def test_renews_flag_while_active(self, tmp_path):
    h = Harness(tmp_path)
    h.session.enter()
    h.make_flag_old()
    assert not flag_fresh(str(h.flag))
    h.session.keepalive()
    assert flag_fresh(str(h.flag))
    h.flag.unlink()
    h.session.keepalive()
    assert flag_fresh(str(h.flag))

  def test_renews_flag_while_entering(self, tmp_path):
    h = Harness(tmp_path, pandad_exits_after=2)
    seen = []

    def during_wait():
      if h.flag.exists():
        h.flag.unlink()
      h.session.keepalive()          # same thread: the session lock is re-entrant
      seen.append((h.session.snapshot()["state"], h.flag.exists()))
    h.on_pandad_poll = during_wait
    h.session.enter()
    assert seen and all(s == ("entering", True) for s in seen)

  def test_does_not_bring_flag_back_after_exit(self, tmp_path):
    h = Harness(tmp_path)
    h.session.enter()
    h.session.exit()
    h.session.keepalive()
    assert not h.flag.exists()

  def test_does_not_bring_flag_back_after_failed_enter(self, tmp_path):
    h = Harness(tmp_path, pandad_exits_after=None)
    with pytest.raises(SessionError):
      h.session.enter()
    h.session.keepalive()
    assert not h.flag.exists()


class TestFlagFresh:
  def test_new_file_is_fresh(self, tmp_path):
    flag = tmp_path / "flag"
    flag.write_text("")
    assert flag_fresh(str(flag))

  def test_file_older_than_window_is_stale(self, tmp_path):
    flag = tmp_path / "flag"
    flag.write_text("")
    old = time.time() - (FLAG_FRESH_S + 1)  # noqa: TID251
    os.utime(flag, (old, old))
    assert not flag_fresh(str(flag))

  def test_window_is_20_seconds(self, tmp_path):
    flag = tmp_path / "flag"
    flag.write_text("")
    mtime = os.path.getmtime(flag)
    assert flag_fresh(str(flag), now=mtime + 19.9)
    assert not flag_fresh(str(flag), now=mtime + 20)

  def test_missing_file_is_not_fresh(self, tmp_path):
    assert not flag_fresh(str(tmp_path / "missing"))

  def test_checks_diag_flag_by_default(self):
    assert flag_fresh.__defaults__[0] == DIAG_FLAG


class TestRun:
  def test_run_requires_active_session(self, tmp_path):
    h = Harness(tmp_path)
    with pytest.raises(SessionError) as err:
      h.session.run(lambda link: None)
    assert err.value.status == 409 and err.value.message == "Enter diagnostic mode first"

  def test_run_passes_link_and_refreshes_activity(self, tmp_path):
    h = Harness(tmp_path)
    h.session.enter()
    h.now += 800
    assert h.session.run(lambda link: link) is h.links[0]
    h.now += 800
    h.session.expire_if_idle()
    assert h.session.snapshot()["state"] == "active"
    assert h.session.snapshot()["lastActivity"] == pytest.approx(h.now - 800)

  def test_activity_counts_from_the_end_of_a_long_operation(self, tmp_path):
    h = Harness(tmp_path)
    h.session.enter()

    def slow(link):
      h.now += 1000
    h.session.run(slow)
    h.session.expire_if_idle()
    assert h.session.snapshot()["state"] == "active"

  def test_exit_waits_for_running_operation(self, tmp_path):
    # one bus operation at a time: exit() from another thread can't pull the link out from under run()
    h = Harness(tmp_path)
    h.session.enter()
    started, release = threading.Event(), threading.Event()
    closed_during_run = []

    def operation(link):
      started.set()
      release.wait(5)
      closed_during_run.append(link.closed)

    runner = threading.Thread(target=h.session.run, args=(operation,))
    runner.start()
    assert started.wait(5)
    exiter = threading.Thread(target=h.session.exit)
    exiter.start()
    exiter.join(0.1)
    assert exiter.is_alive()               # blocked on the session lock
    assert h.flag.exists()
    release.set()
    runner.join(5)
    exiter.join(5)
    assert closed_during_run == [False]
    assert h.links[0].closed and not h.flag.exists()
