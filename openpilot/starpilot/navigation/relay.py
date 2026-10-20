"""Mapbox requests through the StarView tablet when the comma has no internet of its own.

In the car the comma is often offline (no SIM data, no Wi-Fi) while the tablet on its USB link is online. starviewd
then writes the tablet's relay address (the tablet's link address and the port of StarView's relay) to RELAY_FILE and
renews it while the tablet stays connected. Requests go straight out first; when the comma can't reach the internet
(no route, no DNS), they go through the tablet for a minute before trying straight again. The relay only passes
HTTPS to Mapbox's servers (CONNECT, end to end TLS: the tablet never sees the request or the key), so nothing else
of the comma's - uploads, updates - ever uses the tablet's data.
"""
from __future__ import annotations

import os
import time

import requests

RELAY_FILE = "/dev/shm/starview_tablet_relay"
FRESH_S = 90.
RETRY_DIRECT_S = 60.


def tablet_proxy(path: str = RELAY_FILE) -> str | None:
  """http://host:port of the tablet's relay, while starviewd keeps it fresh."""
  try:
    if time.time() - os.stat(path).st_mtime > FRESH_S:  # noqa: TID251 - file times are wall clock
      return None
    with open(path) as f:
      host, port = f.read(64).strip().rsplit(":", 1)
    if not host or not 0 < int(port) < 65536 or any(c not in "0123456789." for c in host):
      return None
    return f"http://{host}:{int(port)}"
  except (OSError, ValueError):
    return None


class RelaySession:
  """requests.get, straight out or through the tablet."""

  def __init__(self, path: str = RELAY_FILE, clock=time.monotonic, get=None):
    self.path, self.clock = path, clock
    self._get = get or requests.get
    self.direct_down_until = 0.

  def get(self, url, **kwargs):
    proxy = tablet_proxy(self.path)
    via = {"https": proxy} if proxy else None
    if via and self.clock() < self.direct_down_until:
      return self._get(url, proxies=via, **kwargs)
    try:
      return self._get(url, **kwargs)
    except requests.ConnectionError:
      if via is None:
        raise
      self.direct_down_until = self.clock() + RETRY_DIRECT_S
      return self._get(url, proxies=via, **kwargs)


SESSION = RelaySession()
