"""Make the TechStream modules testable off-device.

api.py imports openpilot.common.swaglog, which needs zmq and the hardware paths. On a device (or a full dev setup) the real
module is used untouched; only when it can't be imported is a stand-in registered whose cloudlog is a plain logger.
"""
import logging
import sys
import types


def _install_swaglog_stub() -> None:
  module = types.ModuleType("openpilot.common.swaglog")
  module.cloudlog = logging.getLogger("cloudlog")
  sys.modules["openpilot.common.swaglog"] = module


try:
  import openpilot.common.swaglog  # noqa: F401
except ImportError:
  _install_swaglog_stub()
