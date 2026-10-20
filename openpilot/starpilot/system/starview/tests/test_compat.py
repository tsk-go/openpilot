"""StarView's 7.0 compatibility layer: the tablet's names, the rebuilt starpilotPlan, NavInstructionState."""
import json

from openpilot.cereal import messaging
from openpilot.starpilot.system.starview import compat


def test_renamed_services_map_to_70():
  assert compat.sources("roadCameraState") == ("narrowRoadCameraState",)
  assert compat.sources("liveCalibration") == ("extrinsicsCalibration",)
  assert compat.sources("livePose") == ("deviceMotion",)
  assert compat.sources("carState") == ("carState",)
  assert compat.known("liveTracks") and compat.known("starpilotPlan")


def test_reused_ordinals_never_reach_an_old_tablet():
  # Event @110 was starpilotDeviceState and is starpilotLongitudinalPlan now: an old tablet would misread it
  for name in ("starpilotDeviceState", "starpilotLongitudinalPlan", "starpilotOnroadEvents", "customReserved6"):
    assert not compat.known(name)
    assert compat.sources(name) == ()
  assert "starpilotLongitudinalPlan" not in compat.tablet_services()
  assert "roadCameraState" in compat.tablet_services() and "starpilotPlan" in compat.tablet_services()


def test_translator_delivers_under_the_tablets_name():
  t = compat.Translator()
  opened = t.route({"roadCameraState", "carState"})
  assert opened == {"narrowRoadCameraState", "carState"}
  out = t.feed("narrowRoadCameraState", [b"a", b"b"], now=1.0)
  assert out == [("roadCameraState", [b"a", b"b"])]
  assert t.feed("radarState", [b"x"], now=1.0) == []      # not asked for


def _slc():
  m = messaging.new_message("slcState")
  s = m.slcState
  s.hasAccepted = True
  s.acceptedSpeedLimit = 20.0
  s.offset = 2.0
  s.acceptedSource = "map"
  s.hasPending = True
  s.pendingSpeedLimit = 25.0
  s.curve.hasCeiling = True
  s.curve.ceilingMps = 12.5
  s.curve.controlling = True
  s.curve.hasRoadCurvature = True
  s.curve.roadCurvature = 0.01
  s.conditionalMode.experimental = True
  s.conditionalMode.statusCode = 8
  return m.to_bytes()


def test_starpilot_plan_is_rebuilt_in_the_old_layout():
  t = compat.Translator(toggles=lambda: {"minimum_lane_change_speed": 2.2})
  t.route({"starpilotPlan"})
  lp = messaging.new_message("starpilotLongitudinalPlan")
  lp.starpilotLongitudinalPlan.forceStopHolding = True
  assert t.feed("starpilotLongitudinalPlan", [lp.to_bytes()], now=1.0) == []   # waits for slcState
  out = t.feed("slcState", [_slc()], now=1.0)
  assert [n for n, _ in out] == ["starpilotPlan"]
  evt = messaging.log_from_bytes(out[0][1][0])
  assert evt.which() == "customReserved6"      # Event @113 = the old starpilotPlan
  p = evt.customReserved6
  assert p.slcSpeedLimit == 20.0 and p.slcSpeedLimitOffset == 2.0 and p.slcSpeedLimitSource == "map"
  assert p.slcNextSpeedLimit == 25.0
  assert p.cscSpeed == 12.5 and p.cscControllingSpeed and abs(p.roadCurvature - 0.01) < 1e-6
  assert p.experimentalMode and p.forcingStop
  assert json.loads(p.starpilotToggles) == {"minimum_lane_change_speed": 2.2}
  # at most 20 Hz
  assert t.feed("slcState", [_slc()], now=1.01) == []
  assert len(t.feed("slcState", [_slc()], now=1.06)) == 1


def _nav(status="guiding"):
  m = messaging.new_message("starpilotNavigation")
  n = m.starpilotNavigation.navigation
  n.version = 2
  n.enabled = True
  n.status = status
  n.frameMonoTime = 5_000_000_000
  n.destinationName = "Home"
  n.instruction.text = "Avenue N"
  n.instruction.maneuverType = "turn"
  n.instruction.maneuverModifier = "left"
  n.instruction.distanceMeters = 120.0
  n.nextManeuver.maneuverType = "turn"
  n.nextManeuver.maneuverModifier = "right"
  n.nextManeuver.distanceMeters = 400.0
  return messaging.log_from_bytes(m.to_bytes()).starpilotNavigation.navigation


def test_nav_instruction_state_from_70_navigation():
  s = compat.nav_instruction_state(_nav())
  assert s["valid"] and s["maneuverPrimaryText"] == "Avenue N"
  assert (s["maneuverType"], s["maneuverModifier"], s["maneuverDistance"]) == ("turn", "left", 120.0)
  assert s["nextManeuverModifier"] == "right" and s["updatedAtMonotonic"] == 5.0
  assert s["destination"] == "Home"
  assert compat.nav_instruction_state(_nav("routing")) is None


def test_mem_params_keep_the_tablets_own_writes():
  m = compat.MemParams()
  m.put("NavInstructionCollapsed", True)
  assert m.get("NavInstructionCollapsed") is True
  m.remove("NavInstructionCollapsed")
  assert m.get("NavInstructionCollapsed") is None
  assert m.get("CEStatus", default=0) == 0       # no slcState yet


def test_onroad_is_not_offroad():
  class P:
    def __init__(self, off): self.off = off
    def get_bool(self, k): return self.off if k == "IsOffroad" else False
  assert compat.is_onroad(P(False)) and not compat.is_onroad(P(True))


def _slc_with_readings(**readings):
  m = messaging.new_message("slcState")
  rows = m.slcState.init("sourceReadings", len(readings))
  for row, (src, v) in zip(rows, readings.items(), strict=True):
    row.source, row.enabled, row.observationKind, row.speedLimit = src, True, "valid" if v else "absent", v
  return m


def test_speed_limit_sources_card_gets_map_and_vision():
  raw = _slc_with_readings(dashboard=0.0, map=24.6, vision=22.4).to_bytes()
  slc = messaging.log_from_bytes(raw).slcState
  assert abs(compat.slc_reading(slc, "map") - 24.6) < 1e-4
  assert compat.slc_reading(slc, "dashboard") == 0.0                       # absent: no number
  plan = messaging.log_from_bytes(compat.build_plan(slc, None, "{}")).customReserved6
  assert abs(plan.slcMapSpeedLimit - 24.6) < 1e-4
  mp = compat.MemParams()
  mp.source = lambda service: (0.0, messaging.log_from_bytes(raw)) if service == "slcState" else None
  assert abs(mp.get("VisionSpeedLimit") - 22.4) < 1e-4


def test_adjacent_cars_fill_the_old_lead_left_right():
  m = messaging.new_message("starpilotRadarState")
  m.logMonoTime = 123
  q = m.starpilotRadarState.qualifiedAdjacent
  q.status = "clear"
  q.left.present, q.left.trackId, q.left.distanceM, q.left.lateralM, q.left.speedMps = True, 7, 31.0, 3.4, 27.0
  out = messaging.log_from_bytes(compat.adjacent_leads(m.to_bytes(), v_ego=25.0))
  r = out.starpilotRadarState
  assert out.logMonoTime == 123 and r.leadLeft.status and not r.leadRight.status
  assert (r.leadLeft.dRel, r.leadLeft.yRel, r.leadLeft.vLead) == (31.0, r.leadLeft.yRel, 27.0) and abs(r.leadLeft.yRel - 3.4) < 1e-5
  assert abs(r.leadLeft.vRel - 2.0) < 1e-5 and r.qualifiedAdjacent.left.trackId == 7
  empty = messaging.new_message("starpilotRadarState").to_bytes()
  assert compat.adjacent_leads(empty) == empty                              # nothing to add: passed through as is
  assert compat.adjacent_leads(b"junk") == b"junk"


def test_translator_rewrites_radar_state_and_learns_speed():
  t = compat.Translator()
  t.route({"starpilotRadarState", "carState"})
  cs = messaging.new_message("carState")
  cs.carState.vEgo = 20.0
  t.feed("carState", [cs.to_bytes()], 1.0)
  m = messaging.new_message("starpilotRadarState")
  m.starpilotRadarState.qualifiedAdjacent.right.present = True
  m.starpilotRadarState.qualifiedAdjacent.right.speedMps = 18.0
  (name, msgs), = t.feed("starpilotRadarState", [m.to_bytes()], 1.1)
  r = messaging.log_from_bytes(msgs[0]).starpilotRadarState
  assert name == "starpilotRadarState" and r.leadRight.status and abs(r.leadRight.vRel + 2.0) < 1e-5


def test_chestnut_state_like_the_comma_screen():
  cs = compat.chestnut_state
  # offroad
  assert cs(False, True, True, False, False, False, False, None, False, alert=True) == "failed"
  assert cs(False, False, False, False, False, False, False, None, False, alert=False) == "disconnected"
  assert cs(False, True, True, False, False, False, False, None, False, alert=False) == "ready"
  # driving
  assert cs(True, True, True, True, True, True, True, True, False, False) == "active"
  assert cs(True, True, True, True, False, True, False, None, False, False) == "failed"      # small model driving
  assert cs(True, True, True, False, False, False, False, None, True, False) == "loading"
  assert cs(True, False, True, False, False, True, True, True, False, False) == "failed"     # gone from USB
  assert cs(True, True, True, False, False, True, True, False, False, False) == "failed"     # modeld gave up
  assert cs(True, False, False, False, False, False, False, None, False, False) == "disconnected"


def test_gps_card_gets_only_the_satellite_reports():
  def ublox(kind):
    m = messaging.new_message("ubloxGnss")
    if kind == "sats":
      svs = m.ubloxGnss.init("satReport").init("svs", 2)
      svs[0].svId, svs[0].cno, svs[0].flagsBitfield = 12, 36, 0x0f
    else:
      m.ubloxGnss.init("measurementReport").numMeas = 20
    return m.to_bytes()
  t = compat.Translator()
  assert t.route({"ubloxGnss"}) == {"ubloxGnss"}
  sats, meas = ublox("sats"), ublox("meas")
  assert t.feed("ubloxGnss", [meas, sats, meas], now=1.0) == [("ubloxGnss", [sats])]
  assert t.feed("ubloxGnss", [meas, meas, b"junk"], now=1.1) == []
