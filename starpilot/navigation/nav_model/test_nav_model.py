"""Tests for the navigation-model inputs (ported from commaai/openpilot nav-model-integration, Oct 2026: tiles,
rendering, route tracking, remote tiles), plus StarPilot's maneuver encoding and custom tile URL."""
import gzip
import re
import struct
import threading
import time
from contextlib import closing, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import numpy as np
import pytest
import requests

from openpilot.starpilot.navigation.nav_model.helpers import navigation_input, starpilot_navigation_input, valhalla_type
from openpilot.starpilot.navigation.nav_model.pmtiles import PMTiles, decode_directory, tile_id
from openpilot.starpilot.navigation.nav_model.renderer import (MAJOR, MEDIUM, MINOR, SIZE, STREET, TRACK, MapRenderer, draw_segments,
                                                                mercator, project, stroke_widths)
from openpilot.starpilot.navigation.nav_model.route import RouteTracker
from openpilot.starpilot.navigation.nav_model.tiles import RemoteTiles, custom_url
from openpilot.starpilot.navigation.nav_model.vector_tile import decode_lines, decode_roads

T = 'openpilot.starpilot.navigation.nav_model.tiles'


METER = 1 / 111319.49079327358  # degrees of latitude


def draw_line(image, points, intensity, width, **kwargs):
  draw_segments(image, points[:-1], points[1:], width / 2, intensity, **kwargs)


def varint(value):
  output = bytearray()
  while value > 127:
    output.append((value & 127) | 128)
    value >>= 7
  output.append(value)
  return bytes(output)


def field(number, value):
  if isinstance(value, bytes):
    return varint(number << 3 | 2) + varint(len(value)) + value
  return varint(number << 3) + varint(value)


def road_tile(crossing=None):
  # One vertical line, from (2048, 0) to (2048, 4096), and one non-road layer. With crossing='bridge' or 'tunnel',
  # a horizontal line from (1024, 2048) to (3072, 2048) at that level.
  geometry = b''.join(varint(v) for v in [9, 4096, 0, 10, 0, 8192])
  feature = field(2, b'\x00\x00') + field(3, 2) + field(4, geometry)
  roads = field(15, 2) + field(1, b'roads') + field(2, feature)
  if crossing is not None:
    geometry = b''.join(varint(v) for v in [9, 2048, 4096, 10, 4096, 0])
    roads += field(2, field(2, b'\x00\x00\x01\x01') + field(3, 2) + field(4, geometry))
  roads += field(3, b'kind') + field(3, f'is_{crossing}'.encode()) + field(4, field(1, b'minor_road')) + field(4, field(7, 1)) + field(5, 4096)
  return field(3, field(1, b'buildings')) + field(3, roads)


def make_archive(payload=None, leaf=False, run=1, max_zoom=0):
  """A PMTiles archive with one zoom-zero tile, in the root directory or in a leaf directory."""
  tile = gzip.compress(road_tile() if payload is None else payload)
  directory = gzip.compress(varint(1) + varint(0) + varint(run) + varint(len(tile)) + varint(1))
  child = directory if leaf else b''
  root = gzip.compress(varint(1) + varint(0) + varint(0) + varint(len(child)) + varint(1)) if leaf else directory
  metadata = gzip.compress(b'{"vector_layers":[{"id":"roads"}]}')
  header = bytearray(127)
  header[:8] = b'PMTiles\x03'
  offsets = [127, 127 + len(root), 127 + len(root) + len(metadata), 127 + len(root) + len(metadata) + len(child)]
  struct.pack_into('<11Q', header, 8, offsets[0], len(root), offsets[1], len(metadata), offsets[2], len(child), offsets[3], len(tile), 1, 1, 1)
  header[96:102] = bytes([1, 2, 2, 1, 0, max_zoom])
  return bytes(header + root + metadata + child + tile)



class _MemorySource:
  def __init__(self, data):
    self.data, self.size = data, len(data)

  def read(self, offset, length):
    return self.data[offset:offset + length]

  def prefetch(self, ranges):
    pass

  def close(self):
    pass


@contextmanager
def local_archive(data):
  """A PMTiles reader over in-memory bytes, bypassing the tile server."""
  with closing(PMTiles(_MemorySource(data))) as archive:
    yield archive


class RangeHandler(BaseHTTPRequestHandler):
  def do_GET(self):
    self.server.requests.append(dict(self.headers))
    if self.headers.get('If-Match', self.server.etag) != self.server.etag:
      self.send_error(412)
      return
    if self.server.ignore_range:
      self.send_response(200)
      self.end_headers()
      return
    offset, end = map(int, re.fullmatch(r'bytes=(\d+)-(\d+)', self.headers['Range']).groups())
    data = self.server.archive[offset:end + 1]
    self.send_response(206)
    self.send_header('Content-Range', f'bytes {offset}-{end}/{len(self.server.archive)}')
    self.send_header('Content-Length', str(len(data)))
    self.send_header('ETag', self.server.etag)
    self.end_headers()
    self.wfile.write(data)

  def log_message(self, format: str, *args: object) -> None:  # noqa: A002  # stdlib override
    pass


@pytest.fixture
def tiles(tmp_path, mocker):
  """Serves a leaf-directory archive over HTTP range requests, with the comma API and tile cache stubbed."""
  server = ThreadingHTTPServer(('127.0.0.1', 0), RangeHandler)
  server.archive = make_archive(leaf=True)
  server.etag = '"test-version"'
  server.ignore_range = False
  server.requests = []
  threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True).start()
  api = mocker.MagicMock(dongle_id='test-dongle')
  api.get_token.return_value = 'device-token'
  url = f'http://127.0.0.1:{server.server_port}/planet.pmtiles?sig=secret'
  api.get.return_value.json.return_value = {'url': url, 'expires': time.time() + 86400}  # noqa: TID251 - SAS expiry is a Unix timestamp
  mocker.patch(f'{T}.Api', mocker.MagicMock(return_value=api))
  mocker.patch(f'{T}.Params', mocker.MagicMock())
  mocker.patch(f'{T}.PC', True)
  mocker.patch(f'{T}.Paths.comma_home', return_value=str(tmp_path))
  mocker.patch(f'{T}.CUSTOM_URL_FILE', tmp_path / 'no_url')
  yield SimpleNamespace(server=server, api=api, url=url, cache=tmp_path / 'navigation' / 'tiles', dir=tmp_path)
  server.shutdown()
  server.server_close()


def test_remote_tiles_shared_cache_and_refresh(tiles, mocker):
  with closing(PMTiles(RemoteTiles())) as archive:
    archive.source.expires = 0  # the signed URL is refreshed before the next fetch
    assert archive.get(0, 0, 0) == road_tile()
    assert archive.get(0, 0, 0) == road_tile()
    assert tiles.api.get.call_count == 2
  count = len(tiles.server.requests)
  with closing(PMTiles(RemoteTiles())) as archive:
    assert archive.get(0, 0, 0) == road_tile()
  # A second reader revalidates only the header; directories and tiles are shared on disk.
  assert len(tiles.server.requests) == count + 1
  mocker.patch(f'{T}.CACHE_LIMIT', 1)
  with closing(RemoteTiles()) as source:
    source.read(1, 2)  # an uncached range is downloaded, then the cache is trimmed to the limit
  assert [p.name for p in tiles.cache.iterdir()] == ['version']


def test_remote_tiles_prefetch_merges_nearby_ranges(tiles, mocker):
  mocker.patch(f'{T}.MERGE_GAP', 16)
  with closing(RemoteTiles()) as source:
    count = len(tiles.server.requests)
    source.prefetch([(20, 10), (0, 10), (60, 10), (20, 10)])
    assert len(tiles.server.requests) == count + 2  # 0-29 in one request, 60-69 in another
    assert tiles.server.requests[-2]['Range'] == 'bytes=0-29'
    for offset in (0, 20, 60):
      assert source.read(offset, 10) == tiles.server.archive[offset:offset + 10]
    assert len(tiles.server.requests) == count + 2


def test_remote_tiles_failures(tiles):
  with closing(PMTiles(RemoteTiles())) as archive:
    tiles.server.etag = '"new-version"'
    with pytest.raises(OSError, match='412'):  # the archive changed under an open reader
      archive.get(0, 0, 0)
  with closing(PMTiles(RemoteTiles())) as archive:  # a new reader starts over on the new version
    assert archive.get(0, 0, 0) == road_tile()
  tiles.server.ignore_range = True
  with pytest.raises(OSError, match='200'):
    RemoteTiles()
  tiles.api.get.return_value.raise_for_status.side_effect = requests.HTTPError(tiles.url)
  with pytest.raises(OSError, match='^Unable to fetch map tiles$'):  # the signed URL stays out of the error
    RemoteTiles()


def test_custom_tiles_url_without_api(tiles, mocker):
  url_file = tiles.dir / 'nav_tiles_url'
  url_file.write_text('https://example.invalid/x.pmtiles\n')
  mocker.patch(f'{T}.CUSTOM_URL_FILE', url_file)
  assert custom_url() == 'https://example.invalid/x.pmtiles'
  url_file.write_text('http://plain.invalid/x.pmtiles')
  assert custom_url() == ''  # https only
  # a custom URL is read directly: no comma API call
  mocker.patch(f'{T}.custom_url', return_value=tiles.url)
  with closing(PMTiles(RemoteTiles())) as archive:
    assert archive.get(0, 0, 0) == road_tile()
  tiles.api.get.assert_not_called()


def test_pmtiles_format():
  assert [tile_id(1, x, y) for x, y in [(0, 0), (0, 1), (1, 1), (1, 0)]] == [1, 2, 3, 4]
  assert sorted(tile_id(3, x, y) for x in range(8) for y in range(8)) == list(range(21, 85))
  # IDs 5, 10; runs 3, 1; lengths 4, 6; the second offset follows the first blob.
  data = bytes([2, 5, 5, 3, 1, 4, 6, 1, 0])
  assert decode_directory(data) == ([5, 10], [(3, 4, 0), (1, 6, 4)])
  for invalid in (b'\x80', b'\x01\x00\x01\x01\x00', data + b'\x00'):
    with pytest.raises(ValueError):
      decode_directory(invalid)
  with local_archive(make_archive(run=3, max_zoom=1)) as archive:  # the zoom-zero tile is also addressed by IDs 1 and 2
    assert archive.get(1, 0, 1) == road_tile()
    assert archive.get(1, 1, 1) is None
  with pytest.raises(ValueError), local_archive(make_archive()[:-1]):
    pass


def test_vector_tiles():
  roads = decode_roads(road_tile())
  assert (len(roads), roads[0].kind) == (1, 'minor_road')
  np.testing.assert_array_equal(roads[0].points, [[0.5, 0], [0.5, 1]])
  lines = decode_lines([9, 20, 20, 10, 10, 0, 9, 9, 9, 10, 0, 10])
  np.testing.assert_array_equal(lines[0], [[10, 10], [15, 10]])
  np.testing.assert_array_equal(lines[1], [[10, 5], [10, 10]])
  for data in (b'\x1a\xff', b'\x00', b'\x1a\x02\x0a\x04'):
    with pytest.raises(ValueError):
      decode_roads(data)
  for commands in ([10, 1, 1], [9, 0], [9, 0, 0, 15]):
    with pytest.raises(ValueError):
      decode_lines(commands)


def test_projection():
  # At the equator, 64m ahead is the image center and the car is 64px below it, at 1m per pixel.
  points = mercator(np.array([[0, 0], [0, 64 * METER], [64 * METER, 0]]))
  np.testing.assert_allclose(project(points, 0, 0, 0), [[128, 192], [128, 128], [192, 192]], atol=1e-5)
  np.testing.assert_allclose(project(points, 0, 0, 90), [[128, 192], [64, 192], [128, 128]], atol=1e-5)
  pixels = project(mercator(np.array([[-179.999, 0]])), 179.999, 0, 90)  # across the antimeridian
  assert pixels[0, 1] == pytest.approx(192 - 222.6389816, abs=1e-5)


def test_strokes():
  image = np.zeros((SIZE, SIZE), dtype=np.uint8)
  draw_line(image, np.array([[-1000, 128], [1000, 128]]), 255, 8)
  assert np.all(image[128] == 255)
  draw_line(image, np.array([[128, 0], [128, 256]]), 128, 5, overlay=True)  # the grey route replaces the white road
  assert (image[128, 128], image[128, 131]) == (128, 255)
  before = image.copy()
  draw_line(image, np.array([[-1000, -1000], [-500, -500]]), 255, 5)
  np.testing.assert_array_equal(image, before)
  draw_line(image, np.array([[40, 40], [40, 40]]), 255, 5)  # a zero-length segment is still a dot
  assert image[40, 40] == 255


def test_crossings():
  route = np.array([[0.01, 0], [0.01, 0.01]])  # off to the side, out of the way of the probes
  images = {}
  for crossing in ('bridge', 'tunnel'):
    with local_archive(make_archive(road_tile(crossing))) as archive:
      images[crossing] = MapRenderer(archive).render(0, -40 * METER, 0, route)[0]  # the crossing 40m ahead
  # The horizontal road crosses the vertical one 40px above the ego, at row 152. A bridge severs the road beneath
  # just outside its own stroke; a tunnel passes underneath untouched. The cut has butt caps, so the
  # bridge's own end is not wrapped in black.
  bridge, tunnel = images['bridge'], images['tunnel']
  assert (bridge[146, 128], bridge[152, 128], bridge[152, 200], bridge[140, 128]) == (0, 255, 255, 255)
  assert (tunnel[146, 128], tunnel[152, 200]) == (255, 255)
  # The ground road cuts over the tunnel beneath it, and the tunnel is drawn without its casing.
  assert (tunnel[152, 133], tunnel[147, 200]) == (0, 0)


def test_road_widths():
  # Pinned at the style zoom of 1 m per pixel: 16.26 at the equator and 15.26 at 60 degrees. Tunnels have no casing.
  styles, levels = np.array([MAJOR, MEDIUM, STREET, MINOR, TRACK, STREET]), np.array([0, 0, 0, 0, 0, -1])
  np.testing.assert_allclose(stroke_widths(16.256, styles, levels), [19.02, 15.48, 9.86, 6.70, 7.02, 7.89], atol=0.01)
  np.testing.assert_allclose(stroke_widths(15.256, styles, levels), [13.52, 10.78, 6.39, 4.16, 4.58, 4.62], atol=0.01)


def test_route_tiles():
  route = np.array([[0, -0.01], [0, 0.01]])  # 2.2 km north along the prime meridian
  with local_archive(make_archive(max_zoom=15)) as archive:
    tiles = MapRenderer(archive).route_tiles(route)
    # Both columns beside the meridian, and the rows within the view radius of the route's ends.
    assert {x for x, _ in tiles} == {16383, 16384}
    assert {y for _, y in tiles} == set(range(16382, 16386))


def test_validity_and_display(mocker):
  route = np.array([[0, -0.01], [0, 0.01]])
  with local_archive(make_archive()) as archive:
    renderer = MapRenderer(archive)
    assert renderer.render(0, 0, 0, route)[1]
    assert not renderer.render(0.01, 0, 0, route)[1]  # no road near the ego
    mocker.patch.object(archive, 'get', return_value=None)  # a missing tile
    image, valid = MapRenderer(archive).render(0, 0, 0, route)
    assert not valid
    assert image[128, 128] == 128  # the route is still drawn
  with local_archive(make_archive(field(3, field(1, b'buildings')))) as archive:  # tiles without roads
    assert not MapRenderer(archive).render(0, 0, 0, route)[1]


def test_snap_heading_and_window():
  m = METER
  tracker = RouteTracker(np.array([[0, 0], [0, 200 * m], [200 * m, 200 * m]]))  # north 200m, then east 200m
  longitude, latitude, bearing = tracker.snap(3 * m, 100 * m)  # 3m right of the first leg
  assert tracker.progress == pytest.approx(100, abs=0.5)
  assert longitude == pytest.approx(0, abs=1e-7)  # lateral error removed
  assert latitude == pytest.approx(100 * m, abs=1e-7)
  assert bearing == pytest.approx(0, abs=5e-4)
  assert tracker.snap(0, 200 * m)[2] == pytest.approx(45, abs=5e-3)  # at the corner the +-50m chord is mid-turn
  assert tracker.snap(0, 150 * m)[2] == pytest.approx(45, abs=5e-3)  # progress never decreases
  tracker.snap(100 * m, 200 * m)  # progress 300: the window ahead no longer includes the first leg
  assert tracker.snap(150 * m, 200 * m)[0] == pytest.approx(150 * m, abs=1e-7)  # so the window's offset is applied
  assert tracker.snap(200 * m, 200 * m)[2] == pytest.approx(90, abs=5e-3)  # the chord clips at the route's end
  # Out and back along the same road: a fix near the far leg stays on the outbound leg within the window,
  # while a fresh tracker searches anywhere and lands on the return leg.
  route = np.array([[0, 0], [0, 1000 * m], [10 * m, 1000 * m], [10 * m, 0]])
  tracker = RouteTracker(route)
  tracker.snap(1 * m, 100 * m)
  assert tracker.snap(9 * m, 150 * m)[2] == pytest.approx(0, abs=5e-4)
  assert tracker.progress == pytest.approx(150, abs=0.5)
  assert RouteTracker(route).snap(9 * m, 150 * m)[2] == pytest.approx(180, abs=5e-4)


def test_starpilot_maneuvers_leave_out_the_current_step():
  M = SimpleNamespace
  # StarPilot: [current step (its turn already made, distance to the end of the step), next steps at their start]
  maneuvers = [M(type='turn', modifier='right', distance=300.0), M(type='off ramp', modifier='right', distance=300.0),
               M(type='fork', modifier='left', distance=900.0)]
  nav = starpilot_navigation_input(maneuvers, 20.0)
  assert int(np.argmax(nav[:-1])) == valhalla_type('off ramp', 'right')
  assert float(nav[-1]) == pytest.approx(2.8)  # (300 - 20) / 100
  assert nav.shape == (47,)
  # comma's helper on the raw list would have taken the turn already made
  assert int(np.argmax(navigation_input(maneuvers, 20.0)[:-1])) == valhalla_type('turn', 'right')
  # passed (negative distance) and depart/arrive (<= 6) are skipped; nothing left -> all zeros
  passed = [M(type='turn', modifier='left', distance=5.0), M(type='arrive', modifier='', distance=50.0)]
  assert float(starpilot_navigation_input(passed, 0.0).sum()) == 0.0
  assert valhalla_type('merge', 'left') is None
