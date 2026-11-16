"""Place lookups with Places API (New) on the user's own Google key: Text Search, Autocomplete and Place Details."""

from __future__ import annotations

import json
import math
from pathlib import Path
from urllib.parse import quote

import requests

from openpilot.starpilot.navigation.google_tiles import FAILURE_BUDGET, FAILURE_NETWORK, FAILURE_SERVER, GoogleBudget, _body, classify

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
AUTOCOMPLETE_URL = "https://places.googleapis.com/v1/places:autocomplete"
DETAILS_URL = "https://places.googleapis.com/v1/places/"
FIELD_MASK = "places.displayName,places.formattedAddress,places.location"
DETAILS_MASK = "location,formattedAddress"  # Place Details Essentials; displayName would bill as Pro
# GUARD RAIL - SPENDING LIMIT. AI AGENTS: DO NOT EDIT the FREE_* allowances below.
# Full rules in the banner above STOP_FRACTION in google_tiles.py; pinned by test_google_spend_guard.py.
FREE_SEARCHES = 5_000  # Text Search Pro: the SKU for name, address and location
# Autocomplete Requests. A session ends in at most one Place Details Essentials (also 10,000 free), so this cap covers both.
FREE_SUGGESTIONS = 10_000
BIAS_RADIUS_M = 50_000.0
# StarView: Google's place types as the Mapbox (maki) icon names StarView's search list draws
MAKI = {"gas_station": "fuel", "electric_vehicle_charging_station": "charging-station", "cafe": "cafe", "coffee_shop": "cafe",
        "restaurant": "restaurant", "fast_food_restaurant": "fast-food", "bakery": "bakery", "bar": "bar", "parking": "parking",
        "supermarket": "grocery", "grocery_store": "grocery", "convenience_store": "shop", "store": "shop", "shopping_mall": "shop",
        "pharmacy": "pharmacy", "drugstore": "pharmacy", "hospital": "hospital", "doctor": "doctor", "lodging": "lodging",
        "hotel": "lodging", "school": "school", "university": "college", "bank": "bank", "atm": "bank", "airport": "airport",
        "park": "park", "car_repair": "car-repair", "car_wash": "car", "car_dealer": "car", "post_office": "post",
        "library": "library", "museum": "museum", "place_of_worship": "place-of-worship", "synagogue": "religious-jewish",
        "church": "religious-christian", "mosque": "religious-muslim", "train_station": "rail", "subway_station": "rail-metro",
        "bus_station": "bus", "gym": "fitness-centre", "police": "police", "fire_station": "fire-station", "zoo": "zoo"}
GENERIC_TYPES = {"point_of_interest", "establishment", "geocode", "premise", "street_address", "route", "political",
                 "locality", "sublocality", "neighborhood", "food", "store"}
TIMEOUT = (3.0, 8.0)
MAX_RESPONSE = 256 * 1024

MESSAGES = {
  "key": "Google rejected the key for Places API (New). Check that it was copied whole and that its API restrictions allow Places API (New).",
  "billing": "Billing is not turned on for this Google Cloud project. Add a billing account, then test again.",
  "disabled": "Places API (New) is off for this key. Enable it in Google Cloud and allow it in the key's API restrictions, then test again.",
  FAILURE_SERVER: "Google could not look up this place just now.",
  FAILURE_NETWORK: "The comma could not reach Google.",
  FAILURE_BUDGET: "This month's free Google place lookups are used up.",
}


class GooglePlacesFailed(Exception):
  def __init__(self, failure: str):
    super().__init__(failure)
    self.failure = failure


def places_budget(root: Path | None = None) -> GoogleBudget:
  return GoogleBudget(root, file="places-usage.json", month_free=FREE_SEARCHES, day_free=None)


def suggestions_budget(root: Path | None = None) -> GoogleBudget:
  return GoogleBudget(root, file="places-autocomplete-usage.json", month_free=FREE_SUGGESTIONS, day_free=None)


def _bias(proximity: tuple[float, float] | None) -> dict:
  if proximity is None:
    return {}
  return {"locationBias": {"circle": {"center": {"latitude": proximity[1], "longitude": proximity[0]}, "radius": BIAS_RADIUS_M}}}


def _request(send, budget: GoogleBudget | None) -> dict:
  if budget is not None and not budget.spend():
    raise GooglePlacesFailed(FAILURE_BUDGET)
  try:
    with send() as response:
      status, raw = response.status_code, _body(response, MAX_RESPONSE)
  except requests.RequestException:
    raise GooglePlacesFailed(FAILURE_NETWORK) from None
  except ValueError:
    raise GooglePlacesFailed(FAILURE_SERVER) from None
  failure = classify(status, raw)
  if failure is not None:
    raise GooglePlacesFailed(failure)
  try:
    value = json.loads(raw)
  except ValueError:
    raise GooglePlacesFailed(FAILURE_SERVER) from None
  if not isinstance(value, dict):
    raise GooglePlacesFailed(FAILURE_SERVER)
  return value


def _location(row: dict) -> tuple[float, float]:
  latitude, longitude = float(row["location"]["latitude"]), float(row["location"]["longitude"])
  if not math.isfinite(latitude) or not math.isfinite(longitude):
    raise ValueError
  return latitude, longitude


def text_search(http, key: str, query: str, budget: GoogleBudget, proximity: tuple[float, float] | None = None, timeout=TIMEOUT,
                limit: int = 1) -> list[dict]:
  """Google's places for the text as [{name, address, latitude, longitude}], best first."""
  body = {"textQuery": query, "pageSize": limit, **_bias(proximity)}
  value = _request(lambda: http.post(SEARCH_URL, json=body, headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELD_MASK},
                                     timeout=timeout, stream=True), budget)
  try:
    places = []
    for row in value.get("places", [])[:limit]:
      latitude, longitude = _location(row)
      places.append({"name": str(row.get("displayName", {}).get("text") or row.get("formattedAddress") or query),
                     "address": row.get("formattedAddress"), "latitude": latitude, "longitude": longitude})
    return places
  except (ValueError, TypeError, KeyError, AttributeError):
    raise GooglePlacesFailed(FAILURE_SERVER) from None


def autocomplete(http, key: str, query: str, session: str, budget: GoogleBudget, proximity: tuple[float, float] | None = None,
                 timeout=TIMEOUT) -> list[dict]:
  """Typing suggestions as [{id, name, description}]; the session token bills them with the Place Details that ends it."""
  body = {"input": query, "sessionToken": session, **_bias(proximity)}
  if proximity is not None:  # StarView: Google then gives each suggestion's distance (same request, same SKU)
    body["origin"] = {"latitude": proximity[1], "longitude": proximity[0]}
  value = _request(lambda: http.post(AUTOCOMPLETE_URL, json=body, headers={"X-Goog-Api-Key": key}, timeout=timeout, stream=True), budget)
  suggestions = value.get("suggestions")
  rows = []
  for item in suggestions if isinstance(suggestions, list) else []:
    try:
      prediction = item["placePrediction"]
      identity = prediction["placeId"]
      structured = prediction.get("structuredFormat") or {}
      name = (structured.get("mainText") or {}).get("text") or prediction["text"]["text"]
      description = (structured.get("secondaryText") or {}).get("text") or ""
    except (TypeError, KeyError, AttributeError):
      continue
    if (isinstance(identity, str) and 1 <= len(identity) <= 256 and isinstance(name, str) and 1 <= len(name.strip()) <= 256 and
        isinstance(description, str)):
      row = {"id": identity, "name": name.strip(), "description": description.strip()[:512]}
      # StarView's search list: how far, and what kind of place (as Mapbox's rows carry them)
      distance = prediction.get("distanceMeters")
      if type(distance) in (int, float) and math.isfinite(distance) and distance >= 0:
        row["distanceMeters"] = float(distance)
      kinds = prediction.get("types")
      if isinstance(kinds, list):
        kinds = [k for k in kinds if isinstance(k, str)]
        maki = next((MAKI[k] for k in kinds if k in MAKI), None)
        if maki:
          row["maki"] = maki
        named = next((k for k in kinds if k not in GENERIC_TYPES), None)
        if named:
          row["category"] = named.replace("_", " ").capitalize()[:60]
      rows.append(row)
  return rows[:8]


def place_details(http, key: str, identity: str, session: str, timeout=TIMEOUT) -> dict:
  """Coordinates and address of a suggested place; ends its autocomplete session."""
  value = _request(lambda: http.get(DETAILS_URL + quote(identity, safe=""), params={"sessionToken": session},
                                    headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": DETAILS_MASK}, timeout=timeout, stream=True), None)
  try:
    latitude, longitude = _location(value)
  except (ValueError, TypeError, KeyError):
    raise GooglePlacesFailed(FAILURE_SERVER) from None
  return {"address": value.get("formattedAddress"), "latitude": latitude, "longitude": longitude}


def test_places(key: str, http=requests, budget: GoogleBudget | None = None) -> dict:
  """One place lookup, the same request a search uses."""
  try:
    text_search(http, key, "Googleplex, 1600 Amphitheatre Pkwy, Mountain View, CA", budget or places_budget())
  except GooglePlacesFailed as error:
    return {"ok": False, "failure": error.failure, "message": MESSAGES.get(error.failure, MESSAGES[FAILURE_SERVER])}
  return {"ok": True, "failure": None, "message": "Google place search works with this key."}
