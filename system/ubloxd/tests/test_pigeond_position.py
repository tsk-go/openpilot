import json
import struct

from openpilot.system.ubloxd.pigeond import LAST_POSITION_ACCURACY_CM, LAST_POSITION_MAX_AGE, add_ubx_checksum, last_position_message

NOW = 1_791_950_000.0
SAVED = {"latitude": 40.6269199, "longitude": -73.749655, "bearing": 90.0, "speed": 0.0, "hasFix": True,
         "updatedAtMonotonic": 1.0, "updatedAtSec": NOW - 3600}


def test_last_position_is_sent_as_mga_ini_pos_llh():
  msg = last_position_message(json.dumps(SAVED), NOW)
  assert msg is not None
  assert msg[:6] == b"\xB5\x62\x13\x40\x14\x00"  # UBX-MGA-INI, 20 bytes
  assert len(msg) == 6 + 20 + 2
  assert add_ubx_checksum(msg[:-2]) == msg
  kind, version, lat, lon, alt, acc = struct.unpack("<BB2xiiiI", msg[6:-2])
  assert (kind, version) == (0x01, 0x00)  # POS_LLH
  assert lat == round(40.6269199 * 1e7) and lon == round(-73.749655 * 1e7) and alt == 0
  assert acc == LAST_POSITION_ACCURACY_CM == 10_000_000
  # bytes and an already parsed dict work the same
  assert last_position_message(json.dumps(SAVED).encode(), NOW) == msg
  assert last_position_message(SAVED, NOW) == msg


def test_last_position_skipped_when_not_usable():
  assert last_position_message(None, NOW) is None
  assert last_position_message("", NOW) is None
  assert last_position_message("not json", NOW) is None
  assert last_position_message(dict(SAVED, hasFix=False), NOW) is None
  assert last_position_message(dict(SAVED, latitude=0.0, longitude=0.0), NOW) is None
  assert last_position_message(dict(SAVED, latitude=float("nan")), NOW) is None
  assert last_position_message(dict(SAVED, latitude=95.0), NOW) is None
  # older than a week, no save time, or saved in the future (a bad clock) -> unknown, skipped
  assert last_position_message(dict(SAVED, updatedAtSec=NOW - LAST_POSITION_MAX_AGE - 1), NOW) is None
  assert last_position_message(dict(SAVED, updatedAtSec=0), NOW) is None
  assert last_position_message({k: v for k, v in SAVED.items() if k != "updatedAtSec"}, NOW) is None
  assert last_position_message(dict(SAVED, updatedAtSec=NOW + 7200), NOW) is None
