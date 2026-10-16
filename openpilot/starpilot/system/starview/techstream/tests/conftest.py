"""Make the TechStream modules testable off-device.

api.py imports openpilot.common.swaglog, which needs zmq and the hardware paths. On a device (or a full dev setup) the real
module is used untouched; only when it can't be imported is a stand-in registered whose cloudlog is a plain logger.
"""
import logging
import sys
import types

import pytest


def _install_swaglog_stub() -> None:
  module = types.ModuleType("openpilot.common.swaglog")
  module.cloudlog = logging.getLogger("cloudlog")
  sys.modules["openpilot.common.swaglog"] = module


try:
  import openpilot.common.swaglog  # noqa: F401
except ImportError:
  _install_swaglog_stub()


@pytest.fixture(autouse=True)
def base_catalog(request):
  """toyopilot's tests replay a recorded Chinese-market Sienna that only knows the base catalog: run them without
  Toyota's extra settings. Tests marked toyota_extras get the full catalog."""
  from openpilot.starpilot.system.starview.techstream import catalog
  catalog.use_toyota_extras(request.node.get_closest_marker("toyota_extras") is not None)
  yield
  catalog.use_toyota_extras(True)


def pytest_configure(config):
  config.addinivalue_line("markers", "toyota_extras: use the catalog with Toyota's extra settings")
