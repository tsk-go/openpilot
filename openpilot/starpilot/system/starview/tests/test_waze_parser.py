"""Waze parser (tablet snapshots -> next maneuver) and comparison with StarPilot's route."""

from openpilot.starpilot.system.starview import waze_parser


def node(t="", d="", i="", b=(0, 0, 0, 0), c="TextView"):
  return {"t": t, "d": d, "i": i, "b": list(b), "c": c}


def nav_snapshot(**kw):
  nodes = [
    node(d="Turn right", c="ImageView", b=(20, 20, 140, 140)),
    node("0.3", b=(150, 30, 230, 90)),
    node("mi", b=(235, 40, 280, 90)),
    node("Main St", b=(150, 95, 600, 140)),
    node("Then", b=(20, 160, 90, 190)),
    node("12:45 PM", b=(40, 1500, 200, 1560)),
    node("18 min", b=(260, 1500, 400, 1560)),
    node("7.4 mi", b=(440, 1500, 600, 1560)),
  ]
  snap = {"v": 1, "t": 1, "w": 1200, "h": 1600, "present": True, "nodes": nodes}
  snap.update(kw)
  return snap


def test_parse_layout_heuristics():
  p = waze_parser.parse(nav_snapshot())
  assert p["navigating"]
  assert abs(p["distanceM"] - 0.3 * 1609.344) < 1
  assert p["street"] == "Main St"
  assert p["modifier"] == "right"
  assert p["etaClock"] == "12:45 PM"
  assert p["remainingMin"] == 18
  assert abs(p["remainingM"] - 7.4 * 1609.344) < 1


def test_parse_ids_and_destination():
  snap = nav_snapshot()
  snap["nodes"].append(node("Drive to ShopRite of Lakewood", b=(40, 1400, 800, 1440)))
  snap["nodes"].append(node("500 ft", i="next_distance", b=(150, 300, 260, 340)))
  p = waze_parser.parse(snap)
  assert p["destination"] == "ShopRite of Lakewood"
  assert abs(p["distanceM"] - 500 * 0.3048) < 1  # id hint beats layout
  assert "distance:id" in p["via"]


def test_not_present_or_not_navigating():
  assert not waze_parser.parse({"present": False, "nodes": []})["navigating"]
  p = waze_parser.parse({"present": True, "h": 1600, "nodes": [node("Where to?", b=(0, 100, 500, 150))]})
  assert not p["navigating"]


def test_street_match_and_compare():
  assert waze_parser.street_match("Main St", "Main Street")
  assert waze_parser.street_match("I-287 N", "Interstate 287 North")
  assert waze_parser.street_match("Exit 9: Garden State Pkwy", "Garden State Parkway")
  assert not waze_parser.street_match("Main St", "Broad Street")
  p = waze_parser.parse(nav_snapshot())
  agree = waze_parser.compare(p, {"valid": True, "maneuverPrimaryText": "Main Street", "maneuverDistance": 480.0, "maneuverModifier": "right"})
  assert agree["wazeAgree"] is True
  dis = waze_parser.compare(p, {"valid": True, "maneuverPrimaryText": "Broad Street", "maneuverDistance": 2500.0, "maneuverModifier": "left"})
  assert dis["wazeAgree"] is False
  assert waze_parser.compare(p, None)["wazeAgree"] is None


def real_split_screen(sheet=False):
  """Layout seen on the Lenovo tablet (Oct 8): Waze in the right half, banner on top, bottom bar / sheet below."""
  nodes = [
    node("0.3 miles", i="distance_text", b=(1136, 80, 1310, 135)),
    node("Ocean Pkwy", i="street_text", b=(1136, 140, 1400, 185)),
    node(d="", i="direction_icon", c="ImageView", b=(1040, 80, 1110, 160)),
  ]
  if sheet:
    nodes += [node("12:41 PM", b=(1420, 340, 1590, 390)), node("59 min", b=(1400, 395, 1480, 430)),
              node("20 mi", b=(1520, 395, 1600, 430)),
              node("Work, 85 Inip Drive, Inwood, NY", b=(1330, 480, 1700, 510)),
              node("Via Belt Pkwy E Brooklyn", b=(1340, 525, 1670, 560)), node("Add a stop", b=(1340, 730, 1460, 760)),
              node("Share drive", b=(1450, 1095, 1560, 1120)), node("Stop", b=(1050, 1165, 1120, 1200)),
              node("Resume", b=(1520, 1165, 1640, 1200))]
  else:
    nodes += [node("12:34 PM", i="eta_time", b=(1420, 1130, 1590, 1175)), node("1:02 h", i="eta_duration", b=(1400, 1180, 1480, 1215)),
              node("20 mi", i="eta_distance", b=(1520, 1180, 1600, 1215))]
  return {"v": 1, "t": 1, "w": 2000, "h": 1250, "present": True, "nodes": nodes}


def test_real_layout_driving_screen():
  p = waze_parser.parse(real_split_screen())
  assert p["navigating"] and p["distanceText"] == "0.3 miles" and p["street"] == "Ocean Pkwy"
  assert p["remainingMin"] == 62 and abs(p["remainingM"] - 20 * 1609.344) < 1
  assert p["destination"] == ""          # not on the driving screen
  assert p["etaClock"] == "12:34 PM"


def test_real_layout_sheet_open():
  p = waze_parser.parse(real_split_screen(sheet=True))
  assert p["sheetOpen"] and p["navigating"]
  assert p["destinationLabel"] == "Work" and p["destination"] == "85 Inip Drive, Inwood, NY"
  assert p["viaRoad"] == "Belt Pkwy E Brooklyn"
  assert p["street"] == "Ocean Pkwy"


def test_and_then_row_is_not_the_street():
  snap = real_split_screen()
  snap["nodes"][1]["t"] = "Ave F"
  snap["nodes"].append(node("and then", b=(1020, 220, 1110, 250)))
  p = waze_parser.parse(snap)
  assert p["street"] == "Ave F" and p["then"] == "and then"


def test_highway_names_and_distance_only():
  assert waze_parser.street_match("878 North", "NY 878")
  assert waze_parser.street_match("878 North", "Nassau Expressway NY 878 North")
  assert not waze_parser.street_match("878 North", "I-495 West")
  w = {"navigating": True, "street": "878 North", "distanceM": 152.0, "modifier": ""}
  r = waze_parser.compare(w, {"valid": True, "maneuverPrimaryText": "Nassau Expressway", "maneuverDistance": 180.0, "maneuverModifier": "left"})
  assert r["wazeAgree"] is True and r["wazeWhy"] == "distance" and r["mbStreet"] == "Nassau Expressway"
  r = waze_parser.compare(w, {"valid": True, "maneuverPrimaryText": "Burnside Avenue", "maneuverDistance": 2400.0})
  assert r["wazeAgree"] is False and r["mbDistance"] == 2400.0
  r = waze_parser.compare(w, {"valid": True, "maneuverType": "depart", "maneuverPrimaryText": "x", "maneuverDistance": 50.0})
  assert r["wazeAgree"] is None and r["wazeWhy"] == "starting"


def test_signpost_and_later_step():
  sign = "to Kennedy Airport / Belt Pkwy W / I-678 Van Wyck Expwy"
  assert waze_parser.road_names(sign) == ["Belt Pkwy W", "I-678 Van Wyck Expwy"]
  w = {"navigating": True, "street": sign, "distanceM": 3862.0, "modifier": ""}
  mb = {"valid": True, "maneuverPrimaryText": "Rockaway Boulevard", "maneuverDistance": 600.0}
  assert waze_parser.compare(w, mb)["wazeAgree"] is False
  up = [("Continue onto Rockaway Boulevard", 600.0), ("Take the ramp toward Belt Parkway West", 3800.0)]
  r = waze_parser.compare(w, mb, up)
  assert r["wazeAgree"] is True and r["wazeWhy"] == "later step"
  assert waze_parser.compare(w, mb, [("Take the ramp toward Belt Parkway West", 9000.0)])["wazeAgree"] is False


def test_drive_oct15_opposite_sides_and_other_streets_disagree():
  # Waze LEFT onto "Ave N." in 50 ft, StarPilot RIGHT onto Avenue N in 60 ft: same street, other way
  w = {"navigating": True, "street": "Ave N.", "distanceM": 15.2, "modifier": "left"}
  mb = {"valid": True, "maneuverType": "turn", "maneuverPrimaryText": "Avenue N", "maneuverDistance": 18.0, "maneuverModifier": "right"}
  r = waze_parser.compare(w, mb)
  assert r["wazeAgree"] is False and r["wazeWhy"] == "waze left, starpilot right" and r["wazeSide"] == "left"
  # Waze "Ave R" in 0.1 mi, StarPilot Kings Highway in 100 ft: the distance is within Waze's 0.1 mi step, the streets aren't
  w = {"navigating": True, "street": "Ave R", "distanceM": 160.9, "modifier": ""}
  mb = {"valid": True, "maneuverType": "turn", "maneuverPrimaryText": "Kings Highway", "maneuverDistance": 30.0, "maneuverModifier": "right"}
  r = waze_parser.compare(w, mb)
  assert r["wazeAgree"] is False
  # same street, same side: agree
  w = {"navigating": True, "street": "Ave R", "distanceM": 160.9, "modifier": "left"}
  mb = {"valid": True, "maneuverType": "turn", "maneuverPrimaryText": "Avenue R", "maneuverDistance": 150.0, "maneuverModifier": "left"}
  r = waze_parser.compare(w, mb)
  assert r["wazeAgree"] is True and r["wazeSide"] == "left"
  # a slight right (exit) is the right side too
  w = {"navigating": True, "street": "Belt Pkwy", "distanceM": 400.0, "modifier": "right"}
  mb = {"valid": True, "maneuverType": "off ramp", "maneuverPrimaryText": "Belt Parkway", "maneuverDistance": 420.0, "maneuverModifier": "slightRight"}
  r = waze_parser.compare(w, mb)
  assert r["wazeAgree"] is True


def test_tablet_arrow_reading_gives_the_direction():
  snap = nav_snapshot()
  snap["nodes"] = [n for n in snap["nodes"] if n["d"] != "Turn right"]
  snap["nodes"].append(node(d="turn left (StarView arrow)", i="starview_arrow", c="ImageView", b=(20, 20, 140, 140)))
  p = waze_parser.parse(snap)
  assert p["modifier"] == "left" and p["maneuverType"] == "turn"
