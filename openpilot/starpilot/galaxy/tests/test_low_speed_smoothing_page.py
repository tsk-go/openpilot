"""tsk-go fork: Galaxy's "Low Speed Smoothing" switch on the 4th-gen Sienna's Driving controls page."""
import shutil
import tempfile
from pathlib import Path
from unittest import TestCase

from opendbc.car.car_helpers import interfaces
from opendbc.car.toyota.values import CAR as TOYOTA
from openpilot.starpilot.galaxy.settings import AuthorityContext
from openpilot.starpilot.galaxy.tests import test_settings as fixtures
from openpilot.starpilot.lateral import low_speed_smoothing as lss


class TestLowSpeedSmoothingPage(TestCase):
  setUp_gateway = fixtures.SettingsGatewayTest.setUp
  page = fixtures.SettingsGatewayTest.page

  def setUp(self):
    self.setUp_gateway()
    folder = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, folder, True)
    self.off_file = Path(folder) / "starview" / "low_speed_smoothing_off"
    self.addCleanup(setattr, lss, "OFF_FILE", lss.OFF_FILE)
    lss.OFF_FILE = str(self.off_file)
    self.car(TOYOTA.TOYOTA_SIENNA_4TH_GEN)

  def car(self, name, *, configurable=True, key=True):
    cp = interfaces[name].get_non_essential_params(name)
    cp.secOcKeyAvailable = key
    self.context.value = AuthorityContext(configurable, cp, cp.as_reader().as_builder().to_bytes())

  def row(self):
    page = self.page("torque")
    labels = [row["label"] for row in page["rows"]]
    index = labels.index("Low Speed Smoothing")
    return page, index, page["rows"][index], labels

  def flip(self, value):
    page, index, _, _ = self.row()
    intent = self.gateway.preview(page["view"], index, 0, self.session, self.generation, value=value)
    return self.gateway.confirm(intent["intent"], self.session, self.generation)

  def test_right_under_highway_smoothing_on_by_default(self):
    _, index, row, labels = self.row()
    self.assertEqual(labels[index - 1], "Highway Smoothing")
    self.assertEqual((row["value"], row["choices"], row["defaultValue"]), ("On", ["Off", "On"], "On"))
    self.assertTrue(row["available"])
    self.assertIn("below about 10 mph", row["reason"])
    self.assertIn("Turns, the blinker and lane changes are untouched", row["reason"])

  def test_off_and_on_again_through_galaxy(self):
    self.assertTrue(self.flip("Off"))
    self.assertTrue(self.off_file.exists())
    self.assertEqual(self.row()[2]["value"], "Off")
    self.assertTrue(self.row()[2]["resetAvailable"])
    self.assertTrue(self.flip("On"))
    self.assertFalse(self.off_file.exists())
    self.assertEqual(self.row()[2]["value"], "On")

  def test_works_while_driving(self):
    self.car(TOYOTA.TOYOTA_SIENNA_4TH_GEN, configurable=False)
    self.assertTrue(self.row()[2]["available"])
    self.assertTrue(self.flip("Off"))
    self.assertTrue(self.off_file.exists())

  def test_a_stale_tap_is_refused(self):
    page, index, _, _ = self.row()
    intent = self.gateway.preview(page["view"], index, 0, self.session, self.generation, value="Off")
    self.off_file.parent.mkdir(parents=True, exist_ok=True)
    self.off_file.write_text("off\n")          # switched off elsewhere (the tablet) in the meantime
    self.assertFalse(self.gateway.confirm(intent["intent"], self.session, self.generation))

  def test_no_row_without_steering(self):
    self.car(TOYOTA.TOYOTA_SIENNA_4TH_GEN, key=False)       # SecOC key not extracted: openpilot can't steer this van
    self.assertNotIn("Low Speed Smoothing", [row["label"] for row in self.page("torque")["rows"]])

  def test_other_cars_have_no_row(self):
    for name in (TOYOTA.TOYOTA_RAV4_TSS2, TOYOTA.TOYOTA_COROLLA_TSS2):
      self.car(name)
      self.assertNotIn("Low Speed Smoothing", [row["label"] for row in self.page("torque")["rows"]])
