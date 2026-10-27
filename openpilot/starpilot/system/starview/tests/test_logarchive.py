import os

import pytest

from openpilot.starpilot.system.starview import logarchive


@pytest.fixture
def params(tmp_path, monkeypatch):
  d = tmp_path / "params"
  d.mkdir()
  monkeypatch.setattr(logarchive, "PARAMS_DIRS", (str(d), str(tmp_path / "shm")))
  def put(name, value):
    if value is None:
      (d / name).unlink(missing_ok=True)
    else:
      (d / name).write_bytes(b"1" if value else b"0")
  return put


@pytest.mark.parametrize("offroad, onroad_flag, expected", [
  (True, None, False),     # StarPilot 7, car off: copy
  (False, None, True),     # StarPilot 7, car on: never touch the stick
  (None, None, True),      # can't tell (no flags yet): treat as the car on
  (True, True, True),      # an older build that still sets IsOnroad
  (True, False, False),
])
def test_onroad_follows_starpilot_7_offroad_flag(params, offroad, onroad_flag, expected):
  params("IsOffroad", offroad)
  params("IsOnroad", onroad_flag)
  assert logarchive.onroad() is expected


def test_copy_stops_within_a_megabyte_when_the_car_turns_on(tmp_path, params, monkeypatch):
  src, mnt = tmp_path / "realdata", tmp_path / "mnt"
  (src / "00000001--abc--0").mkdir(parents=True)
  mnt.mkdir()
  (src / "00000001--abc--0" / "fcamera.hevc").write_bytes(os.urandom(5 * 1024 * 1024))
  monkeypatch.setattr(logarchive, "SRC", str(src))
  monkeypatch.setattr(logarchive, "MNT", str(mnt))
  params("IsOffroad", True)
  reads = []
  real_open = open
  def spy_open(path, mode="r", *a, **k):
    f = real_open(path, mode, *a, **k)
    if "fcamera" in str(path) and "r" in mode and str(path).startswith(str(src)):
      orig = f.read
      def read(n=-1):
        reads.append(n)
        if len(reads) == 2:
          params("IsOffroad", False)   # the car starts while the second megabyte is copied
        return orig(n)
      f.read = read
    return f
  monkeypatch.setattr("builtins.open", spy_open)
  monkeypatch.setattr(logarchive.time, "sleep", lambda s: None)
  st = {}
  copied, files = logarchive.copy_all(st)
  assert st["stopped"] == "car turned on" and files == 0
  assert len(reads) <= 3
  assert not any(p.name.endswith(".part") for p in mnt.rglob("*"))


def test_copy_is_capped_at_the_set_speed(tmp_path, params, monkeypatch):
  src, mnt = tmp_path / "realdata", tmp_path / "mnt"
  (src / "00000001--abc--0").mkdir(parents=True)
  mnt.mkdir()
  (src / "00000001--abc--0" / "rlog.zst").write_bytes(os.urandom(4 * 1024 * 1024))
  monkeypatch.setattr(logarchive, "SRC", str(src))
  monkeypatch.setattr(logarchive, "MNT", str(mnt))
  monkeypatch.setattr(logarchive, "MAX_BYTES_PER_S", 2 * 1024 * 1024)
  params("IsOffroad", True)
  slept = []
  monkeypatch.setattr(logarchive.time, "sleep", slept.append)
  copied, files = logarchive.copy_all({})
  assert files == 1 and copied == 4 * 1024 * 1024
  assert sum(slept) >= 1.5            # 4 MB at 2 MB/s: about 2 s of waiting
  assert (mnt / "00000001--abc--0" / "rlog.zst").stat().st_size == 4 * 1024 * 1024
