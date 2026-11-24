"""Mapbox requests through the StarView tablet when the comma has no internet of its own.

In the car the comma is often offline (no SIM data, no Wi-Fi) while the tablet on its USB link is online. starviewd
then writes the tablet's relay address (the tablet's link address and the port of StarView's relay) to RELAY_FILE and
renews it while the tablet stays connected. Requests go straight out first; when the comma can't reach the internet
(no route, no DNS), they go through the tablet for a minute before trying straight again. The relay only passes
HTTPS to Mapbox's servers (CONNECT, end to end TLS: the tablet never sees the request or the key), so nothing else
of the comma's - uploads, updates - ever uses the tablet's data.
Since the Nov 16 sync it wraps upstream's pooled session (owner._pooled_session), whose Google requests stay direct.
"""
from __future__ import annotations

import os
import time

import requests
from urllib.parse import urlsplit

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


def _relayable(url: str) -> bool:
  """The tablet's relay passes only Mapbox (CONNECT to mapbox.com / *.mapbox.com, port 443)."""
  host = (urlsplit(url).hostname or "").lower()
  return urlsplit(url).scheme == "https" and (host == "mapbox.com" or host.endswith(".mapbox.com"))


class RelaySession:
  """A requests session (upstream's pooled one) whose Mapbox GETs go straight out or through the tablet.

  Everything else (Google's routes, tiles and places, shared links: GET and POST) goes straight out only.
  """

  def __init__(self, path: str = RELAY_FILE, clock=time.monotonic, get=None, session=None):
    self.path, self.clock = path, clock
    self.session = session
    self._get = get or (session.get if session is not None else requests.get)
    self.direct_down_until = 0.

  def get(self, url, **kwargs):
    proxy = tablet_proxy(self.path) if _relayable(url) else None
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

  def __getattr__(self, name):
    # post, head, mount ... straight to the session underneath
    return getattr(self.session if self.session is not None else requests, name)


SESSION = RelaySession()


def for_owner(given, built):
  """NavigationOwner's hook (owner.py, right after it makes its session): its own pooled session (`built`, made when no
  session was handed in) goes through RelaySession; a session handed in (tests, other callers) stays as it is."""
  return RelaySession(session=built) if given is None or given is requests else built
