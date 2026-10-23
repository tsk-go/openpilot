import os
import tempfile
import unittest

from openpilot.starpilot.system.starview import lane_one_line


class TestLaneOneLine(unittest.TestCase):
  def test_off_by_default_on_and_back_off(self):
    with tempfile.TemporaryDirectory() as d:
      path = os.path.join(d, "starview", "lane_one_line")
      self.assertFalse(lane_one_line.read(path))
      self.assertTrue(lane_one_line.write(True, path))
      self.assertTrue(lane_one_line.read(path))
      self.assertFalse(lane_one_line.write(False, path))
      self.assertFalse(os.path.exists(path))
      self.assertFalse(lane_one_line.write(False, path))   # already off

  def test_only_true_or_false(self):
    with tempfile.TemporaryDirectory() as d:
      for bad in ("1", 1, None):
        with self.assertRaises(ValueError):
          lane_one_line.write(bad, os.path.join(d, "x"))
