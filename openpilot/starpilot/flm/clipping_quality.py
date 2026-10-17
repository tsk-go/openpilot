"""Versioned encoder-local clipping demand comparison, never native authority."""
import math

RECORDED_DEBT = 'recorded-debt-v1'
STATE_ALIGNED_DEBT = 'candidate-state-debt-v1'
STATE_ALIGNED_RELIEF = 'candidate-state-relief-v2'
EXACT_EMISSION_QUALITY = 'candidate-exact-emission-v3'
QUALIFIED_EVENT_CLIPPING_QUALITY = EXACT_EMISSION_QUALITY
STRICT_IDENTIFICATION = 'strict-final-quality-v1'
NATIVE_SHADOW_IDENTIFICATION = 'native-limited-shadow-v1'
FIXED_MAP_IDENTIFICATION = 'fixed-map-no-identification-v1'
RESTORE_ACTIVATION_VERSION = 'fixed-eight-whole-map-restore-v1'
RESTORE_AGGREGATE_ACTIVATION_VERSION = 'fixed-eight-whole-map-restore-support-v2'


def clipping_quality(value):
  if type(value) is not str or value not in (RECORDED_DEBT, STATE_ALIGNED_DEBT, STATE_ALIGNED_RELIEF, EXACT_EMISSION_QUALITY):
    raise ValueError('unknown clipping quality contract')
  return value


def event_clipping_quality(payload):
  if type(payload.get('event_version')) is int and payload['event_version'] in (4, 5):
    if (payload.get('event_operation') != 'restore' or
        payload.get('event_restore_policy') != {4: RESTORE_ACTIVATION_VERSION, 5: RESTORE_AGGREGATE_ACTIVATION_VERSION}[payload['event_version']] or
        payload.get('event_clipping_quality') != QUALIFIED_EVENT_CLIPPING_QUALITY or
        payload.get('event_identification_policy') != FIXED_MAP_IDENTIFICATION):
      raise ValueError('explicit whole-map restore policy/operation')
    return QUALIFIED_EVENT_CLIPPING_QUALITY
  if 'event_restore_policy' in payload:
    raise ValueError('whole-map restore policy requires version4/5')
  if 'event_clipping_quality' in payload and payload.get('event_version') != 3:
    raise ValueError('explicit clipping quality requires event version3')
  contract = clipping_quality(payload.get('event_clipping_quality', RECORDED_DEBT))
  expected = identification_for_quality(contract)
  if contract in (STATE_ALIGNED_RELIEF, EXACT_EMISSION_QUALITY) and payload.get('event_identification_policy') != expected:
    raise ValueError('combined event experiment requires explicit native shadow identification')
  if 'event_identification_policy' in payload and (payload.get('event_version') != 3 or
      identification_policy(payload['event_identification_policy']) != expected):
    raise ValueError('event identification/final quality policy mismatch')
  return contract


def debt_is_admitted(recorded, reference, candidate, contract):
  """State-aligned reference is ORIGINAL request through CANDIDATE prestate.

  This attributes direct request demand separately from path-dependent limiter
  state. It does not assert no total clipping, safe handling or physical benefit.
  Recorded clipping direction remains an additional veto in BOTH contracts.
  """
  clipping_quality(contract)
  if any(type(value) not in (int, float) or not math.isfinite(value) for value in (recorded, reference, candidate)):
    return False
  bound = recorded if contract == RECORDED_DEBT else reference
  if contract != RECORDED_DEBT and (not recorded or not reference):
    return False
  return bool(abs(candidate) <= abs(bound) and
    (not candidate or (candidate > 0) == (bound > 0) == (recorded > 0)))


def native_relief_is_admitted(recorded_request, reference_request, candidate_request,
                              recorded_output, reference_output, candidate_output,
                              recorded_debt, reference_debt, candidate_debt):
  """Certify a native UNWIND partial order, not a physical benefit claim.

  All values must share one increasing physical torque domain. Honda callers
  supply shaped normalized requests and DECODED normalized CAN outputs, never
  inverse-sign lookup raw magnitudes. No zero/sign-crossing or tolerance.
  """
  requests = recorded_request, reference_request, candidate_request
  outputs = recorded_output, reference_output, candidate_output
  debts = recorded_debt, reference_debt, candidate_debt
  if any(type(value) not in (int, float) or not math.isfinite(value) or value == 0
         for value in requests + outputs + debts):
    return False
  sign = 1 if recorded_request > 0 else -1
  return bool(all(sign * value > 0 for value in requests + outputs) and
    all(debt * request < 0 for debt, request in zip(debts, requests, strict=True)) and
    abs(candidate_request) < min(abs(recorded_request), abs(reference_request)) and
    abs(candidate_output) <= min(abs(recorded_output), abs(reference_output)))


def identification_policy(value):
  if type(value) is not str or value not in (STRICT_IDENTIFICATION, NATIVE_SHADOW_IDENTIFICATION):
    raise ValueError('unknown identification policy')
  return value


def identification_for_quality(contract):
  clipping_quality(contract)
  return NATIVE_SHADOW_IDENTIFICATION if contract in (STATE_ALIGNED_RELIEF, EXACT_EMISSION_QUALITY) else STRICT_IDENTIFICATION
