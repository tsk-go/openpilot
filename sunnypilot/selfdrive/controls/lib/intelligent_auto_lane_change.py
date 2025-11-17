"""
Intelligent Automatic Lane Change Controller

This module implements automatic lane changing on highways when following a slower
vehicle, with comprehensive safety checks and state management.

Copyright (c) 2024
Licensed under the MIT License.
"""
from enum import IntEnum
from cereal import log
from openpilot.common.params import Params
from openpilot.common.realtime import DT_MDL
from openpilot.common.constants import CV

LaneChangeDirection = log.LaneChangeDirection
LaneChangeState = log.LaneChangeState


class IntelligentALCState(IntEnum):
    """State machine states for intelligent auto lane change"""
    IDLE = 0
    EVALUATING = 1
    REQUESTING = 2
    EXECUTING = 3
    COOLDOWN = 4


class IntelligentAutoLaneChange:
    """
    Intelligent Automatic Lane Change Controller
    
    Automatically initiates lane changes on highways when:
    - Following a slower vehicle
    - Set cruise speed is higher than current speed
    - Adjacent lanes are safe and clear
    """
    
    def __init__(self, desire_helper):
        self.DH = desire_helper
        self.params = Params()
        
        # Feature enable/disable
        self.enabled = False
        
        # Configuration parameters (with defaults)
        self.min_speed_mph = 30.0  # Minimum speed to activate (mph)
        self.min_speed_delta_mph = 5.0  # Minimum speed difference (mph)
        self.evaluation_time = 2.0  # Time to evaluate before triggering (seconds)
        self.cooldown_time = 10.0  # Time between automatic lane changes (seconds)
        self.request_delay = 0.5  # Delay after setting blinker (seconds)
        self.min_lead_distance = 20.0  # Minimum distance to lead vehicle (meters)
        self.min_gap_distance = 40.0  # Minimum gap in target lane (meters)
        self.max_speed_mph = 80.0  # Maximum speed for feature (mph)
        self.lane_line_confidence_threshold = 0.5
        self.min_edge_distance = 2.0  # Minimum distance to road edge (meters)
        
        # State machine
        self.state = IntelligentALCState.IDLE
        self.state_timer = 0.0
        
        # Lane change tracking
        self.selected_direction = LaneChangeDirection.none
        self.lane_change_triggered = False
        
        # Lead vehicle tracking
        self.lead_detected_timer = 0.0
        self.lead_stable_threshold = 3.0  # Seconds lead must be detected
        
        # Abort tracking
        self.abort_count = 0
        self.abort_count_timer = 0.0
        self.abort_count_window = 60.0  # 60 second window
        self.max_aborts_in_window = 3
        self.abort_disable_time = 300.0  # 5 minutes
        self.abort_disabled_timer = 0.0
        
        # Monitoring
        self.last_v_ego = 0.0
        self.last_lead_status = False
        
        # Parameter reading
        self.param_read_counter = 0
        
        self.read_params()
    
    def read_params(self) -> None:
        """Read configuration parameters from Params"""
        self.enabled = self.params.get_bool("IntelligentAutoLaneChangeEnabled")
        
        # Read custom thresholds if set
        min_speed = self.params.get("IntelligentALCMinSpeed")
        if min_speed is not None:
            try:
                self.min_speed_mph = float(min_speed)
            except (ValueError, TypeError):
                pass
        
        speed_delta = self.params.get("IntelligentALCSpeedDelta")
        if speed_delta is not None:
            try:
                self.min_speed_delta_mph = float(speed_delta)
            except (ValueError, TypeError):
                pass
    
    def update_params(self) -> None:
        """Periodically update parameters"""
        if self.param_read_counter % 100 == 0:  # Every 5 seconds at 20Hz
            self.read_params()
        self.param_read_counter += 1
    
    def update(self, car_state, radar_state, model_v2, longitudinal_plan, lateral_active: bool) -> None:
        """
        Main update function called every frame
        
        Args:
            car_state: Current vehicle state from CAN
            radar_state: Radar data with lead vehicle info
            model_v2: Vision model output
            longitudinal_plan: Longitudinal planning data
            lateral_active: Whether lateral control is active
        """
        self.update_params()
        
        # Check if feature is disabled due to too many aborts
        if self.abort_disabled_timer > 0:
            self.abort_disabled_timer = max(0, self.abort_disabled_timer - DT_MDL)
            if self.abort_disabled_timer == 0:
                self.abort_count = 0
            return
        
        # Update abort count window
        if self.abort_count > 0:
            self.abort_count_timer += DT_MDL
            if self.abort_count_timer >= self.abort_count_window:
                self.abort_count = 0
                self.abort_count_timer = 0.0
        
        # Store current values
        self.last_v_ego = car_state.vEgo
        self.last_lead_status = radar_state.leadOne.status
        
        # Update lead detection timer
        if radar_state.leadOne.status:
            self.lead_detected_timer += DT_MDL
        else:
            self.lead_detected_timer = 0.0
        
        # Update state machine
        self._update_state_machine(car_state, radar_state, model_v2, longitudinal_plan, lateral_active)
    
    def _update_state_machine(self, car_state, radar_state, model_v2, longitudinal_plan, lateral_active: bool) -> None:
        """Update the state machine based on current conditions"""
        
        if self.state == IntelligentALCState.IDLE:
            self._handle_idle_state(car_state, radar_state, model_v2, longitudinal_plan, lateral_active)
        
        elif self.state == IntelligentALCState.EVALUATING:
            self._handle_evaluating_state(car_state, radar_state, model_v2, longitudinal_plan, lateral_active)
        
        elif self.state == IntelligentALCState.REQUESTING:
            self._handle_requesting_state(car_state, radar_state, model_v2, lateral_active)
        
        elif self.state == IntelligentALCState.EXECUTING:
            self._handle_executing_state(car_state, radar_state, model_v2, lateral_active)
        
        elif self.state == IntelligentALCState.COOLDOWN:
            self._handle_cooldown_state()
    
    def _handle_idle_state(self, car_state, radar_state, model_v2, longitudinal_plan, lateral_active: bool) -> None:
        """Handle IDLE state - waiting for trigger conditions"""
        # Check if we should start evaluating
        if self._check_trigger_conditions(car_state, radar_state, longitudinal_plan, lateral_active):
            self.state = IntelligentALCState.EVALUATING
            self.state_timer = 0.0
            self.selected_direction = LaneChangeDirection.none
    
    def _handle_evaluating_state(self, car_state, radar_state, model_v2, longitudinal_plan, lateral_active: bool) -> None:
        """Handle EVALUATING state - checking if lane change is safe"""
        self.state_timer += DT_MDL
        
        # Check abort conditions
        if self._check_abort_conditions(car_state, radar_state, lateral_active):
            self._abort_lane_change("Abort condition detected during evaluation")
            return
        
        # Re-check trigger conditions
        if not self._check_trigger_conditions(car_state, radar_state, longitudinal_plan, lateral_active):
            self.state = IntelligentALCState.IDLE
            self.state_timer = 0.0
            return
        
        # Timeout if evaluation takes too long
        if self.state_timer > 5.0:
            self.state = IntelligentALCState.IDLE
            self.state_timer = 0.0
            return
        
        # After evaluation period, select lane
        if self.state_timer >= self.evaluation_time:
            direction = self._select_best_lane(car_state, radar_state, model_v2)
            
            if direction != LaneChangeDirection.none:
                self.selected_direction = direction
                self.state = IntelligentALCState.REQUESTING
                self.state_timer = 0.0
            else:
                # No safe lane found
                self.state = IntelligentALCState.IDLE
                self.state_timer = 0.0
    
    def _handle_requesting_state(self, car_state, radar_state, model_v2, lateral_active: bool) -> None:
        """Handle REQUESTING state - waiting before triggering lane change"""
        self.state_timer += DT_MDL
        
        # Check abort conditions
        if self._check_abort_conditions(car_state, radar_state, lateral_active):
            self._abort_lane_change("Abort condition detected during request")
            return
        
        # Re-verify lane is still safe
        available, _ = self._assess_lane_availability(self.selected_direction, car_state, radar_state, model_v2)
        if not available:
            self._abort_lane_change("Target lane no longer safe")
            return
        
        # After delay, trigger lane change
        if self.state_timer >= self.request_delay:
            self.lane_change_triggered = True
            self.state = IntelligentALCState.EXECUTING
            self.state_timer = 0.0
    
    def _handle_executing_state(self, car_state, radar_state, model_v2, lateral_active: bool) -> None:
        """Handle EXECUTING state - lane change in progress"""
        self.state_timer += DT_MDL
        
        # Check abort conditions
        if self._check_abort_conditions(car_state, radar_state, lateral_active):
            self._abort_lane_change("Abort condition detected during execution")
            return
        
        # Check if lane change is complete (handled by DesireHelper)
        # We'll transition to cooldown when mark_lane_change_complete() is called
        
        # Timeout safety
        if self.state_timer > 10.0:
            self.state = IntelligentALCState.COOLDOWN
            self.state_timer = 0.0
            self.lane_change_triggered = False
    
    def _handle_cooldown_state(self) -> None:
        """Handle COOLDOWN state - waiting before next automatic lane change"""
        self.state_timer += DT_MDL
        
        if self.state_timer >= self.cooldown_time:
            self.state = IntelligentALCState.IDLE
            self.state_timer = 0.0
            self.selected_direction = LaneChangeDirection.none
    
    def _check_trigger_conditions(self, car_state, radar_state, longitudinal_plan, lateral_active: bool) -> bool:
        """
        Check if all trigger conditions are met to start evaluation
        
        Returns:
            bool: True if all conditions met
        """
        if not self.enabled:
            return False
        
        if not lateral_active:
            return False
        
        # Speed check
        v_ego_mph = car_state.vEgo * CV.MS_TO_MPH
        if v_ego_mph < self.min_speed_mph or v_ego_mph > self.max_speed_mph:
            return False
        
        # Cruise active check
        if not car_state.cruiseState.enabled:
            return False
        
        # Lead vehicle present and stable
        if not radar_state.leadOne.status:
            return False
        
        if self.lead_detected_timer < self.lead_stable_threshold:
            return False
        
        # Check lead distance is reasonable
        if radar_state.leadOne.dRel < self.min_lead_distance or radar_state.leadOne.dRel > 100.0:
            return False
        
        # Speed differential check
        v_cruise_mph = car_state.vCruise * CV.KPH_TO_MPH
        speed_delta_mph = v_cruise_mph - v_ego_mph
        
        if speed_delta_mph < self.min_speed_delta_mph:
            return False
        
        # Check that we're actually being slowed by the lead vehicle
        # (not just in slow traffic where lane change won't help)
        if longitudinal_plan.hasLead and radar_state.leadOne.vRel >= -1.0:
            # Lead is not significantly slower
            return False
        
        return True
    
    def _check_abort_conditions(self, car_state, radar_state, lateral_active: bool) -> bool:
        """
        Check if any abort conditions are present
        
        Returns:
            bool: True if should abort
        """
        # Driver intervention
        if car_state.brakePressed or car_state.gasPressed:
            return True
        
        # Lateral control lost
        if not lateral_active:
            return True
        
        # Speed dropped too low
        v_ego_mph = car_state.vEgo * CV.MS_TO_MPH
        if v_ego_mph < 25.0:
            return True
        
        # Cruise disabled
        if not car_state.cruiseState.enabled:
            return True
        
        # Lead vehicle accelerated significantly
        if radar_state.leadOne.status and radar_state.leadOne.vRel > 1.0:
            return True
        
        return False
    
    def _assess_lane_availability(self, direction: int, car_state, radar_state, model_v2) -> tuple:
        """
        Assess if a lane is available and safe for lane change
        
        Args:
            direction: LaneChangeDirection.left or .right
            car_state: Current vehicle state
            radar_state: Radar data
            model_v2: Vision model output
        
        Returns:
            tuple: (available: bool, confidence: float)
        """
        # Check blindspot
        if direction == LaneChangeDirection.left and car_state.leftBlindspot:
            return False, 0.0
        if direction == LaneChangeDirection.right and car_state.rightBlindspot:
            return False, 0.0
        
        # Check lane lines confidence
        lane_line_confidence = self._get_lane_line_confidence(model_v2, direction)
        if lane_line_confidence < self.lane_line_confidence_threshold:
            return False, 0.0
        
        # Check road edges
        edge_distance = self._get_edge_distance(model_v2, direction)
        if edge_distance < self.min_edge_distance:
            return False, 0.0
        
        # Additional checks could include:
        # - Adjacent vehicle detection from radar
        # - Lane width estimation
        # - Road curvature
        
        confidence = lane_line_confidence
        return True, confidence
    
    def _get_lane_line_confidence(self, model_v2, direction: int) -> float:
        """
        Get confidence of lane line detection for target lane
        
        Args:
            model_v2: Vision model output
            direction: LaneChangeDirection
        
        Returns:
            float: Confidence value 0.0-1.0
        """
        # Lane lines in modelV2:
        # Index 0: left-left, 1: left, 2: right, 3: right-right
        
        if direction == LaneChangeDirection.left:
            # Check left lane line (index 1) exists
            if len(model_v2.laneLines) > 1:
                # Use probability as confidence
                lane_line_prob = model_v2.laneLineProbs[1] if len(model_v2.laneLineProbs) > 1 else 0.0
                return float(lane_line_prob)
        
        elif direction == LaneChangeDirection.right:
            # Check right lane line (index 2) exists
            if len(model_v2.laneLines) > 2:
                lane_line_prob = model_v2.laneLineProbs[2] if len(model_v2.laneLineProbs) > 2 else 0.0
                return float(lane_line_prob)
        
        return 0.0
    
    def _get_edge_distance(self, model_v2, direction: int) -> float:
        """
        Get distance to road edge in target direction
        
        Args:
            model_v2: Vision model output
            direction: LaneChangeDirection
        
        Returns:
            float: Distance in meters
        """
        # Road edges in modelV2:
        # Index 0: left edge, 1: right edge
        
        if direction == LaneChangeDirection.left:
            if len(model_v2.roadEdges) > 0 and len(model_v2.roadEdges[0].y) > 0:
                # Get lateral position of left edge at near distance
                left_edge_y = model_v2.roadEdges[0].y[0]
                # Positive y is to the left
                return abs(float(left_edge_y))
        
        elif direction == LaneChangeDirection.right:
            if len(model_v2.roadEdges) > 1 and len(model_v2.roadEdges[1].y) > 0:
                # Get lateral position of right edge at near distance
                right_edge_y = model_v2.roadEdges[1].y[0]
                # Negative y is to the right
                return abs(float(right_edge_y))
        
        # Default to large distance if not detected
        return 10.0
    
    def _select_best_lane(self, car_state, radar_state, model_v2) -> int:
        """
        Select the best lane for lane change (left preferred)
        
        Returns:
            LaneChangeDirection: Selected direction or none
        """
        # Try left lane first (passing lane in US)
        left_available, left_confidence = self._assess_lane_availability(
            LaneChangeDirection.left, car_state, radar_state, model_v2
        )
        
        if left_available and left_confidence > 0.6:
            return LaneChangeDirection.left
        
        # Try right lane as fallback
        right_available, right_confidence = self._assess_lane_availability(
            LaneChangeDirection.right, car_state, radar_state, model_v2
        )
        
        if right_available and right_confidence > 0.6:
            return LaneChangeDirection.right
        
        return LaneChangeDirection.none
    
    def _abort_lane_change(self, reason: str) -> None:
        """
        Abort the current lane change attempt
        
        Args:
            reason: Reason for abort (for logging)
        """
        self.state = IntelligentALCState.COOLDOWN
        self.state_timer = 0.0
        self.lane_change_triggered = False
        self.selected_direction = LaneChangeDirection.none
        
        # Track abort count
        self.abort_count += 1
        if self.abort_count >= self.max_aborts_in_window:
            # Disable feature temporarily
            self.abort_disabled_timer = self.abort_disable_time
            self.abort_count = 0
    
    def should_trigger_lane_change(self) -> bool:
        """
        Check if lane change should be triggered
        
        Returns:
            bool: True if should trigger
        """
        return self.lane_change_triggered
    
    def get_lane_change_direction(self) -> int:
        """
        Get the selected lane change direction
        
        Returns:
            LaneChangeDirection: Selected direction
        """
        return self.selected_direction
    
    def mark_lane_change_started(self) -> None:
        """Mark that the lane change has been initiated by DesireHelper"""
        self.lane_change_triggered = False
    
    def mark_lane_change_complete(self) -> None:
        """Mark that the lane change has completed successfully"""
        if self.state == IntelligentALCState.EXECUTING:
            self.state = IntelligentALCState.COOLDOWN
            self.state_timer = 0.0
            self.selected_direction = LaneChangeDirection.none
    
    def reset(self) -> None:
        """Reset to idle state"""
        if self.state in (IntelligentALCState.IDLE, IntelligentALCState.COOLDOWN):
            return
        
        self.state = IntelligentALCState.IDLE
        self.state_timer = 0.0
        self.lane_change_triggered = False
        self.selected_direction = LaneChangeDirection.none
