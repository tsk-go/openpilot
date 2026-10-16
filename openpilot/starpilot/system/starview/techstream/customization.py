"""4th-gen Sienna customization items: scan per ECU, write, restore (rules from toyopilot's Carista reverse engineering;
bit operations in coding.py).

- UDS ECUs: 22 XX00 support bitmap -> 22 DID reads the whole payload; write = read-modify-write with 2E DID, and on
  7F 2E 7F switch to 10 03 and try once more.
- Toyota CAN ECUs (window-type): A8 03 mask table -> 21 id reads compressed data, expanded by the mask; write 3B id
  <expanded data>, expect 7B id.
- Every write is backed up first and read back afterwards; each ECU's protocol is fixed in the catalog.
"""
from collections.abc import Callable

from openpilot.starpilot.system.starview.techstream import catalog, coding
from openpilot.starpilot.system.starview.techstream.link import EcuRejectedError, MalformedResponseError, NoResponseError, \
  ECU_COMMUNICATION_ERRORS, expect_positive, read_error_text

Address = tuple[int, int | None]
READ_CAN_MASK_TABLE = b"\xa8\x03"
EXTENDED_SESSION = b"\x10\x03"
NRC_SERVICE_NOT_SUPPORTED_IN_SESSION = 0x7F


class StaleDataError(Exception):
  """The ECU's data changed since the scan: refuse to write based on old data."""


class BackupError(Exception):
  """The backup before writing couldn't be saved (e.g. /data not writable): nothing is written."""


def read_uds_did(link, address: Address, did: int) -> bytes:
  return expect_positive(link, address, b"\x22" + did.to_bytes(2, "big"), 3)


def read_can_expanded(link, address: Address, local_id: int, mask_entry: bytes) -> bytes:
  return coding.expand_by_mask(expect_positive(link, address, bytes([0x21, local_id]), 2), mask_entry)


def _read_once(cache: dict, key, read: Callable[[], bytes]) -> bytes:
  """Read each key only once; a failed read is cached too and raises the same error every time after."""
  if key not in cache:
    try:
      cache[key] = read()
    except ECU_COMMUNICATION_ERRORS as exc:
      cache[key] = exc
  if isinstance(cache[key], Exception):
    raise cache[key]
  return cache[key]


class _UdsReader:
  """Scanning one UDS ECU: support bitmaps cached per DID high byte, every DID read once."""

  def __init__(self, link, address: Address):
    self.link, self.address = link, address
    self._bitmaps: dict[int, bytes | Exception] = {}
    self._payloads: dict[int, bytes | Exception] = {}

  def supported(self, setting: dict) -> bool:
    did = int(setting["did"], 16)
    high = did >> 8
    bitmap = _read_once(self._bitmaps, high, lambda: read_uds_did(self.link, self.address, high << 8))
    return coding.uds_did_supported(bitmap, did)

  def payload(self, setting: dict) -> bytes:
    did = int(setting["did"], 16)
    return _read_once(self._payloads, did, lambda: read_uds_did(self.link, self.address, did))


class _CanReader:
  """Scanning one Toyota CAN ECU: A8 03 mask table read once, every local ID read once."""

  def __init__(self, link, address: Address):
    self.link, self.address = link, address
    self.masks = coding.parse_masks(link.request(*address, READ_CAN_MASK_TABLE))
    self._data: dict[int, bytes | Exception] = {}

  def supported(self, setting: dict) -> bool:
    entry = self.masks.get(int(setting["localId"], 16), b"")
    return coding.can_setting_supported(entry, setting["byteIndex"], int(setting["mask"], 16))

  def payload(self, setting: dict) -> bytes:
    local_id = int(setting["localId"], 16)
    return _read_once(self._data, local_id, lambda: read_can_expanded(self.link, self.address, local_id, self.masks[local_id]))


def _bit_support_ok(setting: dict, payload: bytes) -> bool:
  """requiresBitSupportCheck: the same bits in the previous byte flag that the item exists."""
  mask = int(setting["mask"], 16)
  index = setting["byteIndex"] - 1
  return 0 <= index < len(payload) and payload[index] & mask == mask


def scan_ecu(link, ecu: dict, settings: list[dict]) -> dict:
  """Current values of the catalog's items on one ECU.

  Returns {ecu, status, items: [{key, value, raw}], total, supported, read, readError?, malformedReason?};
  status: offline (no answer to 3E) / malformed (answer isn't valid ISO-TP) / ok. raw is the whole UDS payload or the
  expanded CAN data. readError is the first read failure (support bitmap or data couldn't be read).
  """
  address = catalog.ecu_address(ecu)
  report = {"ecu": ecu["id"], "status": "ok", "items": [], "total": len(settings), "supported": 0, "read": 0}
  try:
    link.request(*address, b"\x3e")
    reader = _CanReader(link, address) if ecu["protocol"] == "toyota_can" else _UdsReader(link, address)
  except NoResponseError:
    return {**report, "status": "offline"}
  except MalformedResponseError as exc:
    return {**report, "status": "malformed", "malformedReason": str(exc)}
  for setting in settings:
    try:
      if not reader.supported(setting):
        continue
    except ECU_COMMUNICATION_ERRORS as exc:
      report.setdefault("readError", read_error_text(exc))
      continue
    try:
      payload = reader.payload(setting)
    except ECU_COMMUNICATION_ERRORS as exc:
      report["supported"] += 1
      report.setdefault("readError", read_error_text(exc))
      continue
    if setting["requiresBitSupportCheck"] and not _bit_support_ok(setting, payload):
      continue
    report["supported"] += 1
    try:
      value = coding.extract_value(payload, setting["byteIndex"], int(setting["mask"], 16))
    except ValueError:
      report.setdefault("readError", "answer too short")
      continue
    report["read"] += 1
    report["items"].append({"key": setting["key"], "value": value, "raw": payload.hex()})
  return report


def probe_setting(link, ecu: dict, setting: dict) -> dict:
  """Read one item directly, even when the ECU's support bitmap / mask table doesn't list it (StarView's "show unlisted
  items"). An ECU that really doesn't have it answers 7F 22 31 (request out of range) -> EcuRejectedError; nothing is
  written here. Returns {key, value, raw} like a scan item, so the normal write path (backup, write, read back) can follow."""
  payload = _read_payload(link, catalog.ecu_address(ecu), ecu, setting)
  try:
    value = coding.extract_value(payload, setting["byteIndex"], int(setting["mask"], 16))
  except ValueError as exc:
    raise MalformedResponseError(f"answer too short: {exc}") from exc
  return {"key": setting["key"], "value": value, "raw": payload.hex()}


# ---- write, restore (read-modify-write -> read back; always backed up first) ----

def _read_payload(link, address: Address, ecu: dict, setting: dict) -> bytes:
  if ecu["protocol"] == "toyota_can":
    local_id = int(setting["localId"], 16)
    mask_entry = coding.parse_masks(link.request(*address, READ_CAN_MASK_TABLE)).get(local_id)
    if not mask_entry:
      raise MalformedResponseError(f"local ID {local_id:02X} isn't in the A8 03 mask table")
    return read_can_expanded(link, address, local_id, mask_entry)
  return read_uds_did(link, address, int(setting["did"], 16))


def _write_payload(link, address: Address, ecu: dict, setting: dict, payload: bytes) -> None:
  if ecu["protocol"] == "toyota_can":
    expect_positive(link, address, bytes([0x3B, int(setting["localId"], 16)]) + payload, 2)
    return
  request = b"\x2e" + int(setting["did"], 16).to_bytes(2, "big") + payload
  response = link.request(*address, request)
  if response == bytes([0x7F, 0x2E, NRC_SERVICE_NOT_SUPPORTED_IN_SESSION]):
    # the default session doesn't allow writes: like Carista, switch to the extended session and try once more
    # (reading works in the default session)
    expect_positive(link, address, EXTENDED_SESSION, 2)
    response = link.request(*address, request)
  if response[:3] != b"\x6e" + request[1:3]:
    raise EcuRejectedError(request, response)


def _save_backup(backups, ecu: dict, setting: dict, data: bytes, after: bytes) -> str:
  try:
    return backups.save({"key": setting["key"], "ecu": ecu["id"], "data": data.hex(), "after": after.hex()})
  except OSError as exc:
    raise BackupError(f"Backup before writing failed, nothing written: {exc}") from exc


def _write_value(link, ecu: dict, setting: dict, value: int, before: bytes, backups) -> dict:
  """Change only this item's bits in before -> back up -> write -> read back. The returned after is what was read back
  (differs from what was meant to be written when the check fails)."""
  address = catalog.ecu_address(ecu)
  mask = int(setting["mask"], 16)
  after = coding.insert_value(before, setting["byteIndex"], mask, value)
  backup_id = _save_backup(backups, ecu, setting, before, after)
  _write_payload(link, address, ecu, setting, after)
  current = _read_payload(link, address, ecu, setting)
  return {"key": setting["key"], "value": coding.extract_value(current, setting["byteIndex"], mask),
          "verified": current == after, "backupId": backup_id, "before": before.hex(), "after": current.hex()}


def write_setting(link, ecu: dict, setting: dict, value: int, expected_before: str, backups) -> dict:
  """expected_before: the raw data from the scan; if the ECU's data changed since, nothing is written (StaleDataError)."""
  before = _read_payload(link, catalog.ecu_address(ecu), ecu, setting)
  if before.hex() != expected_before.lower():
    raise StaleDataError(f"the ECU's data {before.hex()} isn't what the scan read ({expected_before})")
  return _write_value(link, ecu, setting, value, before, backups)


def restore_setting(link, ecu: dict, setting: dict, backup: dict, backups) -> dict:
  """Undo = write this item's value back to the backed-up value (only this item's bits, so other items changed later in
  the same DID stay); the backup is marked restored only when the read-back matches."""
  old_value = coding.extract_value(bytes.fromhex(backup["data"]), setting["byteIndex"], int(setting["mask"], 16))
  current = _read_payload(link, catalog.ecu_address(ecu), ecu, setting)
  result = _write_value(link, ecu, setting, old_value, current, backups)
  if result["verified"]:
    backups.mark_restored(backup["id"])
  return result
