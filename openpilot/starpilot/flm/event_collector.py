"""Bounded storage transport for whole-event fitting, using original joins."""
from collections import deque

from openpilot.starpilot.flm.fullrate_collector import FullrateCollector
from openpilot.starpilot.flm.adaptive_profile import replay_accepts


class EventFullrateCollector(FullrateCollector):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    # At most5,120 joined endpoints; whole events are selected before the
    # child12,000-frame/24-event export budget, never by arbitrary packet tail.
    self.blocks = deque(self.blocks, maxlen=64)

  def physical(self, value, now_ns):
    accepted = super().physical(value, now_ns)
    if self.sealed:
      # An80-point packet is storage only, never a physical independent event.
      # Keep recording the unmodified chronological trace; child reconstruction
      # alone groups complete cycles/turns into independent fit episodes.
      self.sealed = False
    return accepted

  def _accepted_fit_target(self, value):
    """A known accepted result changes collection lineage, not live health."""
    try:
      trace = value.effect_trace
      profile = self.fit_result.profile
      trace.validate()
      previous = self.ready[-1][0]
      return bool(trace.qualified and trace.envelope == profile.effect_envelope and
        replay_accepts(self.fit_validation, profile) and self.physical_context is not None and
        self.context == (value.identity, value.generation, value.domain, value.stage_revision,
          value.response_revision, value.source_epoch, value.controller_mode, value.policy,
          value.baseline_revision, value.controller_revision, value.turn_assist) and
        previous.native_identity == value.native_identity and
        self.adapter.fit_profile == profile)
    except (AttributeError, IndexError, TypeError, ValueError, OverflowError):
      return False

  def _rollover_training(self):
    # The original active/native/source chronology remains intact. Training
    # endpoints and pending joins cannot cross an accepted target change.
    self.training_interruptions['accepted_full_effect_target_changed'] += 1
    self.controls.clear()
    self.applied.clear()
    self.recent_controls.clear()
    self.recent_applied.clear()
    self.ready.clear()
    self.points.clear()
    self.raw_points.clear()
    self.blocks.clear()
    self.cohort = None
    self.sealed = False
    self.model_block_sequence += 1
    self.model_points = 0
    self.model_sealed = False
    self.fit_block_sequence = self.block_sequence
    self.result = self.last_validation = None
    # Retaining the immutable fit NEVER retains a current physical admission.
    # A genuinely new pose and the normal current controller/native probe are
    # mandatory before the parent can renew its original bounded lease.
    self.last_qualified_response = 0
    self.adapter.current_physical_valid = False
    self.adapter.last_physical_ns = 0

  def control(self, value, now_ns):
    rollover = self.adapter.target_changed
    if rollover:
      if self._accepted_fit_target(value):
        self._rollover_training()
      else:
        self.split('accepted_full_effect_target_changed', reset=True)
      self.adapter.target_changed = False
    accepted = super().control(value, now_ns)
    if rollover and not accepted:
      # Invalid, stale or faulted first-target evidence cannot preserve a fit.
      self.split('unqualified_accepted_target', reset=True)
    return accepted

  def job_snapshot(self, now_ns):
    if (self.context is None or self.block_sequence == self.fit_block_sequence or len(self.blocks) < 8 or
        self.last_fit and now_ns - self.last_fit < 60_000_000_000 or not self.ready or self.physical_context is None):
      return None
    control, output = self.ready[-1]
    self.sequence += 1
    try:
      return self.adapter.fit_job_snapshot(tuple(self.blocks), now_ns=now_ns, sequence=self.sequence,
        prior=self.prior_coefficients, control=control, output=output, physical_context=self.physical_context)
    except (ValueError, TypeError, OverflowError, MemoryError):
      self.reason, self.last_fit = 'event_snapshot_unavailable', now_ns
      return None
