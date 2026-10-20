from types import SimpleNamespace
from unittest.mock import Mock

from openpilot.starpilot.models import program_cache


def use(monkeypatch, cache):
  monkeypatch.setattr(program_cache, "_codegen", lambda: SimpleNamespace(to_program_cache=cache))
  monkeypatch.setattr(program_cache, "_on_disk", 0)
  monkeypatch.setattr(program_cache, "cloudlog", Mock())


def test_programs_come_back_in_a_new_start(monkeypatch, tmp_path):
  use(monkeypatch, {("k1", "AMD"): "program-1", ("k2", "AMD"): "program-2"})
  assert program_cache.save("mountaindewv3", tmp_path) == 2
  fresh = {("k2", "AMD"): "already-made"}
  use(monkeypatch, fresh)
  assert program_cache.preload("mountaindewv3", tmp_path) == 1
  assert fresh == {("k1", "AMD"): "program-1", ("k2", "AMD"): "already-made"}


def test_unchanged_cache_is_not_rewritten(monkeypatch, tmp_path):
  use(monkeypatch, {("k1", "AMD"): "program-1"})
  program_cache.save("m", tmp_path)
  cache = {}
  use(monkeypatch, cache)
  program_cache.preload("m", tmp_path)
  assert program_cache.save("m", tmp_path) == 0
  cache[("k2", "AMD")] = "program-2"
  assert program_cache.save("m", tmp_path) == 2


def test_damaged_file_compiles_instead_and_is_removed(monkeypatch, tmp_path):
  use(monkeypatch, {("k1", "AMD"): "program-1"})
  program_cache.save("m", tmp_path)
  path = program_cache.path_for("m", tmp_path)
  data = bytearray(path.read_bytes())
  data[-1] ^= 0xFF
  path.write_bytes(bytes(data))
  cache = {}
  use(monkeypatch, cache)
  assert program_cache.preload("m", tmp_path) == 0
  assert cache == {} and not path.exists()


def test_missing_file_and_nothing_to_save(monkeypatch, tmp_path):
  use(monkeypatch, {})
  assert program_cache.preload("m", tmp_path) == 0
  assert program_cache.save("m", tmp_path) == 0
  assert not any(tmp_path.iterdir())


def test_unpicklable_entries_are_skipped(monkeypatch, tmp_path):
  use(monkeypatch, {("k1", "AMD"): "program-1", ("k2", "AMD"): lambda: None})
  assert program_cache.save("m", tmp_path) == 1


def test_file_names_are_safe_and_old_files_trimmed(monkeypatch, tmp_path):
  assert program_cache.path_for("../x y", tmp_path).parent == tmp_path
  assert program_cache.path_for(None, tmp_path).name.endswith("-bundled.programs")
  use(monkeypatch, {("k", "AMD"): "p"})
  for i in range(program_cache.KEEP_FILES + 2):
    monkeypatch.setattr(program_cache, "_on_disk", 0)
    program_cache.save(f"model{i}", tmp_path)
  assert len(list(tmp_path.glob("*.programs"))) == program_cache.KEEP_FILES
  assert program_cache.path_for(f"model{program_cache.KEEP_FILES + 1}", tmp_path).exists()
