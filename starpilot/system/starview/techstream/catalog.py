"""Lazy-loads the 4th-gen Sienna catalog data/sienna_catalog.json (toyopilot's Carista-derived data, translated to English)."""
import json
import os
from functools import cache

CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sienna_catalog.json")


@cache
def load_sienna() -> dict:
  with open(CATALOG_PATH) as f:
    return json.load(f)


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
