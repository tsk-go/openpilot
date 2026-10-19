"""Generic optional-feature admission from finalized native CarParams.

Admission creates a host; the host still checks live axis and source authority.
PCM cruise describes engagement/set-speed integration, not who controls acceleration.
"""


def _native_configuration_valid(cp, *, longitudinal: bool) -> bool:
  """Keep native configuration checks separate from global feature availability.

  GM's finalized owners encode the physical topology and longitudinal owner in
  correlated safety words, flags and vehicle identity. A control boolean alone
  cannot validate that contract. Reuse its native validators instead of a
  feature launch allowlist or a second, weaker copy of those safety rules.
  """
  if getattr(cp, 'brand', None) == 'gm':
    from opendbc.car.gm.feature_capabilities import display_supported, longitudinal_supported
    return longitudinal_supported(cp) if longitudinal else display_supported(cp)
  return True


def display_supported(cp) -> bool:
  return bool(cp is not None and getattr(cp, 'carFingerprint', '') and
              getattr(cp, 'passive', None) is False and
              getattr(cp, 'dashcamOnly', None) is False and
              getattr(cp, 'notCar', None) is False and
              _native_configuration_valid(cp, longitudinal=False))


def longitudinal_supported(cp) -> bool:
  return bool(display_supported(cp) and getattr(cp, 'openpilotLongitudinalControl', None) is True and
              _native_configuration_valid(cp, longitudinal=True))
