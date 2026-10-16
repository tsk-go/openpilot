import os

import pytest

from openpilot.starpilot.system.starview.techstream import catalog
from openpilot.starpilot.system.starview.techstream import customization as cz
from openpilot.starpilot.system.starview.techstream.backups import BackupStore
from openpilot.starpilot.system.starview.techstream.link import DiagLink, EcuRejectedError

from .fakes import PROBE, FakeEcu, FakePanda, FakeToyotaCanEcu, FakeUdsEcu

# ---- 4th-gen Sienna: scan per ECU (catalog + Carista rules) ----

# settings per UDS ECU in the catalog = how many the real car reports as supported (after dropping the kick sensor)
UDS_SETTING_COUNTS = {"750/40": 44, "750/67": 17, "750/B5": 14, "750/B8": 11, "7C4": 9, "750/A7": 7, "750/A4": 7,
                      "7C0": 3, "750/41": 2, "750/C7": 2}
WINDOW_SETTING = {"key": "car_setting_one_touch_test", "ecu": "750/90", "did": None, "localId": "11", "byteIndex": 2,
                  "mask": "20", "requiresBitSupportCheck": False}


def _link(panda: FakePanda) -> DiagLink:
  return DiagLink(panda, elm327_mode=3, heartbeat_thread=False, timeout=0.02, pending_timeout=0.1)


def _replay_link(ecu_id: str):
  ecu = catalog.ecu(ecu_id)
  fake = FakeUdsEcu.from_probe(PROBE, ecu["tx"], ecu["sub"])
  return _link(FakePanda({catalog.ecu_address(ecu): fake}))


def _settings_of(ecu_id: str) -> list[dict]:
  return [s for s in catalog.load_sienna()["settings"] if s["ecu"] == ecu_id]


class TestScanEcu:
  @pytest.mark.parametrize("ecu_id", sorted(UDS_SETTING_COUNTS))
  def test_replayed_car_reports_every_catalog_setting(self, ecu_id):
    result = cz.scan_ecu(_replay_link(ecu_id), catalog.ecu(ecu_id), _settings_of(ecu_id))
    assert result["status"] == "ok"
    assert len(result["items"]) == result["supported"] == result["read"] == UDS_SETTING_COUNTS[ecu_id]

  @pytest.mark.parametrize("ecu_id, key, value, raw", [
    ("750/40", "car_setting_warn_headlights_on_door_open", 1, "01"),   # real car: 62 2270 01
    ("750/B5", "car_setting_warn_on_key_in_car", 1, None),             # has to pass the previous byte's support-bit check
    ("750/41", "car_setting_rcta", 0, None),
  ])
  def test_values_match_the_probe(self, ecu_id, key, value, raw):
    items = {i["key"]: i for i in cz.scan_ecu(_replay_link(ecu_id), catalog.ecu(ecu_id), _settings_of(ecu_id))["items"]}
    assert items[key]["value"] == value
    if raw is not None:
      assert items[key]["raw"] == raw

  def test_bit_support_check_hides_setting_whose_support_bit_is_clear(self):
    setting = {**catalog.setting("car_setting_warn_on_key_in_car")}
    bitmap = bytearray(32)
    bitmap[(0x0C - 1) >> 3] = 1 << ((-0x0C) & 7)                      # DID 200C is in the bitmap
    fake = FakeUdsEcu({0x2000: bytes(bitmap), 0x200C: bytes.fromhex("0020")}, {b"\x3e": b"\x7e"})   # previous byte 0x00: support bit clear
    result = cz.scan_ecu(_link(FakePanda({(0x750, 0xB5): fake})), catalog.ecu("750/B5"), [setting])
    assert result["items"] == [] and result["supported"] == 0

  def test_toyota_can_setting_is_read_from_expanded_data(self):
    window = FakeToyotaCanEcu({0x11: bytes.fromhex("a020")}, {0x11: bytes.fromhex("ff0030")})
    result = cz.scan_ecu(_link(FakePanda({(0x750, 0x90): window})), catalog.ecu("750/90"), [WINDOW_SETTING])
    # compressed a0 20 expanded by mask ff 00 30 is a0 00 20; byte 2 & 0x20 -> 1
    assert result["items"] == [{"key": "car_setting_one_touch_test", "value": 1, "raw": "a00020"}]

  def test_malformed_ecu_is_reported_not_raised(self):
    # real car: the 750/AD moonroof's out-of-order A8 03 answer once turned the whole scan into an HTTP 500
    sunroof = FakeEcu({b"\x3e": b"\x7e", b"\xa8\x03": b"\xe8\x03" + bytes(range(20))}, misnumbered_frames=True)
    result = cz.scan_ecu(_link(FakePanda({(0x750, 0xAD): sunroof})), catalog.ecu("750/AD"), [])
    assert result["status"] == "malformed" and "invalid consecutive frame index" in result["malformedReason"]

  def test_offline_ecu(self):
    result = cz.scan_ecu(_link(FakePanda({})), catalog.ecu("750/40"), _settings_of("750/40"))
    assert (result["status"], result["items"], result["total"]) == ("offline", [], 44)

  def test_unreadable_did_is_reported_not_raised(self):
    fake = FakeUdsEcu.from_probe(PROBE, "750", "40")
    del fake.memory[0x2270]                                             # the bitmap says supported, but the read is refused
    result = cz.scan_ecu(_link(FakePanda({(0x750, 0x40): fake})), catalog.ecu("750/40"), _settings_of("750/40"))
    assert result["read"] == 43 and result["readError"] == "NRC 31"

  def test_unreadable_support_bitmap_is_reported(self):
    fake = FakeUdsEcu({0x2270: b"\x01"}, {b"\x3e": b"\x7e"})            # 22 2200 refused: no way to know what's supported
    result = cz.scan_ecu(_link(FakePanda({(0x750, 0x40): fake})), catalog.ecu("750/40"), _settings_of("750/40"))
    assert (result["status"], result["items"], result["readError"]) == ("ok", [], "NRC 31")


HEADLIGHTS = "car_setting_warn_headlights_on_door_open"   # 750/40 DID 2270 byte 0 mask FF, real car value 01


def _body_ecu_link(**fake_kwargs):
  fake = FakeUdsEcu.from_probe(PROBE, "750", "40", **fake_kwargs)
  return fake, _link(FakePanda({(0x750, 0x40): fake}))


class TestWriteSetting:
  def test_uds_write_backs_up_writes_and_verifies(self, tmp_path):
    fake, link = _body_ecu_link()
    backups = BackupStore(str(tmp_path))
    result = cz.write_setting(link, catalog.ecu("750/40"), catalog.setting(HEADLIGHTS), 0, "01", backups)
    assert {k: result[k] for k in ("key", "value", "verified", "before", "after")} == \
      {"key": HEADLIGHTS, "value": 0, "verified": True, "before": "01", "after": "00"}
    assert fake.memory[0x2270] == b"\x00"
    saved = backups.get(result["backupId"])
    assert (saved["key"], saved["ecu"], saved["data"], saved["after"]) == (HEADLIGHTS, "750/40", "01", "00")

  def test_refuses_when_ecu_changed_since_scan(self, tmp_path):
    fake, link = _body_ecu_link()
    with pytest.raises(cz.StaleDataError, match="isn't what the scan read"):
      cz.write_setting(link, catalog.ecu("750/40"), catalog.setting(HEADLIGHTS), 0, "00", BackupStore(str(tmp_path)))
    assert fake.memory[0x2270] == b"\x01" and not os.listdir(tmp_path)

  def test_switches_to_extended_session_when_default_session_refuses(self, tmp_path):
    fake, link = _body_ecu_link(writes_need_extended_session=True)
    result = cz.write_setting(link, catalog.ecu("750/40"), catalog.setting(HEADLIGHTS), 0, "01", BackupStore(str(tmp_path)))
    assert result["verified"] and fake.extended_session
    assert fake.requests.count(b"\x10\x03") == 1

  def test_rejected_write_raises_with_nrc(self, tmp_path):
    _, link = _body_ecu_link(reject_writes=b"\x7f\x2e\x22")
    with pytest.raises(EcuRejectedError) as exc:
      cz.write_setting(link, catalog.ecu("750/40"), catalog.setting(HEADLIGHTS), 0, "01", BackupStore(str(tmp_path)))
    assert exc.value.nrc == 0x22

  def test_failed_backup_blocks_write(self, tmp_path):
    fake, link = _body_ecu_link()
    blocker = tmp_path / "file"
    blocker.write_text("")
    with pytest.raises(cz.BackupError, match="nothing written"):
      cz.write_setting(link, catalog.ecu("750/40"), catalog.setting(HEADLIGHTS), 0, "01", BackupStore(str(blocker / "sub")))
    assert fake.memory[0x2270] == b"\x01"

  def test_unverified_write_reports_data_read_back_from_ecu(self, tmp_path):
    fake, link = _body_ecu_link(ignore_writes=True)
    result = cz.write_setting(link, catalog.ecu("750/40"), catalog.setting(HEADLIGHTS), 0, "01", BackupStore(str(tmp_path)))
    assert (result["verified"], result["value"], result["after"]) == (False, 1, "01")

  def test_toyota_can_write_sends_expanded_data(self, tmp_path):
    window = FakeToyotaCanEcu({0x11: bytes.fromhex("a020")}, {0x11: bytes.fromhex("ff0030")})
    link = _link(FakePanda({(0x750, 0x90): window}))
    result = cz.write_setting(link, catalog.ecu("750/90"), WINDOW_SETTING, 0, "a00020", BackupStore(str(tmp_path)))
    assert (result["verified"], result["value"], result["after"]) == (True, 0, "a00000")
    assert window.memory[0x11] == bytes.fromhex("a000")
    assert bytes.fromhex("3b11a00000") in window.requests

  def test_restore_backs_up_current_value_then_writes_backup_back(self, tmp_path):
    fake, link = _body_ecu_link()
    backups = BackupStore(str(tmp_path))
    written = cz.write_setting(link, catalog.ecu("750/40"), catalog.setting(HEADLIGHTS), 0, "01", backups)
    restored = cz.restore_setting(link, catalog.ecu("750/40"), catalog.setting(HEADLIGHTS), backups.get(written["backupId"]), backups)
    assert restored["verified"] and restored["value"] == 1
    assert fake.memory[0x2270] == b"\x01"
    assert backups.get(restored["backupId"])["data"] == "00"        # what was saved before restoring is the overwritten value
    assert backups.get(written["backupId"])["restored"] is True

  def test_unverified_restore_keeps_backup_restorable(self, tmp_path):
    fake, link = _body_ecu_link()
    backups = BackupStore(str(tmp_path))
    written = cz.write_setting(link, catalog.ecu("750/40"), catalog.setting(HEADLIGHTS), 0, "01", backups)
    fake.ignore_writes = True
    restored = cz.restore_setting(link, catalog.ecu("750/40"), catalog.setting(HEADLIGHTS), backups.get(written["backupId"]), backups)
    assert not restored["verified"]
    assert not backups.get(written["backupId"]).get("restored")

  def test_undo_restores_only_its_own_bits(self, tmp_path):
    # 750/B5 DID 2009 is c0 00 on the real car: 0x80 / 0x40 of byte 1 are two different settings
    fake = FakeUdsEcu.from_probe(PROBE, "750", "B5")
    link = _link(FakePanda({(0x750, 0xB5): fake}))
    backups = BackupStore(str(tmp_path))
    ecu = catalog.ecu("750/B5")
    closed = catalog.setting("car_setting_auto_arm_on_doors_closed")
    closing = catalog.setting("car_setting_auto_arm_on_doors_closing")
    first = cz.write_setting(link, ecu, closed, 1, "c000", backups)
    cz.write_setting(link, ecu, closing, 1, "c080", backups)
    restored = cz.restore_setting(link, ecu, closed, backups.get(first["backupId"]), backups)
    assert fake.memory[0x2009] == bytes.fromhex("c040")             # closing, written later, isn't undone along with it
    assert restored["verified"] and restored["value"] == 0
