"""StarView's door frames in the Toyota safety (modes/toyota_starview.h, fork patches 46-49 and 53): the start frames
behind upstream's stationary gate, the hand-back and lock-state read frames always (relay fine), nothing else. Moved
here from test_toyota.py's TestToyotaSafetyBase so upstream's file stays as it is; they run on every Toyota safety
variant test_toyota.py runs (as they did there), and only ours - upstream's own run in test_toyota.py."""
import unittest

from opendbc.safety.tests import test_toyota


class StarViewDoorFrames:
  UDS_DOOR_START = (b"\x40\x02\x10\x03\x00\x00\x00\x00", b"\x40\x06\x2f\x28\x10\x03\x01\x80",
                    b"\x40\x06\x2f\x28\x11\x03\x01\x80", b"\x40\x06\x2f\x28\x4a\x03\x01\x80",
                    b"\x40\x06\x2f\x28\x02\x03\x01\x80")
  UDS_DOOR_RETURN = (b"\x40\x05\x2f\x28\x10\x00\x80\x00", b"\x40\x05\x2f\x28\x11\x00\x80\x00",
                     b"\x40\x05\x2f\x28\x4a\x00\x80\x00", b"\x40\x05\x2f\x28\x02\x00\x80\x00",
                     b"\x40\x02\x10\x01\x00\x00\x00\x00", b"\x40\x02\x3e\x00\x00\x00\x00\x00",
                     # StarLock's lock state reads (22 101A / 1019 / 101B / 101C / 101E)
                     b"\x40\x03\x22\x10\x1a\x00\x00\x00", b"\x40\x03\x22\x10\x19\x00\x00\x00",
                     b"\x40\x03\x22\x10\x1b\x00\x00\x00", b"\x40\x03\x22\x10\x1c\x00\x00\x00",
                     b"\x40\x03\x22\x10\x1e\x00\x00\x00")

  def test_uds_door_start_frames_follow_the_stationary_gate(self):
    for data in self.UDS_DOOR_START:
      self.safety.set_safety_hooks(self.SAFETY_MODEL, self.SAFETY_PARAM)
      self.safety.set_timer(1_000_000)
      self.assertFalse(self._tx(self._body_command(data)))
      self._body_required_rx()
      self.assertTrue(self._tx(self._body_command(data)))
      self.assertTrue(self._rx(self._user_gas_msg(1)))
      self.assertFalse(self._tx(self._body_command(data)))
      self.assertTrue(self._rx(self._user_gas_msg(0)))
      self.assertTrue(self._rx(self._speed_msg(1)))
      self.assertFalse(self._tx(self._body_command(data)))
      self.assertTrue(self._rx(self._speed_msg(0)))
      self.assertTrue(self._tx(self._body_command(data)))
      for bus in (1, 2):
        self.assertFalse(self._tx(self._body_command(data, bus)))
      for index in range(8):
        changed = bytes(data[:index]) + bytes([data[index] ^ 1]) + bytes(data[index + 1:])
        # one bit turns lock into unlock (2810 <-> 2811): only frames on the list get through
        self.assertEqual(self._tx(self._body_command(changed)), changed in self.UDS_DOOR_START + self.UDS_DOOR_RETURN)

  def test_uds_door_return_frames_are_allowed_even_moving_but_nothing_else(self):
    self.safety.set_timer(1_000_000)
    for data in self.UDS_DOOR_RETURN:
      self.assertTrue(self._tx(self._body_command(data)))       # no witnesses yet: handing back is still fine
    self._body_required_rx()
    self.assertTrue(self._rx(self._speed_msg(10)))
    for data in self.UDS_DOOR_RETURN:
      self.assertTrue(self._tx(self._body_command(data)))
      self.assertFalse(self._tx(self._body_command(data, 1)))
    # other services / DIDs / sub-addresses stay blocked
    for data in (b"\x40\x02\x10\x02\x00\x00\x00\x00", b"\x40\x02\x11\x01\x00\x00\x00\x00",
                 b"\x40\x05\x2f\x28\x12\x00\x80\x00", b"\x40\x06\x2f\x28\x12\x03\x01\x80",
                 b"\x41\x02\x10\x01\x00\x00\x00\x00", b"\x40\x04\x2e\x28\x10\x01\x00\x00",
                 b"\x40\x06\x2f\x28\x04\x03\x01\x80", b"\x40\x06\x2f\x28\x41\x03\x01\x80",   # siren, window
                 b"\x40\x06\x2f\x28\x03\x03\x01\x80",                                                  # security horn
                 b"\x40\x03\x22\x10\x18\x00\x00\x00", b"\x40\x03\x22\x10\x1d\x00\x00\x00",   # other reads
                 b"\x40\x03\x22\xf1\x90\x00\x00\x00", b"\x40\x03\x22\x10\x1a\x01\x00\x00",
                 b"\x40\x04\x22\x10\x1a\x00\x00\x00", b"\x41\x03\x22\x10\x1a\x00\x00\x00"):
      self.assertFalse(self._tx(self._body_command(data)))
    self.safety.set_relay_malfunction(True)
    self.assertFalse(self._tx(self._body_command(self.UDS_DOOR_RETURN[0])))
    self.safety.set_relay_malfunction(False)


OURS = tuple(name for name in vars(StarViewDoorFrames) if name.startswith("test"))


def _variants():
  for name, cls in vars(test_toyota).items():
    if (isinstance(cls, type) and issubclass(cls, test_toyota.TestToyotaSafetyBase) and name.startswith("Test") and
        not name.endswith("Base")):
      yield name, cls


for _name, _cls in _variants():
  _hidden = {test: None for test in dir(_cls) if test.startswith("test") and test not in OURS}
  globals()[_name + "StarView"] = type(_name + "StarView", (StarViewDoorFrames, _cls), _hidden)
del _name, _cls, _hidden


if __name__ == "__main__":
  unittest.main()
