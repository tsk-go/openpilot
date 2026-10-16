import pytest

from openpilot.starpilot.system.starview.techstream import coding

# The real car's 750/40 body ECU answer to 22 2200 (without 62 22 00): the support bitmap of DIDs 22xx
BODY_BITMAP_22XX = bytes.fromhex("8001007180b9e001a07b00400001880600002000000008700000000000000000")


class TestUdsDidSupported:
  @pytest.mark.parametrize("did, supported", [
    (0x2201, True),    # bit 7 of the first byte
    (0x2202, False),   # on the real car 22 2202 answers 7F 22 31
    (0x2270, True),    # headlights-on reminder when a door opens; the real car read 62 2270 01
  ])
  def test_matches_what_the_car_answered(self, did, supported):
    assert coding.uds_did_supported(BODY_BITMAP_22XX, did) is supported

  def test_bitmap_must_be_32_bytes(self):
    assert coding.uds_did_supported(BODY_BITMAP_22XX[:31], 0x2201) is False


class TestValueBits:
  def test_extract_shifts_masked_bits_down(self):
    assert coding.extract_value(bytes.fromhex("00b4"), 1, 0x30) == 3

  def test_insert_replaces_only_masked_bits(self):
    assert coding.insert_value(bytes.fromhex("00b4"), 1, 0x30, 1) == bytes.fromhex("0094")

  def test_insert_rejects_value_wider_than_mask(self):
    with pytest.raises(ValueError, match="doesn't fit mask 30"):
      coding.insert_value(bytes.fromhex("00b4"), 1, 0x30, 4)

  def test_short_payload_raises(self):
    with pytest.raises(ValueError, match="no byte 1"):
      coding.extract_value(b"\x01", 1, 0xFF)


class TestToyotaCanMasks:
  def test_parse_and_expand(self):
    # A8 03 answer: E8 03 + [id, len, mask...]; 21 reads compressed data holding only the bytes whose mask is non-zero
    masks = coding.parse_masks(bytes.fromhex("e803 11 03 ff0030 12 01 02"))
    assert masks == {0x11: bytes.fromhex("ff0030"), 0x12: b"\x02"}
    assert coding.expand_by_mask(bytes.fromhex("a020"), masks[0x11]) == bytes.fromhex("a00020")

  @pytest.mark.parametrize("byte_index, mask, supported", [(2, 0x20, True), (2, 0x40, False), (1, 0x01, False), (3, 0x01, False)])
  def test_setting_supported_when_mask_covers_its_bits(self, byte_index, mask, supported):
    assert coding.can_setting_supported(bytes.fromhex("ff0030"), byte_index, mask) is supported
