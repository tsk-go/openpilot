"""StarView's offline mode lets the model and sound downloads through its download door (fork patch 54): the model
manager's _work and the sound downloads' _run run inside offline.download_door (offline.through_door, one decorator
line in each upstream file), and their default opener is offline.urlopen. Moved here from upstream's
models/tests/test_manager.py and audio/tests/test_downloads.py, on those files' own fixtures."""
from contextlib import contextmanager
from unittest.mock import patch

from openpilot.starpilot.audio.tests import test_downloads as sounds_upstream
from openpilot.starpilot.models.manager import ModelManager
from openpilot.starpilot.models.tests import test_manager as models_upstream
from openpilot.starpilot.system.starview import offline


@contextmanager
def fixture(cls):
  case = cls("run")
  case.setUp()
  try:
    yield case
  finally:
    case.doCleanups()


def door_recorder(events, extra=lambda: ()):
  @contextmanager
  def door(reason):
    events.append(("open", reason))
    yield
    events.append(("close", reason, *extra()))
  return door


def test_model_downloads_open_the_door_for_the_whole_job():
  with fixture(models_upstream.ModelManagerTest) as case:
    events = []
    with patch.object(offline, "download_door", door_recorder(events, lambda: (len(case.urls),))):
      case.manager.action('refresh_manifest', {})
      case.manager.worker.join(3)
      case.download()
    assert events == [("open", "models"), ("close", "models", 1), ("open", "models"), ("close", "models", 4)]


def test_model_managers_default_opener_is_the_offline_aware_one():
  with fixture(models_upstream.ModelManagerTest) as case:
    manager = ModelManager(root=case.root)
    try:
      assert manager.opener is offline.urlopen
    finally:
      manager.close()


def test_sound_download_opens_the_door():
  with fixture(sounds_upstream.SoundDownloadTests) as case:
    payload = sounds_upstream.archive({"sounds/": b"", "sounds/engage.wav": sounds_upstream.wav()})
    events = []
    with patch.object(offline, "download_door", door_recorder(events)):
      manager = case.manager(payload)
      manager.action("download", {"pack": "duck"})
      job = case.finish(manager)["job"]
    assert job["state"] == "complete", job.get("error")
    assert events == [("open", "sounds"), ("close", "sounds")]
    assert sounds_upstream.SoundDownloads(lambda: True, case.root, case.catalog).opener is offline.urlopen
