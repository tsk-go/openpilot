"""Lazy-loads the 4th-gen Sienna catalog data/sienna_catalog.json (toyopilot's Carista-derived data, translated to English)
plus data/toyota_settings.json (Toyota's own North America Customize list for the Sienna HV modules - names and addresses
check out, values unverified; built by tools/build_toyota_extras.py). The car itself decides what shows: a scan only
lists items whose ECU reports the data ID (and the "fitted" bit where Toyota has one)."""
import json
import os
from functools import cache

CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sienna_catalog.json")
TOYOTA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "toyota_settings.json")


def use_toyota_extras(on: bool) -> None:
  """Tests: the replayed (Chinese-market) Sienna only knows toyopilot's base catalog."""
  global TOYOTA_PATH
  TOYOTA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "toyota_settings.json") if on else ""
  load_sienna.cache_clear()
  _by_key.cache_clear()


@cache
def load_sienna() -> dict:
  with open(CATALOG_PATH) as f:
    data = json.load(f)
  if TOYOTA_PATH and os.path.exists(TOYOTA_PATH):
    with open(TOYOTA_PATH) as f:
      extra = json.load(f)
    known = {e["id"] for e in data["ecus"]}
    data["ecus"] = data["ecus"] + [e for e in extra["ecus"] if e["id"] not in known]
    data["categories"] = data["categories"] + extra["categories"]
    data["settings"] = data["settings"] + extra["settings"]
  return data


@cache
def _by_key(section: str, key_field: str) -> dict[str, dict]:
  return {entry[key_field]: entry for entry in load_sienna()[section]}


def ecu(ecu_id: str) -> dict | None:
  return _by_key("ecus", "id").get(ecu_id)


def setting(key: str) -> dict | None:
  return _by_key("settings", "key").get(key)


def live_item(key: str) -> dict | None:
  return _by_key("live", "key").get(key)


def option_label(options: list[dict] | None, value) -> str | None:
  """Label of an option value; None when it isn't one of the options (or the item has no options)."""
  return next((o["label"] for o in options or [] if o["value"] == value), None)


def ecu_address(ecu: dict) -> tuple[int, int | None]:
  """(request ID, 0x750 gateway sub-address or None)."""
  return int(ecu["tx"], 16), int(ecu["sub"], 16) if ecu["sub"] else None
