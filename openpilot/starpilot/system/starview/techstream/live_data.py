"""4th-gen Sienna live data (rules from toyopilot's Carista reverse engineering, their spec-v2 §1.6; items are
catalog.load_sienna()["live"]).

- All UDS 22 DID -> 62 DID payload; items sharing an (ECU, DID) are one request.
- raw = payload[byteIndex : byteIndex + mask bytes] big-endian & mask; signed = two's complement over the mask width.
- value = offset + mult x raw (full precision - the battery page computes block differences from it); text rounded to
  precision, or the option label.
- A failure (no response, bad response, negative response, answer too short) only sets that item's error.
"""
from openpilot.starpilot.system.starview.techstream import catalog
from openpilot.starpilot.system.starview.techstream.link import ECU_COMMUNICATION_ERRORS, expect_positive, read_error_text


class _ReadError(Exception):
  pass


def decode(item: dict, payload: bytes) -> float:
  mask = int(item["mask"], 16)
  width = len(item["mask"]) // 2
  chunk = payload[item["byteIndex"]:item["byteIndex"] + width]
  if len(chunk) < width:
    raise _ReadError("answer too short")
  raw = int.from_bytes(chunk, "big") & mask
  bits = mask.bit_length()
  if item["signed"] and raw >> (bits - 1):
    raw -= 1 << bits
  return item["offset"] + item["mult"] * raw


def format_value(item: dict, value: float) -> str:
  return catalog.option_label(item["options"], value) or f"{value:.{item['precision']}f}"


def _read_did(link, ecu_id: str, did: str) -> bytes:
  try:
    return expect_positive(link, catalog.ecu_address(catalog.ecu(ecu_id)), b"\x22" + bytes.fromhex(did), 3)
  except ECU_COMMUNICATION_ERRORS as exc:
    raise _ReadError(read_error_text(exc)) from None


def read(link, items: list[dict]) -> list[dict]:
  """[{key, value, text}] in the order of items; a failed item has value None, text "" and an error."""
  payloads: dict[tuple[str, str], bytes | _ReadError] = {}
  values = []
  for item in items:
    source = (item["ecu"], item["did"])
    if source not in payloads:
      try:
        payloads[source] = _read_did(link, *source)
      except _ReadError as exc:
        payloads[source] = exc
    try:
      if isinstance(payloads[source], _ReadError):
        raise payloads[source]
      value = decode(item, payloads[source])
    except _ReadError as exc:
      values.append({"key": item["key"], "value": None, "text": "", "error": str(exc)})
      continue
    values.append({"key": item["key"], "value": value, "text": format_value(item, value)})
  return values
