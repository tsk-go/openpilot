"""StarView's tablet in openpilot's lane changes and turns, in one place (fork patches 2, 10, 38, 80).

Upstream's files only call in here, so a sync meets a few hook lines instead of our logic:
  selfdrive/modeld/modeld.py   `starview = DH.starview = StarViewLanes(CP.brand, navigation_turn)` once; every frame
                               `starview.before_turn(sm)` and `desire = starview.after_turn(desire, DH)` around
                               TurnIntent.select, and `starview.before_lane_change(...)` right before DH.update
  selfdrive/controls/lib/desire_helper.py   `self.starview = LaneInputs()` (no tablet: nothing changes),
                               `self.starview.begin(...)` at the top of update and `self.starview.pre_lane_change(...)`
                               in its preLaneChange step, just before it decides
  starpilot/navigation/intent.py   TurnIntent.signal_desire: no turn while `starview_no_turn`

What the tablet says (starviewd's files in /dev/shm):
  - why it holds the blinker (blinker_signal.py):
      "lane"  a lane change the driver confirmed on the tablet (tap, nudge or its countdown). It stands in for the nudge
              once per blinker hold, when the adjacent lane (the same check as an automatic lane change) and a clear
              blind spot have held for SETTLE_S, within CONFIRM_MAX_S. Confirmed while openpilot wasn't steering, or
              with the blind spot occupied: void (the driver nudges, or confirms again).
      "exit"  (patch 80) the route's exit taken from our own lane, before the ramp opens beside us: a signal only, no
              automatic lane change starts on it (a nudge still does). At the opening the tablet says "lane".
      "turn"  its blinker at the route's turn: a route turn, like upstream's (at speed it waits for the lane, and a lane
              change toward the turn may start), only with Galaxy's Automatic Turn Initiation on.
    "lane" and "exit" are never a turn (neither Turn Signal Guidance's nor the route's) and keep the lane change
    helper's desire.
  - whether its street map has a street to turn into on the blinker's side within 250 ft (blinker_turn.py, patch 38):
    "no" -> no turn from Turn Signal Guidance (pulling over). No say -> upstream as it is.
  - the nudge strength (nudge.py, patch 10, Toyota): the driver's torque toward that side held NUDGE_HOLD_S instead of
    the car's own steeringPressed. No setting -> the stock rule.
"""
from openpilot.cereal import log
from openpilot.common.realtime import DT_MDL
from openpilot.starpilot.system.starview.blinker_signal import StarViewSignal
from openpilot.starpilot.system.starview.blinker_turn import BlinkerTurn
from openpilot.starpilot.system.starview.nudge import NudgeSetting

LaneChangeState = log.LaneChangeState
LaneChangeDirection = log.LaneChangeDirection

SETTLE_S = 0.5          # the adjacent lane seen with the blind spot clear this long ...
CONFIRM_MAX_S = 5.0     # ... within this long of the tablet's confirmation
NUDGE_HOLD_S = 0.15     # StarView's nudge strength: the torque held this long
NOT_A_TURN = ("lane", "exit")


class LaneInputs:
  """DesireHelper's side (DesireHelper.starview). As made, it is "no tablet": update runs exactly as upstream's."""

  def __init__(self):
    self.why = None             # the tablet's reason for this blinker: "lane", "exit", "turn"; None or "" = none
    self.evidence = False       # the adjacent lane is there (for "lane")
    self.nudge_torque = None    # StarView's nudge strength in the car's torque units; None = the stock rule
    self.nudge_s = 0.0
    self.started_on_lane = False
    self.reset()

  def reset(self):
    self.confirm_used = False
    self.pending_s = 0.0
    self.clear_s = 0.0

  @property
  def lane(self) -> bool:
    return self.why == "lane"

  def automatic_turns(self) -> bool:
    """Galaxy's Automatic Turn Initiation (StarViewLanes reads it from TurnIntent)."""
    return False

  def begin(self, dh, carstate, lateral_active, engaged, navigation_turn, route_turn=False):
    """First thing in DesireHelper.update. Returns its (navigation_turn, route_turn) as the tablet changes them: a blinker
    the tablet holds for a lane change or our lane's exit is neither a turn (upstream's forecast) nor the route's turn;
    the tablet's "turn" is a route turn (since upstream's Nov 24 route turns: it may change lanes toward the turn at
    speed, waiting for the lane like the comma's own route), only with Automatic Turn Initiation on."""
    if self.started_on_lane and dh.lane_change_state == LaneChangeState.laneChangeStarting:
      self.confirm_used = True    # the last frame started a lane change: one per confirmation, however it started
    self.started_on_lane = False
    if dh.lane_change_state == LaneChangeState.off:
      self.nudge_s = 0.0          # a new wait for the nudge
    if not carstate.leftBlinker and not carstate.rightBlinker:
      self.reset()
    if self.lane and (not lateral_active or not engaged):
      self.confirm_used = True
    if self.why in NOT_A_TURN:
      return False, False
    return navigation_turn, route_turn or (self.why == "turn" and self.automatic_turns())

  def pre_lane_change(self, dh, carstate, blindspot_detected, torque_applied, auto_ready):
    """In DesireHelper.update's preLaneChange step, just before it decides. Returns (torque_applied, auto_ready)."""
    if self.nudge_torque is not None:
      toward = ((carstate.steeringTorque > 0 and dh.lane_change_direction == LaneChangeDirection.left) or
                (carstate.steeringTorque < 0 and dh.lane_change_direction == LaneChangeDirection.right))
      self.nudge_s = self.nudge_s + DT_MDL if toward and abs(carstate.steeringTorque) >= self.nudge_torque else 0.0
      torque_applied = self.nudge_s >= NUDGE_HOLD_S - 1e-6
    if self.why == "exit":
      dh.pre_lane_change_timer = 0.0
      auto_ready = False
    if self.lane and not self.confirm_used:
      self.pending_s += DT_MDL
      self.clear_s = self.clear_s + DT_MDL if self.evidence and not blindspot_detected else 0.0
      if blindspot_detected or self.pending_s > CONFIRM_MAX_S:
        self.confirm_used = True
      elif self.clear_s >= SETTLE_S:
        torque_applied = True     # the confirmation stands in for the nudge
    self.started_on_lane = self.lane
    return torque_applied, auto_ready


class StarViewLanes(LaneInputs):
  """modeld's side: reads the tablet's files once a frame and hands what they say to TurnIntent and DesireHelper."""

  def __init__(self, brand: str, turn_intent):
    super().__init__()
    self.turn_intent = turn_intent
    self.signal = StarViewSignal()
    self.street = BlinkerTurn()
    self.nudge = NudgeSetting(brand)

  def automatic_turns(self) -> bool:
    return self.turn_intent.automatic_turn_enabled

  def before_turn(self, sm):
    """Before TurnIntent.select."""
    car_state = sm['carState']
    self.why = self.signal.for_blinker(car_state)
    self.turn_intent.starview_no_turn = self.why in NOT_A_TURN or self.street.for_blinker(car_state) == "no"

  def after_turn(self, desire, dh):
    """After TurnIntent.select: a lane change or our lane's exit keeps the lane change helper's desire (TurnIntent
    keeps its stop latch)."""
    return dh.desire if self.why in NOT_A_TURN else desire

  def before_lane_change(self, sm, model_msg, direction, policy, clock_guard, vehicle_capable,
                         mono_now_ns, boot_now_ns, clock_skew_ns):
    """Right before DesireHelper.update: the adjacent lane for the tablet's "lane", and the nudge strength."""
    from openpilot.starpilot.lateral.auto_lane_change import auto_evidence   # modeld has it loaded already
    self.evidence = bool(self.lane and direction != 0 and
                         clock_guard.ready(sm, mono_now_ns, boot_now_ns, clock_skew_ns) and
                         auto_evidence(sm, model_msg.modelV2, direction, policy.minimum_lane_width_m,
                                       now_mono_ns=mono_now_ns, now_boot_ns=boot_now_ns,
                                       model_valid=bool(model_msg.valid), vehicle_capable=vehicle_capable))
    self.nudge_torque = self.nudge.torque()
