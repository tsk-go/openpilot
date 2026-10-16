"""Waze bridge on StarPilot 7: destination handoff through the navigation owner, comparison fields for the tablet."""
import json
import time

import pytest

from openpilot.starpilot.system.starview import waze_bridge
from openpilot.starpilot.system.starview.waze_bridge import NavDestinations

from .test_waze_parser import node, real_split_screen


class FakeOwner:
  """starpilot/navigation/owner.py NavigationOwner, as far as the bridge uses it."""

  def __init__(self, destination=None, hits=None, fail=None):
    self.doc = {"revision": "r0", "destination": destination, "favorites": [], "recents": []}
    self.hits = hits if hits is not None else [{"id": "a1", "name": "85 Inip Drive", "address": "85 Inip Drive, Inwood, NY",
                                                "latitude": 40.1, "longitude": -74.2}]
    self.searches, self.fail = [], fail
    self.conflict_once = False

  def read(self):
    return json.loads(json.dumps(self.doc))

  def search(self, query):
    self.searches.append(query)
    if self.fail:
      raise self.fail
    return self.hits

  def _check(self, rev):
    from openpilot.starpilot.navigation.owner import ConflictError
    if self.conflict_once:
      self.conflict_once = False
      self.doc["revision"] = "bumped"
      raise ConflictError("Navigation changed; refresh and try again")
    assert rev == self.doc["revision"]

  def select(self, value, rev, authorized):
    self._check(rev)
    assert authorized is True
    from openpilot.starpilot.navigation.owner import destination
    self.doc["destination"] = destination(value)
    self.doc["revision"] = rev + "+"
    return dict(self.doc)

  def clear(self, rev, authorized):
    self._check(rev)
    self.doc["destination"] = None
    self.doc["revision"] = rev + "+"
    return dict(self.doc)


@pytest.fixture
def feed(tmp_path, monkeypatch):
  for k, v in (("STATE_PATH", "w.json"), ("OUR_DEST_PATH", "ours.json"), ("OFF_FLAG", "off"), ("LOG_DIR", "logs")):
    monkeypatch.setattr(waze_bridge, k, str(tmp_path / v))
  owner = FakeOwner()
  f = waze_bridge.WazeFeed(dest=NavDestinations(owner))
  f.owner = owner
  return f


def wait(feed):
  deadline = time.monotonic() + 5.0
  while feed._geocode_inflight:
    assert time.monotonic() < deadline, "address lookup still running"
    time.sleep(0.01)


IDLE = {"v": 1, "present": True, "h": 1250, "nodes": [node("Where to?", b=(1100, 100, 1500, 150))]}


def test_destination_from_waze_and_cleared_when_waze_ends(feed, monkeypatch, tmp_path):
  r = feed.ingest(dict(real_split_screen(), record=True))
  assert r["needDestination"] and feed.owner.doc["destination"] is None      # driving screen: no destination yet
  assert list((tmp_path / "logs").glob("waze-*.jsonl"))
  feed.ingest(real_split_screen(sheet=True))
  wait(feed)
  d = feed.owner.doc["destination"]
  assert (d["latitude"], d["longitude"], d["name"], d["address"]) == (40.1, -74.2, "Work", "85 Inip Drive, Inwood, NY")
  assert feed.owner.searches == ["85 Inip Drive, Inwood, NY"]
  r = feed.ingest(real_split_screen())                                         # sheet closed again
  assert not r["needDestination"] and r["parsed"]["destination"] == "85 Inip Drive, Inwood, NY"
  assert len(feed.owner.searches) == 1
  monkeypatch.setattr(waze_bridge, "END_CLEAR_S", 0.0)
  feed.ingest(IDLE)
  feed.ingest(IDLE)
  assert feed.owner.doc["destination"] is None


def test_someone_elses_destination_is_kept(feed, monkeypatch):
  feed.owner.select({"name": "Home", "latitude": 41.0, "longitude": -73.0}, "r0", True)
  monkeypatch.setattr(waze_bridge, "END_CLEAR_S", 0.0)
  feed.ingest(IDLE)
  feed.ingest(IDLE)
  assert feed.owner.doc["destination"]["name"] == "Home"


def test_same_place_is_not_set_again(feed):
  feed.owner.select({"name": "Work", "latitude": 40.1, "longitude": -74.2}, "r0", True)
  rev = feed.owner.doc["revision"]
  feed.ingest(real_split_screen(sheet=True))
  wait(feed)
  assert feed.owner.doc["revision"] == rev                                     # already StarPilot's destination


def test_conflict_is_retried(feed):
  feed.owner.conflict_once = True                                              # Galaxy changed navigation meanwhile
  assert feed.set_tablet_destination("Work", "85 Inip Drive, Inwood, NY", 40.8676, -73.9212)["ok"]
  assert feed.owner.doc["destination"]["latitude"] == 40.8676


def test_search_failure_retries_with_the_remembered_address(feed, monkeypatch):
  from openpilot.starpilot.navigation.owner import ValidationError
  feed.owner.fail = ValidationError("The map service could not complete this request")
  monkeypatch.setattr(waze_bridge, "NET_RETRY_S", 0.0)
  feed.ingest(real_split_screen(sheet=True))
  wait(feed)
  r = feed.ingest(real_split_screen())
  assert "can't reach Mapbox" in r["handoff"] and feed.owner.doc["destination"] is None
  wait(feed)
  feed.owner.fail = None
  feed.ingest(real_split_screen())
  wait(feed)
  assert feed.owner.doc["destination"]["latitude"] == 40.1


def test_no_key_says_so(feed):
  from openpilot.starpilot.navigation.owner import ValidationError
  feed.owner.fail = ValidationError("Add your Mapbox access token first")
  feed.ingest(real_split_screen(sheet=True))
  wait(feed)
  assert "no Mapbox key" in feed.ingest(real_split_screen())["handoff"]


def test_tablet_destination(feed, monkeypatch):
  r = feed.set_tablet_destination("Work", "85 Inip Drive, Inwood, NY", 40.8676, -73.9212)
  assert r["ok"] and r["destination"]["name"] == "Work"
  feed.ingest(real_split_screen(sheet=True))                                   # nothing is looked up
  wait(feed)
  assert feed.owner.searches == []
  monkeypatch.setattr(waze_bridge, "END_CLEAR_S", 0.0)
  feed.ingest(IDLE)
  feed.ingest(IDLE)
  assert feed.owner.doc["destination"] is not None                             # Waze still starting: grace time
  monkeypatch.setattr(waze_bridge, "TABLET_GRACE_S", 0.0)
  feed.ingest(IDLE)
  feed.ingest(IDLE)
  assert feed.owner.doc["destination"] is None and not feed._tablet_route
  assert not feed.set_tablet_destination("", "", 40.0, -74.0)["ok"]
  assert not feed.set_tablet_destination("X", "", 95.0, -74.0)["ok"]
  assert not feed.set_tablet_destination("X", "", float("nan"), -74.0)["ok"]


def test_fields_for_the_tablet(feed, tmp_path):
  sp = {"valid": True, "maneuverType": "turn", "maneuverPrimaryText": "Ocean Parkway", "maneuverDistance": 500.0,
        "maneuverModifier": "right"}
  assert feed.fields(sp) == {"wazeFresh": False}                               # no Waze reading yet
  feed.ingest(real_split_screen())
  f = feed.fields(sp)
  assert f["wazeFresh"] and f["wazeAgree"] is True and f["wazeDisagreeS"] == 0.0
  other = dict(sp, maneuverPrimaryText="Coney Island Avenue")
  assert feed.fields(other)["wazeAgree"] is False
  (tmp_path / "off").write_text("")
  assert feed.fields(sp) == {"wazeFresh": False}


def test_state_file_age_is_monotonic(feed, monkeypatch):
  feed.ingest(real_split_screen())
  assert waze_bridge.load_state() is not None
  monkeypatch.setattr(waze_bridge, "_wall", lambda: 0.0)
  assert waze_bridge.load_state() is not None
  mono = time.monotonic() + waze_bridge.FRESH_S + 1
  monkeypatch.setattr(waze_bridge.time, "monotonic", lambda: mono)
  assert waze_bridge.load_state() is None
