"""Child-only canonical effect trials through complete selected controller/CAN history."""
import math

from openpilot.starpilot.flm.clipping_quality import NATIVE_SHADOW_IDENTIFICATION

from openpilot.starpilot.flm.adaptive_profile import ReplayValidation
from openpilot.starpilot.flm.controller_replay import MAX_FRAME_GAP_NS, _run, final_command, restore_snapshot, same_final_command, same_float
from openpilot.starpilot.flm.runtime_adapter_registry import canonical_physical_context, physical_model_revision
from openpilot.starpilot.flm.torque_eligibility import exact_unclipped_pair

POLICY = 'event_effect_coordinate_v2'
RESTORE_POLICY = 'event_effect_restore_v1'


class EventControllerReplay:
  """Reuse original source/native/encoder proofs; replace only trial coordinates."""
  def __init__(self, engine, objective, original_anchor, *, restore_envelope=None, activation_plan=None):
    if (engine.failed or not engine.raw_mode or not 1 <= len(objective.names) <= 4 or
        len(set(objective.names)) != len(objective.names) or len(objective.anchor_digest) != 64):
      raise ValueError('event selected replay contract')
    self.engine, self.objective, self.original_anchor = engine, objective, original_anchor
    self.restore_envelope = restore_envelope
    self.activation_plan = activation_plan
    self.__identification_token = object()
    if activation_plan is not None:
      from openpilot.starpilot.flm.restore_activation import WholeMapRestorePlan, restore_plan_matches
      activation_plan.validate()
      if (restore_envelope is not None and not restore_plan_matches(activation_plan, restore_envelope) or
          restore_envelope is None and type(activation_plan) is WholeMapRestorePlan):
        raise ValueError('restore activation exact operation/transaction binding')
      if (activation_plan.identity != engine.identity or
          activation_plan.baseline_revision != engine.baseline_revision or activation_plan.source_epoch != objective.context_key or
          tuple(row[:2] for row in activation_plan.windows) != tuple(engine.replay_windows)):
        raise ValueError('event activation source/window binding')
    if restore_envelope is not None:
      restore_envelope.validate()
      if (restore_envelope.version != 2 or restore_envelope.operation != 'restore' or
          restore_envelope.replay_anchor() != original_anchor):
        raise ValueError('explicit whole-map restore replay context')
    self.projected = {}
    accumulated = dict(original_anchor['accumulated']) if isinstance(original_anchor, dict) else {}
    self.prior_full = accumulated
    self.reference = tuple(float(accumulated.get(name, 0.0)) for name in objective.names)

  def __getattr__(self, name):
    return getattr(self.engine, name)

  def _prior_matches(self, frame):
    trace = getattr(frame, 'effect_trace', None)
    if trace is None:
      return not any(self.prior_full.values()) and not any(frame.applied_coordinates)
    try:
      trace.validate()
      envelope = trace.envelope
      return (dict(trace.target) == self.prior_full and envelope.selected_baseline_revision == self.baseline_revision and
              envelope.source_epoch == self.objective.context_key and
              getattr(frame, 'effect_prepare_ns', 0) == trace.control_ns)
    except (AttributeError, TypeError, ValueError):
      return False

  def _rollout(self, coordinates, *, restore_target=False, restore_omit_group=None, _identification_token=None):
    from openpilot.starpilot.flm.selected_effects import (EffectTrial, EffectReplayTransition, EffectReplayRecordedSource,
      EffectRestoreTrial, EffectRestoreAblationTrial)

    shadow = _identification_token is not None
    if shadow and (_identification_token is not self.__identification_token or self.activation_plan is None or
                   self.activation_plan.identification_policy != NATIVE_SHADOW_IDENTIFICATION or restore_target or self.restore_envelope is not None):
      raise ValueError('event identification scope/policy mismatch')
    if (len(coordinates) != len(self.objective.names) or
        any(not math.isfinite(value) or abs(value) > .25 for value in coordinates)):
      raise ValueError('event original anchor coordinate envelope')
    if restore_target:
      if self.restore_envelope is None:
        raise ValueError('restore endpoint cannot be an optimizer trial')
      restore_coordinates = tuple(dict(self.restore_envelope.coordinates)[n] for n in self.objective.names)
      if tuple(coordinates) != restore_coordinates:
        raise ValueError('restore markers changed historical map')
      if restore_omit_group is None:
        trial = EffectRestoreTrial(self.objective, tuple(coordinates), self.baseline_revision,
          self.original_anchor, self.restore_envelope)
      else:
        if self.activation_plan is not None:
          from openpilot.starpilot.flm.canonical_surface_adapter import GROUPS
          if tuple(restore_omit_group) not in tuple(GROUPS[group] for group in self.restore_envelope.restoration_groups):
            raise ValueError('restore ablation must be one active exact canonical group')
        trial = EffectRestoreAblationTrial(self.objective, tuple(coordinates), self.baseline_revision,
          self.original_anchor, self.restore_envelope, tuple(restore_omit_group))
      trial.basis()
    elif restore_omit_group is not None:
      raise ValueError('group-off analysis requires explicit full restore')
    elif self.restore_envelope is not None:
      trial = None  # Restore baseline is the recorded neutral trajectory.
    else:
      trial = EffectTrial(self.objective, tuple(coordinates), self.baseline_revision, self.original_anchor)
    frames, windows = tuple(self.records), tuple(self.replay_windows)
    if not frames or len(frames) > 12000 or not 1 <= len(windows) <= 24:
      raise ValueError('event exact window bound')
    if any(a > b or i and a <= windows[i - 1][1] for i, (a, b) in enumerate(windows)):
      raise ValueError('event windows overlap')
    controller, vm = self.factory.create()
    transition = None if trial is None or restore_target else EffectReplayTransition(trial)
    checkpoints, requests, saturated = dict(self.checkpoints), {}, {}
    prior_ns = prior_sequence = index = 0
    neutral = not restore_target and (self.restore_envelope is not None or tuple(coordinates) == self.reference)
    for frame in frames:
      while index < len(windows) and frame.control_ns > windows[index][1]:
        index += 1
      if index >= len(windows) or not windows[index][0] <= frame.control_ns <= windows[index][1]:
        raise ValueError('event frame outside original window')
      if frame.control_ns == windows[index][0]:
        if frame.control_ns not in checkpoints:
          raise ValueError('event actual pre-maneuver state missing')
        restore_snapshot(controller, vm, checkpoints[frame.control_ns])
        if transition is not None:
          transition.reset()
        prior_ns = prior_sequence = 0
      elif not prior_ns:
        raise ValueError('event window beginning omitted')
      if (not self.engine._frame_context(frame) or not self._prior_matches(frame) or any(frame.centre_values) or
          frame.actual_stage_residual is not None and any(frame.actual_stage_residual) or
          prior_ns and not 0 < frame.control_ns - prior_ns <= MAX_FRAME_GAP_NS or
          prior_sequence and frame.frame_sequence != prior_sequence + 1):
        raise ValueError('event source/history mismatch')
      trace = getattr(frame, 'effect_trace', None)
      prepare_ns = getattr(frame, 'effect_prepare_ns', 0)
      activation = None if self.activation_plan is None else self.activation_plan.activation_for(*windows[index])
      if self.activation_plan is not None and activation is None:
        raise ValueError('event activation window omitted')
      original_prefix = bool(activation is not None and (activation[0] == 0 or frame.control_ns < activation[0]))
      activation_tick = bool(activation is not None and frame.control_ns == activation[0])
      if activation_tick and prepare_ns != activation[1]:
        raise ValueError('event activation original prepare clock changed')
      if self.activation_plan is not None and restore_target and not original_prefix and not 0 < prepare_ns <= frame.control_ns:
        raise ValueError('restore activation original owner clock unavailable')
      if neutral or original_prefix:
        source = None if trace is None else EffectReplayRecordedSource(trace)
      elif restore_target:
        # Whole-map endpoint qualification is independent from the separately
        # replayed/probed gradual owner transition. Never reduce this map to the
        # protocol's <=4 marker coordinates or infer neutral from zero markers.
        source = trial
      elif prepare_ns > 0:
        source = transition.source_for_frame(prepare_ns, trace, new_owner=activation_tick)
      elif self.activation_plan is not None:
        raise ValueError('event activation post-treatment owner clock missing')
      elif trace is None and not any(self.prior_full.values()):
        # Historical zero-effect data may qualify a stationary shape proposal;
        # it contains no new owner prepare stamp and confers no slew admission.
        # Parent current_effect_probe separately requires fresh exact prepare_ns.
        source = trial
      else:
        raise ValueError('event exact owner transition clock unavailable')
      output, log = _run(controller, vm, frame.inputs, self.engine.objective, (0.0, 0.0), frame.torque_values,
                         actual_stage_residual=frame.actual_stage_residual, effect_trial=source)
      if (neutral or original_prefix) and (not same_final_command(output, frame.selected_command) or
                      frame.actual_lac_command is not None and not same_float(output, frame.actual_lac_command)):
        raise ValueError('event neutral selected trajectory changed')
      output = final_command(output)
      if not math.isfinite(output) or abs(output) > 1.000001:
        raise ValueError('event selected command envelope')
      requests[frame.control_ns], saturated[frame.control_ns] = output, bool(log.saturated)
      prior_ns, prior_sequence = frame.control_ns, frame.frame_sequence
    if index != len(windows) - 1 or prior_ns != windows[-1][1]:
      raise ValueError('event last actual tick missing')
    # This replays every consumed native encoding, including clipped unscored
    # context. The encoder independently refuses greater/opposite clipping.
    quality = {} if self.activation_plan is None else {'quality_contract': self.activation_plan.clipping_quality}
    if shadow:
      quality['identification_policy'] = NATIVE_SHADOW_IDENTIFICATION
    encoded = self.emissions.rollout(requests, windows[0][0], windows[-1][1], windows, **quality)
    return requests, encoded, saturated

  def rebuild_causal_features(self, *, epsilon=.01):
    if self.restore_envelope is not None:
      raise ValueError('restoration requires joint full-map/group-off proof, not marker finite differences')
    if not math.isfinite(epsilon) or not 0 < epsilon <= .03:
      raise ValueError('event finite difference envelope')
    _, baseline, _ = self._rollout(self.reference)
    plan = self.__dict__.get('activation_plan')
    identify = {} if plan is None or plan.identification_policy != NATIVE_SHADOW_IDENTIFICATION else {
      '_identification_token': self.__identification_token}
    sensitivities = []
    for index, parameter in enumerate(self.objective.parameters):
      plus, minus = list(self.reference), list(self.reference)
      plus[index], minus[index] = min(self.reference[index] + epsilon, parameter.high), max(self.reference[index] - epsilon, parameter.low)
      span = plus[index] - minus[index]
      if span <= 0:
        raise ValueError('event parameter has no admitted excitation domain')
      # Only the explicitly bound combined experiment uses native-limited
      # SHADOW secants. These are conditional algorithmic sensitivities, never
      # admitted profiles. Final validate() uses a separate strict rollout.
      # Legacy experiments retain their original final-quality probe gates.
      high = low = None
      try:
        _, high, _ = self._rollout(tuple(plus), **identify)
      except ValueError:
        pass
      try:
        _, low, _ = self._rollout(tuple(minus), **identify)
      except ValueError:
        pass
      if high is None and low is None:
        sensitivities.append(dict.fromkeys(baseline, 0.0))
        continue
      if high is None:
        high, plus[index] = baseline, self.reference[index]
      if low is None:
        low, minus[index] = baseline, self.reference[index]
      span = plus[index] - minus[index]
      if set(high) != set(baseline) or set(low) != set(baseline):
        raise ValueError('event emission support changed')
      if span <= 0:
        if plus[index] != self.reference[index] or minus[index] != self.reference[index]:
          raise ValueError('event finite difference lost admitted domain')
        # At a parameter boundary the only successful direction can be the
        # exact neutral trajectory. A rejected nonzero probe remains rejected;
        # this coordinate has ZERO identifiable support, not a fit derivative.
        sensitivities.append(dict.fromkeys(baseline, 0.0))
        continue
      sensitivities.append({stamp: (high[stamp] - low[stamp]) / span for stamp in baseline})
    self.projected = {stamp: (value, tuple(feature[stamp] for feature in sensitivities)) for stamp, value in baseline.items()}
    return len(self.projected)

  def validate(self, profile, control, output, physical_context, blocks, model):
    if (self.failed or profile.policy != (RESTORE_POLICY if self.restore_envelope is not None else POLICY) or
        self.restore_envelope is not None and profile.effect_envelope != self.restore_envelope or profile.identity != self.identity or
        profile.parameters != self.objective.parameters or len(profile.coefficients) != len(self.objective.names) or
        model.identity != self.identity or model.domain != 'normalized_torque' or
        model.context != canonical_physical_context(physical_context) or
        control.identity != self.identity or control.baseline_revision != self.baseline_revision or
        output.limited or output.override or output.fault or not output.active or not output.valid or not output.native_allowed or
        control.limited and not exact_unclipped_pair(control, output) or not self.applied_matches(control, output) or
        set(profile.train_ids) & set(profile.heldout_ids) or len(profile.train_ids) < 4 or len(profile.heldout_ids) < 4):
      return None
    selected = [block for block in blocks if block.block_id in profile.heldout_ids]
    if {block.block_id for block in selected} != set(profile.heldout_ids):
      return None
    try:
      base_requests, baseline, base_saturated = self._rollout(self.reference)
      trial_requests, proposed, trial_saturated = self._rollout(profile.coefficients, restore_target=self.restore_envelope is not None)
      if set(proposed) != set(baseline) or any(trial_saturated[stamp] and not base_saturated[stamp] for stamp in base_requests):
        return None
      if not self._slew_ok(base_requests, trial_requests, encoded=False) or not self._slew_ok(baseline, proposed, encoded=True):
        return None
      improvements = {cohort: [] for cohort in self.objective.required_cohorts}
      used = set()
      for block in selected:
        if block.identity != self.identity or block.cohort not in improvements or len(block.samples) < 40:
          return None
        base_loss = trial_loss = weight = 0.0
        for row in block.samples:
          key = row.control_ns, row.applied_ns
          if (key in used or not row.active or row.override or row.fault or row.saturated or not row.native_allowed or
              not row.physical_valid or not row.stage_valid or row.model_wobble or row.controller_chatter or
              row.applied_ns not in self.projected or row.applied_ns not in baseline):
            return None
          used.add(key)
          target = row.residual_target + self.projected[row.applied_ns][0] - sum(
            a * b for a, b in zip(row.features, self.reference, strict=True))
          base, trial = baseline[row.applied_ns], proposed[row.applied_ns]
          if not all(model.command_low <= -value <= model.command_high for value in (target, base, trial)):
            return None
          base_loss += row.weight * (model.slope * (target - base)) ** 2
          trial_loss += row.weight * (model.slope * (target - trial)) ** 2
          weight += row.weight
        if weight <= 0:
          return None
        improvements[block.cohort].append((base_loss - trial_loss) / weight)
      lower_bounds = []
      for values in improvements.values():
        if len(values) < 2:
          return None
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
        lower = mean - 12.707 * math.sqrt(variance / len(values))
        if not math.isfinite(lower) or lower <= 0:
          return None
        lower_bounds.append(lower)
      return ReplayValidation(profile, self.baseline_revision, physical_model_revision(model), True, True,
                              min(lower_bounds), tuple(control.baseline_values))
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
      return None

  def _slew_ok(self, baseline, proposed, *, encoded):
    previous = None
    maximum_base = maximum_trial = 0.0
    for stamp in sorted(baseline):
      event = self.emissions.events[stamp] if encoded else None
      control_ns = event.control_ns if encoded else stamp
      window = next((index for index, (a, b) in enumerate(self.replay_windows) if a <= control_ns <= b), None)
      if window is None:
        return False
      if previous is not None and window == previous[3]:
        elapsed = (stamp - previous[0]) / 1e9
        if elapsed <= 0:
          return False
        maximum_base = max(maximum_base, abs(baseline[stamp] - previous[1]) / elapsed)
        maximum_trial = max(maximum_trial, abs(proposed[stamp] - previous[2]) / elapsed)
      previous = stamp, baseline[stamp], proposed[stamp], window
    return maximum_trial <= maximum_base + 1e-6
