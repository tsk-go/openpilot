"""The tablet's navigation map: route details from Mapbox, route options, traffic refresh, nav_link.NavLink."""
import json
from concurrent.futures import Future
from types import SimpleNamespace
import pytest

from openpilot.starpilot.navigation.mapbox_budget import MonthlyBudget
from openpilot.starpilot.navigation.owner import NavigationOwner, ValidationError, route_exclusions
from openpilot.starpilot.navigation.route_engine import MapboxRouteEngine, NavigationRoute, encode_polyline
from openpilot.starpilot.navigation.runtime import REFRESH_NS, RouteRuntime, fastest_first, keep_road
from openpilot.starpilot.system.starview.nav_link import NavLink

PLACE = {'name': 'Library', 'longitude': .03, 'latitude': 0.}


def mapbox_route(lat=0., duration=300., congestion=('low', 'heavy', 'heavy'), incidents=True, closure=False):
  points = [[0., lat], [.01, lat], [.02, lat], [.03, lat]]
  leg = {'summary': 'Main Street, Ocean Parkway', 'annotation': {'congestion': list(congestion)},
         'steps': [
           {'distance': 2224., 'duration': duration - 100, 'name': 'Main Street', 'maneuver': {'type': 'depart', 'instruction': 'Head east on Main Street',
            'location': points[0]}, 'intersections': [{'classes': ['toll']}, {'classes': ['motorway', 'bogus']}]},
           {'distance': 1112., 'duration': 100., 'name': 'Ocean Parkway', 'ref': 'NY 908',
            'maneuver': {'type': 'turn', 'modifier': 'slight right', 'instruction': 'Turn right onto Ocean Parkway', 'location': points[2]}},
           {'distance': 0., 'duration': 0., 'name': '', 'maneuver': {'type': 'arrive', 'instruction': 'You have arrived', 'location': points[3]}}]}
  if incidents:
    leg['incidents'] = [{'id': 7, 'type': 'accident', 'impact': 'major', 'description': 'Crash on Main Street', 'closed': False,
                         'geometry_index_start': 1, 'geometry_index_end': 2}]
  if closure:
    leg['closures'] = [{'geometry_index_start': 2, 'geometry_index_end': 3}]
  return {'distance': 3336., 'duration': duration, 'duration_typical': 240., 'geometry': {'coordinates': points}, 'legs': [leg]}


@pytest.fixture
def owner(tmp_path, monkeypatch):
  monkeypatch.setattr(NavigationOwner, '_is_metric', lambda self: False)
  o = NavigationOwner(tmp_path, runtime_source=lambda: None, transient_root=tmp_path / 'runtime')
  saved = o.configure({'enabled': True, 'token': 'pk.test'}, '0', True)
  o.select(PLACE, saved['revision'], True)
  return o


def test_route_details_traffic_incidents_steps_and_classes():
  route = NavigationRoute(mapbox_route(closure=True))
  d = route.details
  assert d['via'] == 'Main Street, Ocean Parkway' and d['typicalSeconds'] == 240.
  assert d['classes'] == ['motorway', 'toll']
  levels = [run[2] for run in d['traffic']]
  assert levels == [1, 3, 5]                      # low, heavy, then the closed last segment
  assert d['traffic'][0][0] == 0 and d['traffic'][-1][1] == pytest.approx(route.cumulative[-1], abs=.2)
  assert d['incidents'][0]['type'] == 'accident' and d['incidents'][0]['startMeters'] == pytest.approx(route.cumulative[1], abs=.2)
  assert [s['text'] for s in d['steps']] == ['Head east on Main Street', 'Turn right onto Ocean Parkway', 'You have arrived']
  assert d['steps'][1]['modifier'] == 'slightRight' and d['steps'][1]['ref'] == 'NY 908'
  assert d['steps'][1]['startMeters'] == 2224.
  assert d['polyline'] == encode_polyline(route.points)


def test_polyline_matches_googles_reference():
  # developers.google.com/maps/documentation/utilities/polylinealgorithm
  assert encode_polyline([(-120.2, 38.5), (-120.95, 40.7), (-126.453, 43.252)]) == '_p~iF~ps|U_ulLnnqC_mqNvxq`@'


def test_details_are_optional():
  raw = mapbox_route()
  raw['legs'][0]['annotation'] = {'congestion': 'garbage'}
  raw['legs'][0]['incidents'] = [{'geometry_index_start': 'x'}]
  route = NavigationRoute(raw)
  assert route.details == {} and route.total_duration == 300.   # the route still drives


ENGINE = 'openpilot.starpilot.navigation.route_engine.response_json'


def test_request_asks_for_traffic_and_includes_carpool_lanes(monkeypatch):
  sent = []
  monkeypatch.setattr(ENGINE, lambda session, url, params: sent.append(params) or {'code': 'Ok', 'routes': [mapbox_route()]})
  MapboxRouteEngine(None).fetch('pk.test', (0., 0.), PLACE, None, ('toll', 'unpaved', '+hov2', '+hov3'))
  params = sent[0]
  assert params['annotations'] == 'congestion,closure' and params['overview'] == 'full'
  assert params['exclude'] == 'toll,unpaved' and params['include'] == 'hov2,hov3'


def test_refused_beta_exclusion_routes_without_it(monkeypatch):
  calls = []
  def answer(session, url, params):
    calls.append(dict(params))
    if 'tunnel' in params.get('exclude', ''):
      raise ValidationError('The map service could not complete this request')
    return {'code': 'Ok', 'routes': [mapbox_route()]}
  monkeypatch.setattr(ENGINE, answer)
  MapboxRouteEngine(None).fetch('pk.test', (0., 0.), PLACE, None, ('ferry', 'tunnel'))
  assert [c.get('exclude') for c in calls] == ['ferry,tunnel', 'ferry']
  def down(*_):
    raise ValidationError('down')
  monkeypatch.setattr(ENGINE, down)
  with pytest.raises(ValidationError):
    MapboxRouteEngine(None).fetch('pk.test', (0., 0.), PLACE, None, ('ferry',))


def test_route_exclusions_from_settings():
  assert route_exclusions({}) == ()
  assert route_exclusions({'avoidTolls': True, 'avoidFerries': True}) == ('toll', 'ferry')
  assert route_exclusions({'avoidUnpaved': True, 'carpool': 3, 'expressLanes': True}) == ('unpaved', '+hov2', '+hov3', '+hot')
  assert route_exclusions({'avoidTolls': True, 'carpool': 2, 'expressLanes': True}) == ('toll', '+hov2')   # no toll lanes
  assert route_exclusions({'carpool': 5, 'avoidTunnels': 'yes'}) == ()


def test_options_change_settings_and_reset_route_choice(owner):
  link = NavLink(owner=owner)
  owner.record_routes(owner.read()['revision'], [NavigationRoute(mapbox_route()), NavigationRoute(mapbox_route(lat=.001))])
  link.select_route(1)
  assert owner.read()['routeChoice'] == 1
  res = link.options({'avoidTolls': True, 'carpool': 2, 'avoidUnpaved': True})
  assert res['options']['avoidTolls'] and res['options']['carpool'] == 2 and res['options']['avoidUnpaved']
  assert not res['options']['avoidFerries'] and res['options']['expressLanes'] is False
  assert owner.read()['routeChoice'] == 0 and owner.read()['destination']['name'] == 'Library'
  for bad in ({'carpool': 4}, {'avoidTunnels': 1}, {'bogus': True}, {}):
    with pytest.raises(ValidationError):
      link.options(bad)


def test_state_sends_lines_only_when_they_change(owner):
  link = NavLink(owner=owner)
  assert link.state()['routes'] == []
  routes = [NavigationRoute(mapbox_route()), NavigationRoute(mapbox_route(lat=.001, duration=420., congestion=('low',) * 3, incidents=False))]
  owner.record_routes(owner.read()['revision'], routes)
  s = link.state()
  assert [r['durationSeconds'] for r in s['routes']] == [300., 420.]
  assert s['routes'][0]['via'] == 'Main Street, Ocean Parkway' and s['routes'][0]['incidents'] == 1 and s['routes'][1]['incidents'] == 0
  assert s['routes'][0]['typicalSeconds'] == 240. and s['routes'][0]['classes'] == ['motorway', 'toll']
  assert s['details'][0]['polyline'] == routes[0].details['polyline'] and len(s['details'][1]['steps']) == 3
  assert s['options']['avoidTolls'] is False and s['options']['carpool'] == 0
  assert len(json.dumps(s)) < 20000
  again = link.state(detail_key=s['detailKey'])
  assert 'details' not in again and again['routeKey'] == s['routeKey']
  same = {'ok': True, 'unchanged': True, 'routeKey': s['routeKey'], 'detailKey': s['detailKey']}
  assert link.state(route_key=s['routeKey'], detail_key=s['detailKey']) == same
  assert 'details' in link.state(route_key=s['routeKey'])            # the tablet lost its lines: sent again
  link.select_route(1)
  chosen = link.state(route_key=s['routeKey'], detail_key=s['detailKey'])
  assert chosen['selectedRoute'] == 1 and 'details' not in chosen


def test_details_of_other_routes_are_not_mixed_up(owner):
  link = NavLink(owner=owner)
  owner.record_routes(owner.read()['revision'], [NavigationRoute(mapbox_route())])
  (owner.transient_root / 'routes.detail').write_text(json.dumps({'expires': 1e18, 'routes': [{'distanceMeters': 1., 'durationSeconds': 2.}]}))
  s = link.state()
  assert s['routes'][0]['via'] == '' and s['details'] == [None]


def test_set_and_cancel_destination(owner):
  link = NavLink(owner=owner)
  link.cancel()
  assert owner.read()['destination'] is None
  res = link.set_destination('', '1 Main St', 40.6, -73.9)
  assert res['destination']['name'] == '1 Main St' and 'address' not in res['destination']
  assert link.lists()['recents'][0]['name'] == '1 Main St'
  link.cancel()
  assert link.cancel() == {'ok': True}


def test_tiles_stop_at_the_free_allowance(owner, monkeypatch):
  link = NavLink(owner=owner)
  with pytest.raises(ValidationError, match='style'):
    link.tile('satellite', 1, 0, 0)
  asked = []
  monkeypatch.setattr(owner, 'map_tile', lambda *a: asked.append(a) or b'png')
  assert link.tile('trafficDark', 3, 1, 2) == b'png' and asked == [(3, 1, 2, 'trafficDark')]
  owner.tile_budget.used = owner.tile_budget.limit
  with pytest.raises(ValidationError, match='used up'):
    link.tile('light', 3, 1, 2)


def test_budget_counts_from_two_processes_add_up(tmp_path):
  galaxy, starview = MonthlyBudget('staticTiles', tmp_path), MonthlyBudget('staticTiles', tmp_path)
  galaxy.spend(3)
  starview.spend(2)
  galaxy.spend(1)
  assert json.loads((tmp_path / 'staticTiles.json').read_text())['used'] == 6
  assert MonthlyBudget('staticTiles', tmp_path).remaining() == galaxy.limit - 6


class Executor:
  def __init__(self):
    self.calls, self.jobs = [], []

  def submit(self, *args):
    self.calls.append(args)
    future = Future()
    self.jobs.append(future)
    return future


def test_traffic_refresh_keeps_the_road_being_driven(owner):
  executor = Executor()
  runtime = RouteRuntime(owner, engine=SimpleNamespace(fetch=None), executor=executor)
  fast, other = NavigationRoute(mapbox_route(duration=300.)), NavigationRoute(mapbox_route(lat=.004, duration=330.))
  fast.alternatives = [fast, other]
  t = 10_000_000_000
  at = (t - 1_000_000, (.001, 0.), 10., 90.)
  runtime.update(t, at, 1)
  executor.jobs[0].set_result(fast)
  runtime.update(t + 1, at, 1)
  owner.select_route(1, owner.read()['revision'], True)          # the driver picked the other road
  assert runtime.update(t + 2, (t + 1, (.001, .004), 10., 90.), 1)['status'] == 'guiding'
  assert runtime.route is other and len(executor.jobs) == 1
  # 5 minutes on: asked again; Mapbox now lists the driven road first
  later = t + REFRESH_NS + 3
  runtime.update(later, (later - 1, (.002, .004), 10., 90.), 1)
  assert len(executor.jobs) == 2 and executor.calls[1][2] == (.002, .004)
  other2, fast2 = NavigationRoute(mapbox_route(lat=.004, duration=280.)), NavigationRoute(mapbox_route(duration=310.))
  other2.alternatives = [other2, fast2]
  executor.jobs[1].set_result(other2)
  result = runtime.update(later + 1, (later, (.002, .004), 10., 90.), 1)
  assert result['status'] == 'guiding' and runtime.route is other2     # same road, fresh traffic
  assert [r['durationSeconds'] for r in owner.route_options(owner.read()['revision'])] == [310., 280.]
  # a refresh that fails keeps the route
  much_later = later + REFRESH_NS + 2
  runtime.update(much_later, (much_later - 1, (.002, .004), 10., 90.), 1)
  executor.jobs[2].set_exception(ValidationError('offline'))
  assert runtime.update(much_later + 1, (much_later, (.002, .004), 10., 90.), 1)['status'] == 'guiding'
  assert runtime.route is other2
  # leaving the route drops a refresh asked from the old position
  stale = much_later + REFRESH_NS + 5
  runtime.update(stale, (stale - 1, (.002, .004), 10., 90.), 1)
  assert runtime.refreshing and len(executor.jobs) == 4
  off = (stale, (.002, .02), 10., 90.)
  runtime.update(stale + 1, off, 1)
  runtime.update(stale + 2_000_000_002, off, 1)
  assert runtime.future is None and not runtime.refreshing and runtime.rerouting
  executor.jobs[3].set_result(other2)                 # arrives late: not used
  runtime.update(stale + 2_000_000_003, off, 1)
  assert len(executor.jobs) == 5 and runtime.route is None
  # the reroute: Mapbox's best new route is driven (it goes where the old choice was)
  r1, r2 = NavigationRoute(mapbox_route(duration=200.)), NavigationRoute(mapbox_route(lat=.004, duration=260.))
  r1.alternatives = [r1, r2]
  executor.jobs[4].set_result(r1)
  runtime.update(stale + 2_000_000_004, (stale + 2_000_000_003, (.001, 0.), 10., 90.), 1)
  assert runtime.route is r1


def test_keep_road_orders_the_driven_road_into_place():
  a, b = NavigationRoute(mapbox_route()), NavigationRoute(mapbox_route(lat=.004))
  assert keep_road(a, 0., [b], 0) == [b]
  assert keep_road(a, 0., [b, a], 0) == [a, b]
  assert keep_road(a, 0., [b, a], 1) == [b, a]
  assert keep_road(a, 0., [b, a], 2) == [a, b]          # the choice is gone: the runtime drives the first one


def shared_then_split(lat):
  # both go east 2 km on the same road, then split north / south
  raw = mapbox_route()
  raw['geometry']['coordinates'] = [[0., 0.], [.009, 0.], [.018, 0.], [.027, lat], [.036, lat * 2]]
  return NavigationRoute(raw)


def test_keep_road_looks_past_a_shared_start():
  north, south = shared_then_split(.01), shared_then_split(-.01)
  # driving the south one; Mapbox now lists north first: south must stay in the driven place
  assert keep_road(south, 0., [north, south], 1) == [north, south]
  assert keep_road(south, 0., [south, north], 1) == [north, south]
  assert keep_road(north, 0., [south, north], 0) == [north, south]


def test_after_leaving_the_route_the_best_new_one_is_driven():
  a, b, c = (NavigationRoute(mapbox_route(duration=d)) for d in (300., 400., 500.))
  assert fastest_first([a, b, c], 2) == [b, c, a]
  assert fastest_first([a, b, c], 0) == [a, b, c]
  assert fastest_first([a, b], 2) == [a, b]
  assert fastest_first([a, b], 1) == [b, a]


def test_choice_past_the_routes_offered_shows_the_first(owner):
  link = NavLink(owner=owner)
  three = [NavigationRoute(mapbox_route(lat=lat)) for lat in (0., .001, .002)]
  owner.record_routes(owner.read()['revision'], three)
  link.select_route(2)
  owner.record_routes(owner.read()['revision'], [NavigationRoute(mapbox_route())])
  assert link.state()['selectedRoute'] == 0


def test_refused_carpool_lanes_route_without_them(monkeypatch):
  calls = []
  def answer(session, url, params):
    calls.append(dict(params))
    if 'include' in params:
      raise ValidationError('The map service could not complete this request')
    return {'code': 'Ok', 'routes': [mapbox_route()]}
  monkeypatch.setattr(ENGINE, answer)
  MapboxRouteEngine(None).fetch('pk.test', (0., 0.), PLACE, None, ('toll', '+hov2'))
  assert [(c.get('exclude'), c.get('include')) for c in calls] == [('toll', 'hov2'), ('toll', None)]
