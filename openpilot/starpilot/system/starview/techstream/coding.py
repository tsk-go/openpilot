"""Bit operations for customization items (pure functions; rules from toyopilot's Carista reverse engineering -
libCarista.so's ByteUtils / ToyotaUdsSupportedDids).

- UDS: the answer to 22 XX00 is the support bitmap of DIDs XX01..XXFF (exactly 32 bytes); DID low byte L's bit =
  bitmap[(L-1)>>3] >> ((-L)&7) & 1, i.e. bit 7 of the first byte is XX01. All 189 DIDs read on a real car matched.
- Toyota CAN: A8 03 -> E8 03 followed by [id, len, mask[len]] entries; reading 21 id returns only the bytes whose mask is
  non-zero (compressed). Expanded by the mask (zero where the mask is 0), Carista's byteIndex is the index.
- Get / set: the bits of payload[byteIndex] covered by mask, shifted down to bit 0 (catalog masks are all 1 byte).
"""
UDS_BITMAP_LEN = 32
POSITIVE_A8 = 0xE8


def uds_did_supported(bitmap: bytes, did: int) -> bool:
  low = did & 0xFF
  if len(bitmap) != UDS_BITMAP_LEN or low == 0:
    return False
  return bool(bitmap[(low - 1) >> 3] >> ((-low) & 7) & 1)


def _shift(mask: int) -> int:
  return (mask & -mask).bit_length() - 1


def _check_index(payload: bytes, byte_index: int) -> None:
  if byte_index >= len(payload):
    raise ValueError(f"data has only {len(payload)} bytes, no byte {byte_index}")


def extract_value(payload: bytes, byte_index: int, mask: int) -> int:
  _check_index(payload, byte_index)
  return (payload[byte_index] & mask) >> _shift(mask)


def insert_value(payload: bytes, byte_index: int, mask: int, value: int) -> bytes:
  _check_index(payload, byte_index)
  shifted = value << _shift(mask)
  if value < 0 or shifted & ~mask:
    raise ValueError(f"value {value} doesn't fit mask {mask:02X}")
  out = bytearray(payload)
  out[byte_index] = (out[byte_index] & ~mask) | shifted
  return bytes(out)


def parse_masks(response: bytes) -> dict[int, bytes]:
  masks: dict[int, bytes] = {}
  if len(response) < 2 or response[0] != POSITIVE_A8:
    return masks
  body = response[2:]
  while len(body) >= 2:
    local_id, length = body[0], body[1]
    if len(body) < 2 + length:
      break
    masks[local_id] = bytes(body[2:2 + length])
    body = body[2 + length:]
  return masks


def expand_by_mask(compressed: bytes, mask: bytes) -> bytes:
  values = iter(compressed)
  return bytes(next(values, 0) if m else 0 for m in mask)


def can_setting_supported(mask_entry: bytes, byte_index: int, mask: int) -> bool:
  return byte_index < len(mask_entry) and mask_entry[byte_index] & mask == mask
