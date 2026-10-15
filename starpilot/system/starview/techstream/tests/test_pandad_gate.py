"""system/manager/process_config.py's pandad_run keeps pandad stopped while TechStream's flag file is fresh.

process_config.py is too heavy to import off-device (cereal, Params, hardware), so the function's source is pulled out
with ast and run with only os/time injected.
"""
import ast
import os
import time
from pathlib import Path

import pytest

from openpilot.starpilot.system.starview.techstream.session import DIAG_FLAG, FLAG_FRESH_S

PROCESS_CONFIG = Path(__file__).resolve().parents[5] / "system" / "manager" / "process_config.py"


@pytest.fixture(scope="module")
def tree_and_source():
  source = PROCESS_CONFIG.read_text()
  return ast.parse(source), source


def _pandad_run_node(tree) -> ast.FunctionDef:
  return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "pandad_run")


def _load_pandad_run(tree_and_source, flag_path: str):
  tree, source = tree_and_source
  node = _pandad_run_node(tree)
  # drop the annotations (Params, car.CarParams, SimpleNamespace aren't imported here) by re-parsing just the function
  func_source = ast.get_source_segment(source, node)
  assert DIAG_FLAG in func_source
  func = ast.parse(func_source.replace(f'"{DIAG_FLAG}"', repr(flag_path))).body[0]
  for arg in func.args.args:
    arg.annotation = None
  func.returns = None
  namespace = {"os": os, "time": time}
  exec(compile(ast.Module(body=[func], type_ignores=[]), str(PROCESS_CONFIG), "exec"), namespace)
  return namespace["pandad_run"]


def _call(pandad_run) -> bool:
  return pandad_run(True, None, None, None)


def test_uses_the_session_flag_and_window(tree_and_source):
  node = _pandad_run_node(tree_and_source[0])
  constants = [c.value for c in ast.walk(node) if isinstance(c, ast.Constant)]
  assert DIAG_FLAG in constants
  assert FLAG_FRESH_S in constants and FLAG_FRESH_S == 20


def test_pandad_process_uses_pandad_run(tree_and_source):
  tree, _ = tree_and_source
  calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "PythonProcess"
           and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == "pandad"]
  assert len(calls) == 1
  should_run = calls[0].args[2] if len(calls[0].args) > 2 else next(k.value for k in calls[0].keywords if k.arg == "should_run")
  assert isinstance(should_run, ast.Name) and should_run.id == "pandad_run"


def test_no_flag_runs_pandad(tree_and_source, tmp_path):
  assert _call(_load_pandad_run(tree_and_source, str(tmp_path / "starview_diag"))) is True


def test_fresh_flag_stops_pandad(tree_and_source, tmp_path):
  flag = tmp_path / "starview_diag"
  flag.write_text("1\n")
  assert _call(_load_pandad_run(tree_and_source, str(flag))) is False


def test_stale_flag_runs_pandad(tree_and_source, tmp_path):
  # a flag nobody renews (starviewd gone) must not keep pandad off
  flag = tmp_path / "starview_diag"
  flag.write_text("1\n")
  old = time.time() - 25  # noqa: TID251  file mtimes are wall clock
  os.utime(flag, (old, old))
  assert _call(_load_pandad_run(tree_and_source, str(flag))) is True


def test_agrees_with_flag_fresh(tree_and_source, tmp_path):
  from openpilot.starpilot.system.starview.techstream.session import flag_fresh
  flag = tmp_path / "starview_diag"
  pandad_run = _load_pandad_run(tree_and_source, str(flag))
  flag.write_text("1\n")
  for age in (0, 5, 19, 21, 60):
    t = time.time() - age  # noqa: TID251
    os.utime(flag, (t, t))
    assert _call(pandad_run) is not flag_fresh(str(flag)), age
