"""Fork fix 6: map speed limits with the phone GPS handoff (StarView's RTK receiver). mapd writes gpsSource 4
(GpsSourcePhone) while Galaxy's GPS source uses the phone handoff; before `phone @4` in custom.capnp str() of it raised
and every such frame was dropped, so map speed limits never arrived (Nov 11). Moved here from upstream's
speed_limits/tests/test_map_source.py."""
import base64
import json
from dataclasses import replace
from pathlib import Path

from openpilot.starpilot.speed_limits import map_source as ms

ROOT = Path(__file__).resolve().parents[5]


def test_phone_gps_handoff_is_read_and_kept_by_its_own_age():
  fixture = json.loads((ROOT / 'mapd_repo/cereal/testdata/mapd_v1_wire.json').read_text())
  from openpilot.cereal import log
  with log.Event.from_bytes(base64.b64decode(fixture['event_base64'])) as event:
    builder = event.as_builder()
  builder.mapdOut.gpsSource = 'phone'
  builder.mapdOut.sampleVersion = 2
  frame = ms.decode_event(builder.to_bytes())
  assert frame.source == 'phone'
  now = frame.gps_mono_ns + 9_000_000_000
  frame = replace(frame, event_mono_ns=now - 10_000_000, computed_mono_ns=now - 20_000_000)
  assert ms.MapTracker().step(frame, received=True, now_boot_ns=now).kind == 'matched_limit_unqualified'
  assert ms.MapTracker().step(frame, received=True, now_boot_ns=frame.gps_mono_ns + 10_000_000_001).kind == 'stale'


def test_mapds_own_age_for_the_phone():
  # mapd_repo/cereal/gps.go phoneFixMaxAge: 10 s
  assert ms.GPS_MAX_AGE_NS['phone'] == 10_000_000_000
  assert 'phoneFixMaxAge' in (ROOT / 'mapd_repo/cereal/gps.go').read_text()
