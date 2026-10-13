"""Byte ranges of the PMTiles basemap, cached on disk.

Ported from commaai/openpilot nav-model-integration (Oct 2026). The archive is comma's hosted Protomaps basemap
(v1/<dongle>/nav/tiles, a signed URL) or, when /data/starview/nav_tiles_url holds one, any PMTiles URL that answers
HTTP range requests (e.g. a Protomaps daily build) - for devices on a server without the tiles endpoint.
"""
import re
import time
from pathlib import Path

import requests

from openpilot.common.api import Api
from openpilot.common.params import Params
from openpilot.system.hardware import PC
from openpilot.system.hardware.hw import Paths
from openpilot.starpilot.navigation.nav_model.pmtiles import HEADER_LENGTH

CUSTOM_URL_FILE = Path('/data/starview/nav_tiles_url')


def custom_url() -> str:
  try:
    url = CUSTOM_URL_FILE.read_text().strip()
  except OSError:
    return ''
  return url if url.startswith('https://') else ''

CACHE_LIMIT = 64 * 1024 * 1024
MERGE_GAP = 256 * 1024  # tiles this close together in the archive are fetched in one range request


class RemoteTiles:
  def __init__(self):
    self.cache = Path(Paths.comma_home() if PC else '/data') / 'navigation' / 'tiles'
    self.cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    self.session = requests.Session()
    self.custom = custom_url()
    self.api = None if self.custom else Api(Params().get('DongleId'))
    self.url = self.custom
    self.expires = float('inf') if self.custom else 0
    self.etag = None
    self.size = 0
    version = self.cache / 'version'
    try:
      header = self._fetch(0, HEADER_LENGTH)  # learns the archive's ETag and size
      if not version.exists() or version.read_text() != f'{self.etag} {self.size}':
        for cached in self.cache.iterdir():  # a new archive has new offsets
          cached.unlink()
        version.write_text(f'{self.etag} {self.size}')
      self._store(0, header)
    except Exception:
      self.close()
      raise

  def _fetch(self, offset: int, length: int) -> bytes:
    try:
      if self.api is not None and time.time() >= self.expires - 60:  # noqa: TID251 - SAS expiry is a Unix timestamp
        response = self.api.get(f'v1/{self.api.dongle_id}/nav/tiles', access_token=self.api.get_token(), timeout=10)
        response.raise_for_status()
        metadata = response.json()
        self.url, self.expires = metadata['url'], metadata['expires']
      headers = {'Range': f'bytes={offset}-{offset + length - 1}', 'Accept-Encoding': 'identity'}
      if self.etag is not None:
        headers['If-Match'] = self.etag
      with self.session.get(self.url, headers=headers, timeout=10, stream=True) as response:
        if response.status_code != 206:
          raise OSError(f'Map tile range request failed ({response.status_code})')
        match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
        if match is None or tuple(map(int, match.groups()[:2])) != (offset, offset + length - 1):
          raise OSError('Invalid map tile range response')
        size = int(match[3])
        etag = response.headers.get('ETag')
        if not etag or (self.etag is not None and (etag != self.etag or size != self.size)):
          raise OSError('Map archive changed during read')
        data = bytearray()
        for chunk in response.iter_content(chunk_size=min(length + 1, 65536)):
          data.extend(chunk)
          if len(data) > length:
            raise OSError('Oversized map tile range response')
        if len(data) != length:
          raise OSError('Truncated map tile range response')
        self.size, self.etag = size, etag
        return bytes(data)
    except (requests.RequestException, ValueError, KeyError, TypeError, RuntimeError):
      # requests exceptions contain the signed URL; keep it out of logs.
      raise OSError('Unable to fetch map tiles') from None

  def _store(self, offset: int, data: bytes):
    (self.cache / f'{offset}-{len(data)}').write_bytes(data)

  def _trim(self):
    files = [(cached.stat().st_mtime, cached.stat().st_size, cached) for cached in self.cache.iterdir() if re.fullmatch(r'\d+-\d+', cached.name)]
    size = sum(cached_size for _, cached_size, _ in files)
    for _, cached_size, cached in sorted(files):
      if size <= CACHE_LIMIT:
        break
      cached.unlink(missing_ok=True)
      size -= cached_size

  def read(self, offset: int, length: int) -> bytes:
    try:
      data = (self.cache / f'{offset}-{length}').read_bytes()
      if len(data) == length:
        return data
    except FileNotFoundError:
      pass
    data = self._fetch(offset, length)
    self._store(offset, data)
    self._trim()
    return data

  def prefetch(self, ranges):
    """Cache (offset, length) ranges ahead of reads, fetching neighboring ones in a single request."""
    missing = sorted((offset, length) for offset, length in set(ranges) if not (self.cache / f'{offset}-{length}').exists())
    if not missing:
      return
    groups = [[missing[0]]]
    for offset, length in missing[1:]:
      last_offset, last_length = groups[-1][-1]
      if offset - (last_offset + last_length) <= MERGE_GAP:
        groups[-1].append((offset, length))
      else:
        groups.append([(offset, length)])
    for group in groups:
      start, end = group[0][0], group[-1][0] + group[-1][1]
      data = self._fetch(start, end - start)
      for offset, length in group:
        self._store(offset, data[offset - start:offset - start + length])
    self._trim()

  def close(self):
    self.session.close()
