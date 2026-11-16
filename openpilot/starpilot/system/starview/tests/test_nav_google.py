"""Galaxy's Google map / routes / places and its share rules on the StarView tablet (nav_link, Nov 16 sync)."""
from io import BytesIO

import pytest
from PIL import Image

from openpilot.starpilot.navigation import google_routes, google_tiles
from openpilot.starpilot.navigation.owner import NavigationOwner, ValidationError
from openpilot.starpilot.navigation.route_engine import NavigationRoute
from openpilot.starpilot.system.starview import nav_link
from openpilot.starpilot.system.starview.nav_link import NavLink, join_tiles
from openpilot.starpilot.system.starview.tests.test_nav_link import PLACE, mapbox_route

KEY = 'AIza' + 'x' * 35
COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]


def png(color, size=256):
  buf = BytesIO()
  Image.new('RGB', (size, size), color).save(buf, 'PNG')
  return buf.getvalue()


@pytest.fixture
def owner(tmp_path, monkeypatch):
  monkeypatch.setattr(NavigationOwner, '_is_metric', lambda self: False)
  o = NavigationOwner(tmp_path, runtime_source=lambda: None, transient_root=tmp_path / 'runtime')
  o.configure({'enabled': True, 'token': 'pk.test'}, '0', True)
  return o


def test_four_google_tiles_make_one_512_tile():
  with Image.open(BytesIO(join_tiles([png(c) for c in COLORS]))) as im:
    assert im.size == (512, 512)
    assert [im.getpixel(p) for p in ((10, 10), (500, 10), (10, 500), (500, 500))] == COLORS


def test_google_map_tiles_one_zoom_deeper_and_mapbox_when_google_cant(owner, monkeypatch):
  link = NavLink(owner=owner)
  calls = []

  def fetch(key, z, x, y, theme, **kw):
    calls.append((key, z, x, y, theme))
    return png(COLORS[len(calls) - 1])
  monkeypatch.setattr(google_tiles, 'fetch_tile', fetch)
  monkeypatch.setattr(owner, 'map_tile', lambda z, x, y, theme='light', **kw: f'mapbox {theme}'.encode())
  # Map provider still Mapbox: Mapbox's traffic map, Google never asked
  assert link.tile('trafficGoogleDark', 3, 1, 2) == b'mapbox trafficDark' and calls == []
  link.google('set', {'mapProvider': 'google', 'googleKey': KEY})
  with Image.open(BytesIO(link.tile('trafficGoogleLight', 3, 1, 2))) as im:
    assert im.size == (512, 512) and im.getpixel((500, 500)) == COLORS[3]
  assert calls == [(KEY, 4, 2, 4, 'light'), (KEY, 4, 3, 4, 'light'), (KEY, 4, 2, 5, 'light'), (KEY, 4, 3, 5, 'light')]

  def refused(*a, **kw):
    raise ValueError("This month's free Google map tiles are used up.")
  monkeypatch.setattr(google_tiles, 'fetch_tile', refused)
  assert link.tile('trafficGoogleDark', 3, 1, 2) == b'mapbox trafficDark'
  status = link.google('status')
  assert status['map'] and 'used up' in status['failures']['map']
  calls.clear()
  monkeypatch.setattr(google_tiles, 'fetch_tile', fetch)
  assert link.tile('trafficGoogleDark', 3, 1, 2) == b'mapbox trafficDark' and calls == []   # a minute on Mapbox
  link._google_down_until = 0.
  assert link.tile('trafficGoogleDark', 3, 1, 2) != b'mapbox trafficDark'


def test_google_settings_from_the_tablet(owner):
  link = NavLink(owner=owner)
  s = link.google('status')
  assert s['mapProvider'] == 'mapbox' and not s['hasKey'] and not s['map'] and not s['routes']
  s = link.google('set', {'mapProvider': 'google', 'routeProvider': 'google', 'googleKey': KEY})
  assert s['map'] and s['routes'] and s['hasKey'] and KEY not in str(s)
  assert s['usage']['map']['monthUsed'] == 0 and 'monthLimit' in s['usage']['routes']
  assert owner.read()['googleKey'] == KEY
  for bad in ({'googleKey': 'short'}, {'mapProvider': 'bing'}, {'token': 'pk.x'}, {}):
    with pytest.raises(ValidationError):
      link.google('set', bad)
  with pytest.raises(ValidationError):
    link.google('delete')


def test_preview_asks_google_when_it_routes_and_mapbox_when_it_cant(owner, monkeypatch):
  link = NavLink(owner=owner)
  asked = []
  monkeypatch.setattr(nav_link.NavLink, '_route_engine', lambda self: type('M', (), {'fetch': lambda _, *a: asked.append(('mapbox', a)) or
                                                                                      NavigationRoute(mapbox_route())})())
  monkeypatch.setattr(google_routes.GoogleRouteEngine, 'fetch', lambda self, *a: asked.append(('google', a)) or NavigationRoute(mapbox_route()))
  origin = {'latitude': .001, 'longitude': 0., 'bearing': 90.}
  link.preview(PLACE, origin)
  assert asked[-1][0] == 'mapbox' and asked[-1][1][3] == 90.
  link.google('set', {'routeProvider': 'google', 'googleKey': KEY})
  res = link.preview(PLACE, origin)
  assert asked[-1][0] == 'google' and asked[-1][1][0] == KEY and asked[-1][1][3] is None and res['routes']

  def fails(self, *a):
    raise google_routes.GoogleRoutesFailed(google_routes.FAILURE_BUDGET)
  monkeypatch.setattr(google_routes.GoogleRouteEngine, 'fetch', fails)
  assert link.preview(PLACE, origin)['routes'] and asked[-1][0] == 'mapbox'


def test_shared_links_read_with_upstreams_rules(owner):
  link = NavLink(owner=owner)
  waze = link.share_parse('Use Waze to drive to Pizza: https://waze.com/ul/hdr5ru7v2m')
  assert waze['place']['latitude'] == pytest.approx(40.7, abs=.1) and waze['place']['longitude'] == pytest.approx(-74.0, abs=.1)
  google = link.share_parse('https://www.google.com/maps/place/Library/@40.1,-73.2,17z/data=!3d40.11!4d-73.22')
  assert google['place'] == {'name': 'Library', 'latitude': 40.11, 'longitude': -73.22}
  assert link.share_parse('https://maps.apple.com/?q=Corner%20Bakery')['query'] == 'Corner Bakery'
  with pytest.raises(ValidationError):
    link.share_parse('')


def test_google_suggestions_carry_distance_and_kind_for_the_search_list(tmp_path):
  import json
  from openpilot.starpilot.navigation import google_places
  sent = []

  class Response:
    status_code = 200
    headers = {}

    def __init__(self, body):
      self.raw_body = json.dumps(body).encode()

    def __enter__(self):
      return self

    def __exit__(self, *a):
      return False

    def iter_content(self, size):
      yield self.raw_body

  class Http:
    def post(self, url, json=None, **kw):
      sent.append(json)
      return Response({'suggestions': [
        {'placePrediction': {'placeId': 'p1', 'text': {'text': 'Shell'}, 'distanceMeters': 1609,
                             'types': ['gas_station', 'point_of_interest', 'establishment'],
                             'structuredFormat': {'mainText': {'text': 'Shell'}, 'secondaryText': {'text': 'Main St'}}}},
        {'placePrediction': {'placeId': 'p2', 'text': {'text': '12 Elm St'}, 'types': ['street_address']}}]})

  rows = google_places.autocomplete(Http(), KEY, 'shell', 'session', google_places.suggestions_budget(tmp_path), (-74., 40.7))
  assert sent[0]['origin'] == {'latitude': 40.7, 'longitude': -74.} and 'locationBias' in sent[0]
  assert rows[0] == {'id': 'p1', 'name': 'Shell', 'description': 'Main St', 'distanceMeters': 1609., 'maki': 'fuel',
                     'category': 'Gas station'}
  assert rows[1] == {'id': 'p2', 'name': '12 Elm St', 'description': ''}
  google_places.autocomplete(Http(), KEY, 'shell', 'session', google_places.suggestions_budget(tmp_path), None)
  assert 'origin' not in sent[1]
