"""Fork patch (StarView): Mapbox requests through the tablet when the comma has no internet; since the Nov 16 sync the
relay wraps upstream's pooled session, and Google's requests (routes, tiles, places) only ever go straight out."""
import requests

from openpilot.starpilot.navigation import relay
from openpilot.starpilot.navigation.owner import NavigationOwner


class FakeSession:
  def __init__(self, down=False):
    self.down, self.calls = down, []

  def get(self, url, **kwargs):
    self.calls.append(('get', url, kwargs.get('proxies')))
    if self.down and not kwargs.get('proxies'):
      raise requests.ConnectionError('no route')
    return 'ok'

  def post(self, url, **kwargs):
    self.calls.append(('post', url, kwargs.get('proxies')))
    return 'posted'


def _relay_file(tmp_path):
  path = tmp_path / 'relay'
  path.write_text('192.168.42.129:8765')
  return str(path)


def test_mapbox_falls_back_to_the_tablet_and_stays_there_a_minute(tmp_path):
  now = [100.]
  session = FakeSession(down=True)
  r = relay.RelaySession(_relay_file(tmp_path), clock=lambda: now[0], session=session)
  assert r.get('https://api.mapbox.com/directions/v5/x') == 'ok'
  assert session.calls == [('get', 'https://api.mapbox.com/directions/v5/x', None),
                           ('get', 'https://api.mapbox.com/directions/v5/x', {'https': 'http://192.168.42.129:8765'})]
  session.calls.clear()
  now[0] += 30
  r.get('https://api.mapbox.com/styles/v1/x')
  assert session.calls == [('get', 'https://api.mapbox.com/styles/v1/x', {'https': 'http://192.168.42.129:8765'})]


def test_google_never_goes_through_the_tablet(tmp_path):
  session = FakeSession(down=True)
  r = relay.RelaySession(_relay_file(tmp_path), session=session)
  try:
    r.get('https://tile.googleapis.com/v1/2dtiles/1/0/0')
    raise AssertionError('should not reach Google without the comma\'s own internet')
  except requests.ConnectionError:
    pass
  assert r.post('https://routes.googleapis.com/directions/v2:computeRoutes', json={}) == 'posted'
  assert all(proxies is None for _, _, proxies in session.calls)


def test_owner_default_session_is_pooled_and_relayed(tmp_path):
  owner = NavigationOwner(tmp_path / 'nav', transient_root=tmp_path / 'shm')
  assert isinstance(owner.session, relay.RelaySession)
  assert isinstance(owner.session.session, requests.Session)
  given = FakeSession()
  assert NavigationOwner(tmp_path / 'nav2', session=given, transient_root=tmp_path / 'shm2').session is given
