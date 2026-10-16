#!/usr/bin/env python3
"""Builds TechStream's extra data for a 4th-gen Sienna HV from Toyota's own Techstream/GTS+ metadata, as published by
github.com/kaikozlov/toyota-diagnostics (toyota_diag/data/toyota_current_diag.zip, unzipped):

  data/toyota_settings.json   every North America Customize item aimed at a Sienna HV module (UDS, one byte field),
                              minus the ones toyopilot's catalog already has (those keep their car-verified options)
  data/active_tests.json      Toyota's Active Tests for the Sienna HV body / comfort modules (UDS 2F direct tests,
                              modes 0/1/3/4/6, and fixed 31 routines) - powertrain, brake, ADAS and telematics left out

Toyota's names and addresses check out against toyopilot's car-verified catalog (115 of 116 at the same address and
bit); its option lists often don't (33 of 115 agree), so settings from here are marked unverified and keep Toyota's
option names as hints only.

usage: build_toyota_extras.py <unzipped bundle dir> <techstream data dir>
"""
import json
import os
import sys

BUNDLE, OUT = sys.argv[1], sys.argv[2]
idx = json.load(open(os.path.join(BUNDLE, "index.json")))
na = idx["regions"]["NA"]
V, I, C, R = na["vehicles"], na["install_sets"], na["categories"], na["routes"]
cust = json.load(open(os.path.join(BUNDLE, "customize", "NA", "0.json")))
base = json.load(open(os.path.join(OUT, "sienna_catalog.json")))

# modules (category id -> address) of every "Sienna HV" vehicle row (gen 4, 2021+)
cats = {}
for v in V.values():
  if v["name"] != "Sienna HV":
    continue
  for i in v["install_set_ids"]:
    for e in I.get(str(i), []):
      r = R.get(e["route_key"], {})
      tx = r.get("physical_request_address")
      if not tx:
        continue
      sub = (r.get("address_extension") or None) if tx == 0x750 else None
      ecu_id = f"{tx:X}" + (f"/{sub:02X}" if sub is not None else "")
      cats.setdefault(e["category_id"], {"id": ecu_id, "tx": f"{tx:X}", "sub": f"{sub:02X}" if sub is not None else None,
                                         "name": C[str(e["category_id"])]["name"], "phase": int(e["route_key"].split(":")[1])})

NO_SETTINGS = {"Engine", "Hybrid Control"}                     # powertrain behaviour: not offered
TEST_MODULES = {"Main Body", "Combination Meter", "Air Conditioner", "RL Door/LH PSD", "RR Door/RH PSD", "Back Door",
                "Power Back Door", "Headlight Control", "Headlight Control (Sub)", "Mirror L", "Mirror R", "Head Up Display",
                "Entry&Start", "Vehicle Proximity Notification System", 'Blind Spot Monitor "A"', 'Blind Spot Monitor "B"',
                "Active Noise Control", "Tilt&Telescopic", "Intuitive P/A", "Circumference Monitoring Camera Control Module"}
TEST_NAME_BLOCK = ("accelerator", "parking brake", "edss", "collision door lock release", "airbag", "fuel pump", "injector")

known_ecus = {e["id"]: e for e in base["ecus"]}
have = set()
for s in base["settings"]:
  if s["did"] is not None:
    have.add((s["ecu"], s["did"].upper(), s["byteIndex"], s["mask"].upper()))

# ---------------------------------------------------------------- settings
groups = {g["group_id"]: g["name"] for g in cust["groups"]}
by_addr = {}
for it in cust["items"]:
  c = cats.get(it["target_category_id"])
  if not c or c["name"] in NO_SETTINGS or not it.get("write_did") or it["target_phase_type"] != c["phase"]:
    continue
  s, e = it["write_bit_start"], it["write_bit_end"]
  if (s >> 3) != (e >> 3) or (it["current_bit_start"], it["current_bit_end"]) != (s, e):
    continue                                                   # multi-byte / read-write split fields: not handled
  mask = 0
  for b in range(s, e + 1):
    mask |= 0x80 >> (b & 7)
  key = (c["id"], f"{it['write_did']:04X}", s >> 3, f"{mask:02X}")
  if key in have:
    continue
  by_addr.setdefault(key, []).append((it, c))

settings, used_ecus, used_groups = [], set(), {}
for (ecu_id, did, byte, mask), rows in sorted(by_addr.items()):
  it, c = rows[0]
  names = list(dict.fromkeys(r[0]["name"].strip() for r in rows))
  width = bin(int(mask, 16)).count("1")
  maxv = (1 << width) - 1
  toyota_choices = []
  for r in rows:
    for ch in r[0]["choices"]:
      if 0 <= ch["value"] <= maxv and (ch["value"], ch["name"]) not in toyota_choices:
        toyota_choices.append((ch["value"], ch["name"]))
  hint = "Toyota's option names (unverified): " + ", ".join(f"{v} = {n}" for v, n in toyota_choices) if toyota_choices else ""
  if width <= 3:
    labels = {}
    for v, n in toyota_choices:
      labels.setdefault(v, n)
    options = [{"value": v, "label": f"{v} · {labels[v]}" if v in labels else str(v)} for v in range(maxv + 1)]
    numeric = None
  else:
    options, numeric = [], {"min": 0, "max": maxv}
  gname = groups.get(it["group_id"], "Other")
  cat_id = "TOYOTA_" + "".join(ch if ch.isalnum() else "_" for ch in gname.upper())
  used_groups[cat_id] = gname
  used_ecus.add(ecu_id)
  settings.append({
    "key": f"toyota_{ecu_id.replace('/', '_')}_{did}_{byte}_{mask}", "category": cat_id,
    "name": " / ".join(names) + (f" (byte {byte})" if any(k[0] == ecu_id and k[1] == did and k[2] != byte for k in by_addr) else ""),
    "ecu": ecu_id, "did": did, "localId": None, "byteIndex": byte, "mask": mask,
    "requiresBitSupportCheck": any(r[0]["merge_mode"] == 1 for r in rows),
    "options": options, "numeric": numeric, "popular": False,
    "source": "toyota", "unverified": True, "hint": hint,
  })

ecus = []
for eid in sorted(used_ecus):
  if eid in known_ecus:
    continue
  c = next(c for c in cats.values() if c["id"] == eid)
  ecus.append({"id": eid, "tx": c["tx"], "sub": c["sub"], "name": c["name"], "protocol": "uds"})
categories = [{"id": k, "name": f"Toyota list: {v}", "icon": "list"} for k, v in sorted(used_groups.items(), key=lambda kv: kv[1])]
json.dump({"source": "Toyota GTS+ North America Customize master via kaikozlov/toyota-diagnostics",
           "ecus": ecus, "categories": categories, "settings": settings},
          open(os.path.join(OUT, "toyota_settings.json"), "w"), indent=0)

# ---------------------------------------------------------------- active tests
tests, test_ecus = [], {}
for cid, c in cats.items():
  if c["name"] not in TEST_MODULES:
    continue
  p = os.path.join(BUNDLE, "catalogs", "NA", f"{cid}.json")
  if not os.path.exists(p):
    continue
  for a in json.load(open(p)).get("active_tests", []):
    name = str(a.get("name") or "").strip()
    if not name or any(w in name.lower() for w in TEST_NAME_BLOCK):
      continue
    if a.get("kind") == "direct" and a.get("execution") in ("plan_only", "executable") and not a.get("multi_control_group") \
       and a.get("encoding_mode") in (0, 1, 3, 4, 6) and a.get("session_requirement") == "extended":
      info = a.get("signal_info") or {}
      t = {"ecu": c["id"], "id": f"d{a['id']}", "name": name, "kind": "direct", "did": f"{a['did']:04X}",
           "mode": a["encoding_mode"], "bitStart": a["bit_start"], "bitEnd": a["bit_end"],
           "start": a["start_prefix"], "stop": a["stop_prefix"],
           "records": [{"bit": r["control_enable_bit_1based"], "offset": r["data_byte_offset"], "length": r["data_byte_length"],
                        "mode": r["encoding_mode"]} for r in a.get("data_id_for_act_records") or []],
           "choices": [{"label": ch["text"], "value": ch["value"]} for ch in info.get("choices") or [] if ch.get("text")],
           "physical": {k: (info.get("physical") or {}).get(k) for k in ("mul", "div", "offset", "decimal_point_count", "unit")}}
      if not t["choices"]:
        continue                                               # free-value tests (no fixed choices) not offered
    elif a.get("kind") == "routine" and a.get("execution") == "executable" and a.get("fixed_request"):
      t = {"ecu": c["id"], "id": f"r{a['id']}", "name": name, "kind": "routine",
           "start": a["start_static"], "stop": a.get("stop_static") or ""}
    else:
      continue
    tests.append(t)
    test_ecus[c["id"]] = {"id": c["id"], "tx": c["tx"], "sub": c["sub"], "name": c["name"]}
json.dump({"source": "Toyota GTS+ North America Active Tests via kaikozlov/toyota-diagnostics",
           "ecus": sorted(test_ecus.values(), key=lambda e: e["name"]), "tests": tests},
          open(os.path.join(OUT, "active_tests.json"), "w"), indent=0)
summary = f"settings: {len(settings)} new ({len(ecus)} new ECUs, {len(categories)} groups); active tests: {len(tests)} on {len(test_ecus)} modules"
print(summary, file=sys.stderr)
