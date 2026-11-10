"""StarView draws Galaxy's settings rows natively (GalaxyRows.kt / GalaxySettingsView.kt), so whatever Galaxy's web
page does to a row before showing it has to be done there too. Oct 26: Galaxy showed Lane Centering Strength as 1-10
(galaxy-setting-row.js presentedSetting) while StarView kept the saved "%" unit and upstream's old "100% is normal"
text, so the top of the scale read "10 %".

These tests fail when upstream changes that presentation code or adds a new kind of display scale. Then: mirror the
change in StarView (GalaxyRows.kt bounds / shown / saved / withUnit / shownReason, GalaxySettingsView.kt), ship the
app, and record the new fingerprint here. Nothing in this file runs on the car.
"""
import hashlib
import re
from pathlib import Path

GALAXY = Path(__file__).resolve().parents[3] / "galaxy"
ROW_JS = GALAXY / "web" / "js" / "galaxy-setting-row.js"

# What StarView mirrors (as of StarView 2.81.3: Galaxy's Nov 4 "heading" rows are section titles; "coordinate" only
# labels the manual steering coordinates on Galaxy's FLM page, which StarView doesn't draw; "previewSound" (upstream
# 359cb9fda, Nov 6) - Galaxy's play button on a volume row - StarView calls the same /api/sounds/preview by itself when
# a volume slider is let go; "collapsed" (upstream d4b781ab, Nov 8) - a heading whose card stays folded until opened -
# no row sets it, see test_no_row_is_collapsed_yet)
MIRRORED_SCALES = {"lane-strength"}
ROW_FIELDS = {"action", "available", "choices", "collapsed", "confirm", "coordinate", "defaultValue", "displayScale", "heading", "label",
              "maximum", "minimum", "page", "previewSound", "reason", "repairValue", "resetAvailable", "step", "unit", "value"}
PRESENTATION_SHA256 = "1bf21707507137fe81bba21be8a5e39e75128b1c76037728e4dc5b2d36e09268"


def presentation_source() -> str:
  """The functions that turn a row into what's shown, plus the template lines for the value, slider range and text."""
  src = ROW_JS.read_text()
  start, end = src.index("export function numericBounds"), src.index("export const GalaxySettingRow")
  shown = [line.strip() for line in src[end:].splitlines()
           if any(k in line for k in ("bounds()", "displayValue", "presentedRow.unit", "presentedRow.reason", "numericMax",
                                      "laneStrengthSaved", "repairValue === 'Reset'"))]
  return src[start:end] + "\n".join(shown)


def test_galaxy_row_presentation_unchanged():
  sha = hashlib.sha256(presentation_source().encode()).hexdigest()
  assert sha == PRESENTATION_SHA256, (
    f"Galaxy's setting-row presentation changed (galaxy-setting-row.js, sha256 {sha}): mirror it in StarView's " +
    "GalaxyRows.kt / GalaxySettingsView.kt, then record the new sha256 in this test")


def test_no_display_scale_starview_does_not_know():
  scales = set()
  for f in list(GALAXY.glob("*.py")) + list((GALAXY / "web" / "js").glob("*.js")):
    scales |= set(re.findall(r"""displayScale["']?\s*(?:[:=]=?=?|!==|===)\s*["']([a-z0-9-]+)["']""", f.read_text()))
  assert scales and scales <= MIRRORED_SCALES, f"new Galaxy display scale(s) StarView doesn't mirror: {sorted(scales - MIRRORED_SCALES)}"


def test_row_fields_starview_reads():
  """A new field in the rows Galaxy sends (settings.py _projection) may carry presentation StarView would miss."""
  src = (GALAXY / "settings.py").read_text()
  start = src.index("def _projection(")
  body = src[start:src.index("\ndef ", start + 10)]
  fields = set(re.findall(r'"([A-Za-z]+)":', body))
  assert fields == ROW_FIELDS, f"Galaxy's row fields changed: new {sorted(fields - ROW_FIELDS)}, gone {sorted(ROW_FIELDS - fields)}"


def test_no_row_is_collapsed_yet():
  """Galaxy's rows carry "collapsed" since Nov 8 (upstream d4b781ab): a heading whose rows stay folded until it's opened.
  The only one, "Specific car experiments", went again the same day (cc51e9e4), so StarView folds nothing. Once a row
  sets it, GalaxySettingsView.kt has to fold that card the same way (rowCards in galaxy/web/js/settings.js)."""
  kwarg = re.compile(r"[(,]\s*collapsed\s*=\s*(?!False\b)")
  users = [str(f.relative_to(GALAXY.parent)) for f in GALAXY.parent.rglob("*.py")
           if "tests" not in f.parts and kwarg.search(f.read_text(errors="ignore"))]
  assert not users, f"Galaxy rows that start folded, which StarView doesn't fold yet: {users}"
