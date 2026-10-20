"""Compatibility policy for two recorded GM configurations; native authority stays separate.

Register divergence remains a protected-register diagnostic, not a benign-fault
claim. Raw fault reports are retained. Every unlisted configuration/bit blocks.
"""
from openpilot.cereal import log
from opendbc.car.gm.cancel_remap import aol_enabled


def _diagnostic_mask(cp):
  try:
    from opendbc.car.gm.aol import qualified_gm
    from opendbc.car.gm.values import CAR, is_volt_sdgm_profile, is_bolt_present_no_acc_pedal_profile
    if cp.brand != 'gm' or len(cp.safetyConfigs) != 1:
      return 0
    word = int(cp.safetyConfigs[0].safetyParam)
    # Only these two exact identities can use this diagnostic classification.
    # Reject every other profile before the full GM admission walk. Current
    # faults and all existing qualification checks remain authoritative.
    if not ((cp.carFingerprint == CAR.CHEVROLET_VOLT_2019 and word == 0x1005) or
            (cp.carFingerprint == CAR.CHEVROLET_BOLT_CC_2018_2021 and word == 0x9D)):
      return 0
    if not qualified_gm(cp) or not aol_enabled(cp):
      return 0
    if (cp.carFingerprint == CAR.CHEVROLET_VOLT_2019 and word == 0x1005 and
        is_volt_sdgm_profile(cp, longitudinal=False) and cp.pcmCruise and not cp.openpilotLongitudinalControl):
      return 1 << 18
    if (cp.carFingerprint == CAR.CHEVROLET_BOLT_CC_2018_2021 and word == 0x9D and
        is_bolt_present_no_acc_pedal_profile(cp) and cp.openpilotLongitudinalControl and not cp.pcmCruise):
      return (1 << 2) | (1 << 3)
  except (AttributeError, TypeError, ValueError, OverflowError, IndexError):
    pass
  return 0


def blocking_fault_mask(mask, cp):
  try:
    value = int(mask)
    return value < 0 or value > 0xFFFFFFFF or bool(value & ~_diagnostic_mask(cp))
  except (TypeError, ValueError, OverflowError):
    return True


def blocking_fault_list(faults, cp):
  try:
    allowed = _diagnostic_mask(cp)
    named = ((log.PandaState.FaultType.interruptRateCan1, 1 << 2),
             (log.PandaState.FaultType.interruptRateCan2, 1 << 3),
             (log.PandaState.FaultType.registerDivergent, 1 << 18))
    return any(not any(fault == name and allowed & bit for name, bit in named) for fault in faults)
  except (TypeError, ValueError, OverflowError):
    return True
