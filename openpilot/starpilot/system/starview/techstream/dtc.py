"""4th-gen Sienna trouble codes, read and clear (rules from toyopilot's Carista reverse engineering, their spec-v2 §1.5).

- UDS ECUs: 19 02 8D -> 59 02 <availability mask>, then 4 bytes each = 3-byte code + 1 status byte; all-zero codes are
  skipped. Clear: 14 FF FF FF -> 54.
- Toyota CAN ECUs (window-type, answer 19 with 7F 19 11): 13 <pid>, trying pids 81, 80, B0, first positive answer
  wins; 53 then a count byte N + N x 2-byte codes, no status. Clear: 14 -> 54.
- Code text: the top 2 bits of the first byte -> P/C/B/U, the rest as hex; UDS codes get -FTB (e.g. U0131-87).
- No response / bad response / negative response are recorded per ECU and returned, never raised.
"""
from openpilot.starpilot.system.starview.techstream import catalog
from openpilot.starpilot.system.starview.techstream.link import EcuRejectedError, MalformedResponseError, NoResponseError, \
  ECU_COMMUNICATION_ERRORS, expect_positive, read_error_text

UDS_READ = bytes.fromhex("19028D")
CAN_READ_PIDS = (0x81, 0x80, 0xB0)
CLEAR = {"uds": bytes.fromhex("14FFFFFF"), "toyota_can": b"\x14"}
NO_CODE = b"\x00\x00\x00"


def decode_code(raw: bytes) -> str:
  code = "PCBU"[raw[0] >> 6] + str((raw[0] >> 4) & 0x3) + raw[:2].hex().upper()[1:]
  return f"{code}-{raw[2]:02X}" if len(raw) == 3 else code


def describe(code: str, dtc_text: dict) -> str:
  """"Base code text (FTB text)"; "" when the base code isn't in the list (the page shows "No description")."""
  text = dtc_text["codes"].get(code[:5])
  if text is None:
    return ""
  ftb = dtc_text["ftb"].get(code[6:]) if len(code) > 5 else None
  return text + (f" ({ftb})" if ftb else "")


def _parse_uds(payload: bytes) -> list[tuple[str, int | None]]:
  records = payload[1:]   # skip the status availability mask
  return [(decode_code(records[i:i + 3]), records[i + 3]) for i in range(0, len(records) - 3, 4)
          if records[i:i + 3] != NO_CODE]


def _parse_can(payload: bytes) -> list[tuple[str, int | None]]:
  count, records = payload[0], payload[1:]
  return [(decode_code(records[i * 2:i * 2 + 2]), None) for i in range(min(count, len(records) // 2))]


def _read_codes(link, ecu: dict) -> tuple[list[tuple[str, int | None]] | None, str]:
  """Returns (codes, error); codes is None when the ECU refused every read request.
  Raises NoResponseError only when no request got any answer (one pid not answering doesn't stop the next)."""
  address = catalog.ecu_address(ecu)
  if ecu["protocol"] == "uds":
    attempts = [(UDS_READ, 2, _parse_uds)]
  else:
    attempts = [(bytes([0x13, pid]), 1, _parse_can) for pid in CAN_READ_PIDS]
  rejection = None
  for request, echo_len, parse in attempts:
    try:
      payload = expect_positive(link, address, request, echo_len)
    except NoResponseError:
      continue
    except EcuRejectedError as exc:
      rejection = rejection or exc
      continue
    if payload:
      return parse(payload), ""
    rejection = rejection or EcuRejectedError(request, b"")
  if rejection is None:
    raise NoResponseError(f"{ecu['id']}: no answer to the trouble-code read")
  return None, read_error_text(rejection)


def scan_ecu(link, ecu: dict, dtc_text: dict) -> dict:
  """One ECU's trouble codes: {ecu, status: offline / malformed / ok, protocol, dtcs, readError?, malformedReason?}."""
  report = {"ecu": ecu["id"], "status": "ok", "protocol": ecu["protocol"], "dtcs": []}
  try:
    codes, error = _read_codes(link, ecu)
  except NoResponseError:
    return {**report, "status": "offline"}
  except MalformedResponseError as exc:
    return {**report, "status": "malformed", "malformedReason": str(exc)}
  if codes is None:
    return {**report, "readError": error}
  for code, status in codes:
    report["dtcs"].append({"code": code, "status": status, "text": describe(code, dtc_text)})
  return report


def clear(link, ecu: dict) -> dict:
  try:
    expect_positive(link, catalog.ecu_address(ecu), CLEAR[ecu["protocol"]], 1)
  except ECU_COMMUNICATION_ERRORS as exc:
    return {"ecu": ecu["id"], "ok": False, "error": read_error_text(exc)}
  return {"ecu": ecu["id"], "ok": True}
