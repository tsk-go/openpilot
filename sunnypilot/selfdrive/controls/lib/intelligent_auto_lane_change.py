from cereal import log
from common.params import Params
from common.realtime import DT_MDL
from common.numpy_fast import interp
from common.conversions import Conversions as CV

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
    # This is the parameter we added to params_keys.h
    self.enabled = self.params.get_bool("IntelligentAutoLaneChangeEnabled")

  def should_trigger_lane_change(self):
    return self.state == IntelligentALCState.REQUESTING

  def get_lane_change_direction(self):
    return self.direction

  def mark_lane_change_started(self):
    self.state = IntelligentALCState.EXECUTING
    self.timer = 0.0

  def mark_lane_change_complete(self):
    self.state = IntelligentALCState.COOLDOWN
    self.timer = 0.0
    self.direction = log.LaneChangeDirection.none

  def _check_safety(self, CS, model_v2, target_direction):
    # 1. Speed Check
    if CS.vEgo < self.min_speed or CS.vEgo > 80.0 * CV.MPH_TO_MS:
      return False

    # 2. Blind Spot Check (using carstate)
    if target_direction == log.LaneChangeDirection.left and CS.leftBlindspot:
      return False
    if target_direction == log.LaneChangeDirection.right and CS.rightBlindspot:
      return False

    # 3. Lane Line Confidence (Vision Model)
    # Check if the target lane line is reasonably visible
    if target_direction == log.LaneChangeDirection.left:
      # Left lane line is index 0 (or 1 depending on fork, using 0 for left boundary)
      target_line_prob = model_v2.laneLineProbs[0]
    else:
      # Right lane line is index 3 (or 2 for right boundary)
      target_line_prob = model_v2.laneLineProbs[3]
      
    if target_line_prob < 0.5:
      return False
      
    # 4. Target Lane Clearance (Simplified: relies on BSM)
    # For a full implementation, this would check the model's path for objects in the target lane.
    # We rely on the BSM check (2) for immediate safety.

    return True

  def _check_trigger_conditions(self, CS, model_v2):
    # 1. Feature Enabled
    if not self.enabled:
      return log.LaneChangeDirection.none

    # 2. Cruise Control Active
    if not CS.cruiseState.enabled:
      return log.LaneChangeDirection.none

    # 3. Lead Vehicle Check (VISION-ONLY)
    # Use modelV2.leadOne for vision-based lead
    lead = model_v2.leadOne
    if not lead.status:
      return log.LaneChangeDirection.none

    # 4. Speed Difference Check (Set speed > Current speed + delta)
    # CS.vCruise is in KPH, CS.vEgo is in m/s. Convert vCruise to m/s.
    if CS.vCruise * CV.KPH_TO_MS < CS.vEgo + self.speed_delta:
      return log.LaneChangeDirection.none

    # 5. Lead Distance Check
    if not (self.min_lead_distance < lead.dRel < self.max_lead_distance):
      return log.LaneChangeDirection.none

    # 6. Check Target Lane Availability (Prefer Left for passing)
    
    # Check Left Lane
    if self._check_safety(CS, model_v2, log.LaneChangeDirection.left):
      return log.LaneChangeDirection.left
      
    # Check Right Lane (if left is not available)
    if self._check_safety(CS, model_v2, log.LaneChangeDirection.right):
      return log.LaneChangeDirection.right

    return log.LaneChangeDirection.none

  def update(self, CS, model_v2, long_plan, lateral_active):
    self.read_params()
    self.timer += DT_MDL

    if not lateral_active:
      self.state = IntelligentALCState.IDLE
      self.timer = 0.0
      return

    if self.state == IntelligentALCState.IDLE:
      self.direction = self._check_trigger_conditions(CS, model_v2)
      if self.direction != log.LaneChangeDirection.none:
        self.state = IntelligentALCState.EVALUATING
        self.timer = 0.0

    elif self.state == IntelligentALCState.EVALUATING:
      # Re-check safety continuously
      if self._check_safety(CS, model_v2, self.direction):
        if self.timer > self.evaluation_time:
          self.state = IntelligentALCState.REQUESTING
          self.timer = 0.0
      else:
        # Safety check failed, return to IDLE
        self.state = IntelligentALCState.IDLE
        self.direction = log.LaneChangeDirection.none
        self.timer = 0.0

    elif self.state == IntelligentALCState.REQUESTING:
      pass

    elif self.state == IntelligentALCState.EXECUTING:
      # If the maneuver takes too long, abort and go to cooldown
      if self.timer > 10.0:
        self.mark_lane_change_complete()

    elif self.state == IntelligentALCState.COOLDOWN:
      if self.timer > self.cooldown_time:
        self.state = IntelligentALCState.IDLE
        self.timer = 0.0
