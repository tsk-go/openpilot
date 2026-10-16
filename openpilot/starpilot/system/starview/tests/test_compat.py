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
  s = compat.nav_instruction_state(_nav(), extra={"wazeFresh": False})
  assert s["valid"] and s["maneuverPrimaryText"] == "Avenue N"
  assert (s["maneuverType"], s["maneuverModifier"], s["maneuverDistance"]) == ("turn", "left", 120.0)
  assert s["nextManeuverModifier"] == "right" and s["updatedAtMonotonic"] == 5.0
  assert s["destination"] == "Home" and s["wazeFresh"] is False
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
