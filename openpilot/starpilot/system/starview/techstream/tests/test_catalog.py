from openpilot.starpilot.system.starview.techstream import catalog


# ---- 4th-gen Sienna catalog (toyopilot's Carista-derived data, translated to English) ----

def _has_cjk(text: str) -> bool:
  # CJK symbols/punctuation, CJK unified ideographs, full-width forms
  return any(0x3000 <= ord(ch) <= 0x303F or 0x4E00 <= ord(ch) <= 0x9FFF or 0xFF00 <= ord(ch) <= 0xFFEF for ch in text)


class TestSiennaCatalog:
  def test_counts_match_the_car(self):
    sienna = catalog.load_sienna()
    # the real car reports 132 supported settings, minus the two kick-sensor sensitivities; 41 ECUs answer; 36 live
    # items (24 of them are the hybrid battery)
    assert len(sienna["settings"]) == 130
    assert len(sienna["ecus"]) == 41
    assert len(sienna["live"]) == 36
    assert len(sienna["categories"]) == 18
    assert [t["id"] for t in sienna["liveTools"]] == ["wheels", "engine", "hvac"]
    assert not [s for s in sienna["settings"] if "kick_sensor" in s["key"]]

  def test_keys_are_unique(self):
    sienna = catalog.load_sienna()
    for section, field in (("ecus", "id"), ("categories", "id"), ("settings", "key"), ("live", "key"), ("liveTools", "id")):
      keys = [entry[field] for entry in sienna[section]]
      assert len(keys) == len(set(keys)), section

  def test_window_ecus_use_toyota_can(self):
    sienna = catalog.load_sienna()
    toyota_can = {e["id"] for e in sienna["ecus"] if e["protocol"] == "toyota_can"}
    assert toyota_can == {"750/90", "750/91", "750/92", "750/93", "750/EC", "750/AD"}
    assert all((s["localId"] is None) == (catalog.ecu(s["ecu"])["protocol"] == "uds") for s in sienna["settings"])

  def test_everything_user_facing_is_english(self):
    sienna = catalog.load_sienna()
    names = ([e["name"] for e in sienna["ecus"]] + [c["name"] for c in sienna["categories"]]
             + [s["name"] for s in sienna["settings"]] + [i["name"] for i in sienna["live"]] + [t["name"] for t in sienna["liveTools"]])
    assert all(n.strip() for n in names)
    assert [n for n in names if _has_cjk(n)] == []
    # option labels may be numbers with units (climate temperature offset +-3 °C), but no Chinese may be left
    labels = [o["label"] for s in sienna["settings"] for o in s["options"]]
    assert all(label.strip() for label in labels)
    assert [label for label in labels if _has_cjk(label)] == []
    live_labels = [o["label"] for i in sienna["live"] for o in i["options"] or []]
    assert [label for label in live_labels if _has_cjk(label)] == []
    dtc_text = sienna["dtcText"]
    assert [t for t in list(dtc_text["codes"].values()) + list(dtc_text["ftb"].values()) if _has_cjk(t)] == []

  def test_references_resolve(self):
    sienna = catalog.load_sienna()
    categories = {c["id"] for c in sienna["categories"]}
    live_keys = {i["key"] for i in sienna["live"]}
    assert all(s["category"] in categories and catalog.ecu(s["ecu"]) for s in sienna["settings"])
    assert all(catalog.ecu(i["ecu"]) for i in sienna["live"])
    assert all(k in live_keys for t in sienna["liveTools"] for k in t["keys"])
    assert sum(s["popular"] for s in sienna["settings"]) == 8

  def test_masks_and_addresses_parse(self):
    sienna = catalog.load_sienna()
    for s in sienna["settings"]:
      assert 0 < int(s["mask"], 16) <= 0xFF and s["byteIndex"] >= 0, s["key"]
      assert (s["did"] is None) == (s["localId"] is not None), s["key"]
      if s["did"] is not None:
        int(s["did"], 16)
      else:
        int(s["localId"], 16)
      assert bool(s["options"]) != bool(s["numeric"]), s["key"]
    for i in sienna["live"]:
      int(i["mask"], 16)
      int(i["did"], 16)
    for e in sienna["ecus"]:
      tx, sub = catalog.ecu_address(e)
      assert 0x700 <= tx <= 0x7FF and (sub is None or 0 <= sub <= 0xFF), e["id"]

  def test_lookups(self):
    headlights = catalog.setting("car_setting_warn_headlights_on_door_open")
    assert (headlights["ecu"], headlights["did"], headlights["byteIndex"], headlights["mask"]) == ("750/40", "2270", 0, "FF")
    assert headlights["name"] == "Headlights-on reminder when door opens"
    assert headlights["options"] == [{"value": 1, "label": "On"}, {"value": 0, "label": "Off"}]
    assert catalog.ecu("750/40")["tx"] == "750" and catalog.ecu("750/40")["sub"] == "40"
    assert catalog.ecu("750/40")["name"] == "Main Body"
    assert catalog.ecu("7B0")["sub"] is None
    assert catalog.setting("nope") is None and catalog.ecu("123") is None
    wheel = catalog.live_item("car_tool_front_right_wheel_speed")
    assert (wheel["ecu"], wheel["did"], wheel["mult"], wheel["unit"]) == ("7B0", "1002", 0.1, "km/h")
    assert catalog.option_label(headlights["options"], 0) == "Off"
    assert catalog.option_label(headlights["options"], 7) is None and catalog.option_label(None, 1) is None

  def test_battery_layout(self):
    blocks = catalog.load_sienna()["battery"]["blocks"]
    # blocks 1, 2, 11, 12 are half blocks (2 modules), the rest full (4 modules): 40 modules in all
    assert [b["modules"] for b in blocks] == [2, 2, 4, 4, 4, 4, 4, 4, 4, 4, 2, 2]
    assert blocks[0]["voltageKey"] == "car_ev_or_hybrid_battery_n1_block_1_voltage"
    assert catalog.live_item(blocks[11]["resistanceKey"])["did"] == "1813"

  def test_dtc_text_covers_carista_tables(self):
    dtc_text = catalog.load_sienna()["dtcText"]
    # Toyota table 1073 + generic OBD-II table 4277, 5345 base codes after de-duplication; FTB 01..FF is 255
    assert (len(dtc_text["codes"]), len(dtc_text["ftb"])) == (5345, 255)
    assert dtc_text["codes"]["U0131"] == "Lost Communication With Power Steering Control Module"
    assert dtc_text["codes"]["B2359"] == "Right Smart LDM"
    assert (dtc_text["ftb"]["87"], dtc_text["ftb"]["13"]) == ("Missing Message", "Circuit Open")

  def test_engine_dependent_live_items_are_marked(self):
    marked = {i["key"] for i in catalog.load_sienna()["live"] if i["needsEngineRunning"]}
    assert marked == {"car_tool_engine_speed", "car_calculated_load", "car_tool_coolant_temp"}
