import threading
import time
from unittest.mock import Mock

from openpilot.starpilot.models import load_profile


def slow_copy(stop):
  while not stop.is_set():
    time.sleep(0.001)


def busy_loader(stop):
  slow_copy(stop)


def test_profile_names_where_the_loader_waits(monkeypatch):
  log = Mock()
  monkeypatch.setattr(load_profile, "cloudlog", log)
  stop = threading.Event()
  loader = threading.Thread(target=busy_loader, args=(stop,), daemon=True)
  loader.start()
  profiler = load_profile.LoadProfiler(loader, interval=0.01).start()
  time.sleep(0.2)
  packet = profiler.report("loaded")
  stop.set()
  loader.join(1)
  assert packet["outcome"] == "loaded" and packet["samples"] > 5
  assert any("test_load_profile.py:slow_copy" in row for row in packet["inclusive"])
  assert any("test_load_profile.py:busy_loader" in row for row in packet["inclusive"])
  log.event.assert_called_once()
  assert log.event.call_args.args[0] == "chestnut.load_profile"


def test_a_finished_loader_gives_an_empty_profile(monkeypatch):
  monkeypatch.setattr(load_profile, "cloudlog", Mock())
  loader = threading.Thread(target=lambda: None)
  loader.start()
  loader.join()
  profiler = load_profile.LoadProfiler(loader, interval=0.01).start()
  time.sleep(0.05)
  packet = profiler.report("failed-load")
  assert packet["samples"] == 0 and packet["inclusive"] == []
