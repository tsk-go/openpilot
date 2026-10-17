"""Registered producer version dispatch; this does not grant restore authority."""
import pytest
from opendbc.car.car_helpers import interfaces
from opendbc.car.honda.values import CAR as HONDA
from opendbc.car.hyundai.values import CAR as HKG
from opendbc.car.toyota.values import CAR as TOYOTA
from openpilot.starpilot.flm.learner_factory import from_evidence
from openpilot.starpilot.flm.runtime_adapter_registry import baseline_values
from openpilot.starpilot.flm.steerlearnerd import production_adapter_for_evidence
from openpilot.starpilot.flm.tests.test_production_event_contract import capture
from openpilot.starpilot.flm.tests.test_registered_controls_global import controls_for


@pytest.mark.parametrize('platform,mode', ((TOYOTA.TOYOTA_RAV4_TSS2, 'standard'),
  (HKG.HYUNDAI_IONIQ_6, 'starpilot'), (HONDA.HONDA_CIVIC, None)))
def test_actual_registered_producer_explicit_restore_version_and_legacy_default(platform, mode):
  cp = interfaces[platform].get_non_essential_params(platform)
  with controls_for(cp, mode, True) as controls:
    evidence, source, _ = capture(controls)
    before = controls.CP.as_builder().to_bytes(), baseline_values(controls.LaC)
    live = production_adapter_for_evidence(controls.CP, evidence, ('event', 'center'), source=source)
    old = from_evidence(controls.CP, evidence, ('event', 'center'), source=source)
    assert live is not None and live.replay_version == 3 and live.restore_version == 5
    assert old is not None and old.replay_version == 2 and old.restore_version == 2
    assert from_evidence(controls.CP, evidence, ('event', 'center'), source=source, event_restore_version=4) is None
    live.select_objective(('event', 'deadband.high'))
    assert live.restore_version == 5
    assert (controls.CP.as_builder().to_bytes(), baseline_values(controls.LaC)) == before
