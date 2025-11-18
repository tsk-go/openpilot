from cereal import log
from openpilot.common.params import Params
from openpilot.common.realtime import DT_MDL
from openpilot.common.numpy_fast import interp
from openpilot.common.conversions import Conversions as CV

# State machine for the intelligent auto lane change
class IntelligentALCState:
  IDLE = 0
  EVALUATING = 1
  REQUESTING = 2
  EXECUTING = 3
  COOLDOWN = 4

class IntelligentAutoLaneChange:
  def __init__(self, DH):
    self.DH = DH
    self.params = Params()
    self.state = IntelligentALCState.IDLE
    self.timer = 0.0
    self.direction = log.LaneChangeDirection.none
    self.enabled = False
    self.min_speed = 30.0 * CV.MPH_TO_MS
    self.speed_delta = 5.0 * CV.MPH_TO_MS
    self.evaluation_time = 2.0
    self.cooldown_time = 10.0
    self.min_lead_distance = 20.0
    self.max_lead_distance = 100.0

    self.read_params()

  def read_params(self):
    self.enabled = self.params.get_bool("IntelligentAutoLaneChangeEnabled")

  def update(self, CS, model_v2, long_plan, lateral_active):
    if not self.enabled:
      self.state = IntelligentALCState.IDLE
      return log.LaneChangeDirection.none

    # 1. Check Pre-conditions
    v_ego = CS.vEgo
    if v_ego < self.min_speed:
      self.state = IntelligentALCState.IDLE
      return log.LaneChangeDirection.none

    # Get Lead Info (Vision-Only)
    lead = model_v2.leadOne
    if not lead.status:
      self.state = IntelligentALCState.IDLE
      return log.LaneChangeDirection.none

    # Check if we are following a slower car
    v_cruise = CS.cruiseState.speed
    v_lead = lead.vLead
    d_lead = lead.dRel

    is_slower_lead = (v_cruise > v_lead + self.speed_delta)
    is_too_close = (d_lead < self.min_lead_distance)
    is_too_far = (d_lead > self.max_lead_distance)

    if not is_slower_lead or is_too_close or is_too_far:
      self.state = IntelligentALCState.IDLE
      return log.LaneChangeDirection.none

    # 2. State Machine
    if self.state == IntelligentALCState.IDLE:
      # Start evaluation if all pre-conditions are met
      self.state = IntelligentALCState.EVALUATING
      self.timer = 0.0
      self.direction = log.LaneChangeDirection.none

    elif self.state == IntelligentALCState.EVALUATING:
      self.timer += DT_MDL
      if self.timer >= self.evaluation_time:
        # Evaluation complete, check for safe lane
        self.direction = self._get_safe_lane_direction(CS, model_v2)
        if self.direction != log.LaneChangeDirection.none:
          self.state = IntelligentALCState.REQUESTING
        else:
          self.state = IntelligentALCState.IDLE # Failed to find safe lane

    elif self.state == IntelligentALCState.REQUESTING:
      # Requesting a lane change. The DH will pick this up.
      self.state = IntelligentALCState.EXECUTING
      self.DH.alc.lane_change_wait_timer = self.DH.alc.lane_change_delay + 1.0 # Force immediate start
      return self.direction

    elif self.state == IntelligentALCState.EXECUTING:
      # Wait for the DH to complete the lane change
      if self.DH.lane_change_state == log.LaneChangeState.off:
        self.state = IntelligentALCState.COOLDOWN
        self.timer = 0.0
        self.direction = log.LaneChangeDirection.none
      return log.LaneChangeDirection.none

    elif self.state == IntelligentALCState.COOLDOWN:
      self.timer += DT_MDL
      if self.timer >= self.cooldown_time:
        self.state = IntelligentALCState.IDLE
      return log.LaneChangeDirection.none

    return log.LaneChangeDirection.none

  def _get_safe_lane_direction(self, CS, model_v2):
    # Simplified safety check: prefers left lane (passing lane)
    # Check if left lane is available and safe (no car in blind spot)

    # Check for left lane
    if model_v2.meta.leftLaneEdgeDetected:
      # Check if left blind spot is clear (assuming carState has BSM info)
      if not CS.leftBlindspot:
        # Check if the lane is clear ahead (vision model can predict this)
        # For simplicity, we assume if BSM is clear, the lane is safe to enter
        return log.LaneChangeDirection.left

    # Check for right lane (less preferred)
    if model_v2.meta.rightLaneEdgeDetected:
      if not CS.rightBlindspot:
        return log.LaneChangeDirection.right

    return log.LaneChangeDirection.none
