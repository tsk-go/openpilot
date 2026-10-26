"""Actual Ford factory, parser, Card, SelfdriveD, Controls and native matrix.

CAN, perception, USB and clocks are synthetic; no physical acceptance claim.
"""
import pytest
from openpilot.starpilot.tests.ford_lifecycle_helpers import FORD_FACTORIES, ford_joined as ford_joined, run_actual_producer


@pytest.fixture(autouse=True)
def configuration_topology(monkeypatch, topology, request):
  monkeypatch.ford_topology = topology
  if request.node.name.startswith('test_route49_first_main_engagement'):
    monkeypatch.ford_first_main = True
    monkeypatch.ford_angle = request.node.callspec.params['angle']


@pytest.mark.parametrize('identity', FORD_FACTORIES)
@pytest.mark.parametrize('alpha', [False, True])
@pytest.mark.parametrize('hands_free', [False])
@pytest.mark.parametrize('topology', ['automatic', 'manual', 'multi-panda', 'manual-multi'])
def test_actual_configuration_lifecycle(ford_joined, monkeypatch):
  run_actual_producer(ford_joined, monkeypatch, scenario='configuration-parity')


@pytest.mark.parametrize('identity', [FORD_FACTORIES[11]])
@pytest.mark.parametrize('alpha', [False])
@pytest.mark.parametrize('hands_free', [False, True])
@pytest.mark.parametrize('topology', ['automatic', 'manual-multi'])
@pytest.mark.parametrize('angle', [False, True])
def test_route49_first_main_engagement_arms_before_cruise_cancel(ford_joined, monkeypatch, angle):
  run_actual_producer(ford_joined, monkeypatch, scenario='route49')
