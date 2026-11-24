"""pandad_gate.pandad_run (pandad's should_run in system/manager/process_config.py) keeps pandad stopped while
TechStream's flag file is fresh. process_config.py is too heavy to import off-device (cereal, Params, hardware), so
its use of pandad_run is checked in its source."""
import ast
import os
import time
from pathlib import Path

import pytest

from openpilot.starpilot.system.starview.techstream import pandad_gate, session

PROCESS_CONFIG = Path(__file__).resolve().parents[5] / "system" / "manager" / "process_config.py"


@pytest.fixture
def flag(tmp_path, monkeypatch):
  path = tmp_path / "starview_diag"
  monkeypatch.setattr(pandad_gate, "DIAG_FLAG", str(path))
  return path


def _call() -> bool:
  return pandad_gate.pandad_run(True, None, None)


def test_uses_the_session_flag_and_window():
  assert (pandad_gate.DIAG_FLAG, pandad_gate.FLAG_FRESH_S) == (session.DIAG_FLAG, session.FLAG_FRESH_S) == \
         ("/dev/shm/starview_diag", 20)


def test_pandad_process_uses_pandad_run():
  tree = ast.parse(PROCESS_CONFIG.read_text())
  assert any(isinstance(n, ast.ImportFrom) and n.module == "openpilot.starpilot.system.starview.techstream.pandad_gate" and
             [a.name for a in n.names] == ["pandad_run"] for n in tree.body)
  calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "PythonProcess"
           and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == "pandad"]
  assert len(calls) == 1
  should_run = calls[0].args[2] if len(calls[0].args) > 2 else next(k.value for k in calls[0].keywords if k.arg == "should_run")
  assert isinstance(should_run, ast.Name) and should_run.id == "pandad_run"


def test_no_flag_runs_pandad(flag):
  assert _call() is True


def test_fresh_flag_stops_pandad(flag):
  flag.write_text("1\n")
  assert _call() is False


def test_stale_flag_runs_pandad(flag):
  # a flag nobody renews (starviewd gone) must not keep pandad off
  flag.write_text("1\n")
  old = time.time() - 25  # noqa: TID251  file mtimes are wall clock
  os.utime(flag, (old, old))
  assert _call() is True


def test_agrees_with_flag_fresh(flag):
  flag.write_text("1\n")
  for age in (0, 5, 19, 21, 60):
    t = time.time() - age  # noqa: TID251
    os.utime(flag, (t, t))
    assert _call() is not session.flag_fresh(str(flag)), age
