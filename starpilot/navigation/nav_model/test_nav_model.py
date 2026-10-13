"""Tests for the navigation-model inputs (ported from commaai/openpilot nav-model-integration, Oct 2026: tiles,
rendering, route tracking, remote tiles), plus StarPilot's maneuver encoding and custom tile URL."""
import gzip
import re
import struct
import tempfile
import threading
import time
import unittest
from contextlib import closing, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import requests

from openpilot.starpilot.navigation.nav_model.helpers import navigation_input, starpilot_navigation_input, valhalla_type
from openpilot.starpilot.navigation.nav_model.pmtiles import PMTiles, decode_directory, tile_id
from openpilot.starpilot.navigation.nav_model.renderer import MAJOR, MEDIUM, MINOR, SIZE, STREET, TRACK, MapRenderer, draw_segments, mercator, project, stroke_widths
from openpilot.starpilot.navigation.nav_model.route import RouteTracker
from openpilot.starpilot.navigation.nav_model.tiles import RemoteTiles
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


@contextmanager
def local_archive(data):
  """A PMTiles reader over in-memory bytes, bypassing the tile server."""
  source = MagicMock(size=len(data))
  source.read.side_effect = lambda offset, length: data[offset:offset + length]
  with closing(PMTiles(source)) as archive:
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


class TileServerCase(unittest.TestCase):
  """Serves a leaf-directory archive over HTTP range requests, with the comma API and tile cache stubbed."""

  def setUp(self):
    self.directory = tempfile.TemporaryDirectory()
    self.addCleanup(self.directory.cleanup)
    self.cache = Path(self.directory.name) / 'navigation' / 'tiles'
    self.server = ThreadingHTTPServer(('127.0.0.1', 0), RangeHandler)
    self.server.archive = make_archive(leaf=True)
    self.server.etag = '"test-version"'
    self.server.ignore_range = False
    self.server.requests = []
    threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True).start()
    self.addCleanup(self.server.server_close)
    self.addCleanup(self.server.shutdown)
    self.api = MagicMock(dongle_id='test-dongle')
    self.api.get_token.return_value = 'device-token'
    self.url = f'http://127.0.0.1:{self.server.server_port}/planet.pmtiles?sig=secret'
    self.api.get.return_value.json.return_value = {'url': self.url, 'expires': time.time() + 86400}  # noqa: TID251
    for name, value in [('Api', MagicMock(return_value=self.api)), ('Params', MagicMock()), ('PC', True)]:
      self.enterContext(patch(f'{T}.{name}', value))
    self.enterContext(patch(f'{T}.Paths.comma_home', return_value=self.directory.name))
    self.enterContext(patch(f'{T}.CUSTOM_URL_FILE', Path(self.directory.name) / 'no_url'))



class TestRemoteTiles(TileServerCase):
  def test_shared_cache_and_refresh(self):
    with closing(PMTiles(RemoteTiles())) as archive:
      archive.source.expires = 0  # the signed URL is refreshed before the next fetch
      self.assertEqual(archive.get(0, 0, 0), road_tile())
      self.assertEqual(archive.get(0, 0, 0), road_tile())
      self.assertEqual(self.api.get.call_count, 2)
    count = len(self.server.requests)
    with closing(PMTiles(RemoteTiles())) as archive:
      self.assertEqual(archive.get(0, 0, 0), road_tile())
    # A second reader revalidates only the header; directories and tiles are shared on disk.
    self.assertEqual(len(self.server.requests), count + 1)
    with patch(f'{T}.CACHE_LIMIT', 1), closing(RemoteTiles()) as source:
      source.read(1, 2)  # an uncached range is downloaded, then the cache is trimmed to the limit
    self.assertEqual([p.name for p in self.cache.iterdir()], ['version'])

  def test_prefetch_merges_nearby_ranges(self):
    with patch(f'{T}.MERGE_GAP', 16), closing(RemoteTiles()) as source:
      count = len(self.server.requests)
      source.prefetch([(20, 10), (0, 10), (60, 10), (20, 10)])
      self.assertEqual(len(self.server.requests), count + 2)  # 0-29 in one request, 60-69 in another
      self.assertEqual(self.server.requests[-2]['Range'], 'bytes=0-29')
      for offset in (0, 20, 60):
        self.assertEqual(source.read(offset, 10), self.server.archive[offset:offset + 10])
      self.assertEqual(len(self.server.requests), count + 2)

  def test_failures(self):
    with closing(PMTiles(RemoteTiles())) as archive:
      self.server.etag = '"new-version"'
      with self.assertRaisesRegex(OSError, '412'):  # the archive changed under an open reader
        archive.get(0, 0, 0)
    with closing(PMTiles(RemoteTiles())) as archive:  # a new reader starts over on the new version
      self.assertEqual(archive.get(0, 0, 0), road_tile())
    self.server.ignore_range = True
    with self.assertRaisesRegex(OSError, '200'):
      RemoteTiles()
    self.api.get.return_value.raise_for_status.side_effect = requests.HTTPError(self.url)
    with self.assertRaisesRegex(OSError, '^Unable to fetch map tiles$'):  # the signed URL stays out of the error
      RemoteTiles()



class TestTiles(unittest.TestCase):
  def test_pmtiles_format(self):
    self.assertEqual([tile_id(1, x, y) for x, y in [(0, 0), (0, 1), (1, 1), (1, 0)]], [1, 2, 3, 4])
    self.assertEqual(sorted(tile_id(3, x, y) for x in range(8) for y in range(8)), list(range(21, 85)))
    # IDs 5, 10; runs 3, 1; lengths 4, 6; the second offset follows the first blob.
    data = bytes([2, 5, 5, 3, 1, 4, 6, 1, 0])
    self.assertEqual(decode_directory(data), ([5, 10], [(3, 4, 0), (1, 6, 4)]))
    for invalid in (b'\x80', b'\x01\x00\x01\x01\x00', data + b'\x00'):
      with self.assertRaises(ValueError):
        decode_directory(invalid)
    with local_archive(make_archive(run=3, max_zoom=1)) as archive:  # the zoom-zero tile is also addressed by IDs 1 and 2
      self.assertEqual(archive.get(1, 0, 1), road_tile())
      self.assertIsNone(archive.get(1, 1, 1))
    with self.assertRaises(ValueError), local_archive(make_archive()[:-1]):
      pass

  def test_vector_tiles(self):
    roads = decode_roads(road_tile())
    self.assertEqual((len(roads), roads[0].kind), (1, 'minor_road'))
    np.testing.assert_array_equal(roads[0].points, [[0.5, 0], [0.5, 1]])
    lines = decode_lines([9, 20, 20, 10, 10, 0, 9, 9, 9, 10, 0, 10])
    np.testing.assert_array_equal(lines[0], [[10, 10], [15, 10]])
    np.testing.assert_array_equal(lines[1], [[10, 5], [10, 10]])
    for data in (b'\x1a\xff', b'\x00', b'\x1a\x02\x0a\x04'):
      with self.assertRaises(ValueError):
        decode_roads(data)
    for commands in ([10, 1, 1], [9, 0], [9, 0, 0, 15]):
      with self.assertRaises(ValueError):
        decode_lines(commands)


class TestRendering(unittest.TestCase):
  def test_projection(self):
    # At the equator, 64m ahead is the image center and the car is 64px below it, at 1m per pixel.
    points = mercator(np.array([[0, 0], [0, 64 * METER], [64 * METER, 0]]))
    np.testing.assert_allclose(project(points, 0, 0, 0), [[128, 192], [128, 128], [192, 192]], atol=1e-5)
    np.testing.assert_allclose(project(points, 0, 0, 90), [[128, 192], [64, 192], [128, 128]], atol=1e-5)
    pixels = project(mercator(np.array([[-179.999, 0]])), 179.999, 0, 90)  # across the antimeridian
    self.assertAlmostEqual(pixels[0, 1], 192 - 222.6389816, places=5)

  def test_strokes(self):
    image = np.zeros((SIZE, SIZE), dtype=np.uint8)
    draw_line(image, np.array([[-1000, 128], [1000, 128]]), 255, 8)
    self.assertTrue(np.all(image[128] == 255))
    draw_line(image, np.array([[128, 0], [128, 256]]), 128, 5, overlay=True)  # the grey route replaces the white road
    self.assertEqual((image[128, 128], image[128, 131]), (128, 255))
    before = image.copy()
    draw_line(image, np.array([[-1000, -1000], [-500, -500]]), 255, 5)
    np.testing.assert_array_equal(image, before)
    draw_line(image, np.array([[40, 40], [40, 40]]), 255, 5)  # a zero-length segment is still a dot
    self.assertEqual(image[40, 40], 255)

  def test_crossings(self):
    route = np.array([[0.01, 0], [0.01, 0.01]])  # off to the side, out of the way of the probes
    images = {}
    for crossing in ('bridge', 'tunnel'):
      with local_archive(make_archive(road_tile(crossing))) as archive:
        images[crossing] = MapRenderer(archive).render(0, -40 * METER, 0, route)[0]  # the crossing 40m ahead
    # The horizontal road crosses the vertical one 40px above the ego, at row 152. A bridge severs the road beneath
    # just outside its own stroke; a tunnel passes underneath untouched. The cut has butt caps, so the
    # bridge's own end is not wrapped in black.
    self.assertEqual((images['bridge'][146, 128], images['bridge'][152, 128], images['bridge'][152, 200], images['bridge'][140, 128]), (0, 255, 255, 255))
    self.assertEqual((images['tunnel'][146, 128], images['tunnel'][152, 200]), (255, 255))
    # The ground road cuts over the tunnel beneath it, and the tunnel is drawn without its casing.
    self.assertEqual((images['tunnel'][152, 133], images['tunnel'][147, 200]), (0, 0))

  def test_road_widths(self):
    # Pinned at the style zoom of 1 m per pixel: 16.26 at the equator and 15.26 at 60 degrees. Tunnels have no casing.
    styles, levels = np.array([MAJOR, MEDIUM, STREET, MINOR, TRACK, STREET]), np.array([0, 0, 0, 0, 0, -1])
    np.testing.assert_allclose(stroke_widths(16.256, styles, levels), [19.02, 15.48, 9.86, 6.70, 7.02, 7.89], atol=0.01)
    np.testing.assert_allclose(stroke_widths(15.256, styles, levels), [13.52, 10.78, 6.39, 4.16, 4.58, 4.62], atol=0.01)

  def test_route_tiles(self):
    route = np.array([[0, -0.01], [0, 0.01]])  # 2.2 km north along the prime meridian
    with local_archive(make_archive(max_zoom=15)) as archive:
      renderer = MapRenderer(archive)
      tiles = renderer.route_tiles(route)
      # Both columns beside the meridian, and the rows within the view radius of the route's ends.
      self.assertEqual({x for x, _ in tiles}, {16383, 16384})
      self.assertEqual({y for _, y in tiles}, set(range(16382, 16386)))

  def test_validity_and_display(self):
    route = np.array([[0, -0.01], [0, 0.01]])
    with local_archive(make_archive()) as archive:
      renderer = MapRenderer(archive)
      self.assertTrue(renderer.render(0, 0, 0, route)[1])
      self.assertFalse(renderer.render(0.01, 0, 0, route)[1])  # no road near the ego
      with patch.object(archive, 'get', return_value=None):  # a missing tile
        image, valid = MapRenderer(archive).render(0, 0, 0, route)
        self.assertFalse(valid)
        self.assertEqual(image[128, 128], 128)  # the route is still drawn
    with local_archive(make_archive(field(3, field(1, b'buildings')))) as archive:  # tiles without roads
      self.assertFalse(MapRenderer(archive).render(0, 0, 0, route)[1])


class TestRouteTracking(unittest.TestCase):
  def test_snap_heading_and_window(self):
    m = METER
    tracker = RouteTracker(np.array([[0, 0], [0, 200 * m], [200 * m, 200 * m]]))  # north 200m, then east 200m
    longitude, latitude, bearing = tracker.snap(3 * m, 100 * m)  # 3m right of the first leg
    self.assertAlmostEqual(tracker.progress, 100, delta=0.5)
    self.assertAlmostEqual(longitude, 0)  # lateral error removed
    self.assertAlmostEqual(latitude, 100 * m)
    self.assertAlmostEqual(bearing, 0, places=3)
    self.assertAlmostEqual(tracker.snap(0, 200 * m)[2], 45, places=2)  # at the corner the +-50m chord is mid-turn
    self.assertAlmostEqual(tracker.snap(0, 150 * m)[2], 45, places=2)  # progress never decreases
    tracker.snap(100 * m, 200 * m)  # progress 300: the window ahead no longer includes the first leg
    self.assertAlmostEqual(tracker.snap(150 * m, 200 * m)[0], 150 * m)  # so the window's offset is applied
    self.assertAlmostEqual(tracker.snap(200 * m, 200 * m)[2], 90, places=2)  # the chord clips at the route's end
    # Out and back along the same road: a fix near the far leg stays on the outbound leg within the window,
    # while a fresh tracker searches anywhere and lands on the return leg.
    route = np.array([[0, 0], [0, 1000 * m], [10 * m, 1000 * m], [10 * m, 0]])
    tracker = RouteTracker(route)
    tracker.snap(1 * m, 100 * m)
    self.assertAlmostEqual(tracker.snap(9 * m, 150 * m)[2], 0, places=3)
    self.assertAlmostEqual(tracker.progress, 150, delta=0.5)
    self.assertAlmostEqual(RouteTracker(route).snap(9 * m, 150 * m)[2], 180, places=3)


class TestCustomTiles(TileServerCase):
  def test_custom_url_without_api(self):
    url_file = Path(self.directory.name) / 'nav_tiles_url'
    url_file.write_text('https://example.invalid/x.pmtiles\n')
    with patch(f'{T}.CUSTOM_URL_FILE', url_file):
      from openpilot.starpilot.navigation.nav_model.tiles import custom_url
      self.assertEqual(custom_url(), 'https://example.invalid/x.pmtiles')
      url_file.write_text('http://plain.invalid/x.pmtiles')
      self.assertEqual(custom_url(), '')                 # https only
    # a custom URL is read directly: no comma API call
    with patch(f'{T}.custom_url', return_value=self.url), closing(PMTiles(RemoteTiles())) as archive:
      self.assertEqual(archive.get(0, 0, 0), road_tile())
    self.api.get.assert_not_called()


class TestStarPilotManeuvers(unittest.TestCase):
  def test_current_step_left_out(self):
    M = SimpleNamespace
    # StarPilot: [current step (its turn already made, distance to the end of the step), next steps at their start]
    maneuvers = [M(type='turn', modifier='right', distance=300.0), M(type='off ramp', modifier='right', distance=300.0),
                 M(type='fork', modifier='left', distance=900.0)]
    nav = starpilot_navigation_input(maneuvers, 20.0)
    self.assertEqual(int(np.argmax(nav[:-1])), valhalla_type('off ramp', 'right'))
    self.assertAlmostEqual(float(nav[-1]), 2.8)                 # (300 - 20) / 100
    self.assertEqual(nav.shape, (47,))
    # comma's helper on the raw list would have taken the turn already made
    self.assertEqual(int(np.argmax(navigation_input(maneuvers, 20.0)[:-1])), valhalla_type('turn', 'right'))
    # passed (negative distance) and depart/arrive (<= 6) are skipped; nothing left -> all zeros
    self.assertEqual(float(starpilot_navigation_input([M(type='turn', modifier='left', distance=5.0),
                                                       M(type='arrive', modifier='', distance=50.0)], 0.0).sum()), 0.0)
    self.assertIsNone(valhalla_type('merge', 'left'))


if __name__ == '__main__':
  unittest.main()
