"""The latest limit, its attention animation and override mark on both screens."""

import time

import pyray as rl

from openpilot.starpilot.ui.large_speed_geometry import LARGE_SIGN_SCALE
from openpilot.starpilot.ui.onroad_state import OnroadState, speed_limit_bounds
from openpilot.starpilot.ui.presentation import BitmapFonts, FontRole, Profile
from openpilot.starpilot.ui.speed_limit_pulse import SpeedLimitPulse
from openpilot.starpilot.ui.speed_limit_shapes import SpeedLimitShapes
from openpilot.starpilot.ui.unified_speed_presentation import displayed_adjusted_limit_mps, resolve_unified_speed


INK = rl.Color(241, 246, 243, 255)
MUTED = rl.Color(190, 208, 202, 255)
SOURCE_LABELS = {'dashboard': 'DASH', 'map': 'OSM', 'vision': 'VISION', 'mapbox': 'NAV'}


def draw_text(fonts, text, role, size, x, y, color=INK):
  if isinstance(color, (tuple, list)):
    color = rl.Color(*color)
  radius = 1.15 if fonts.profile == Profile.LARGE else 1.
  contour = rl.Color(6, 14, 10, round(color.a * .90))
  for dx, dy in ((-radius, 0), (radius, 0), (0, -radius), (0, radius)):
    fonts.draw(text, role, size, x + dx, y + dy, contour)
  fonts.draw(text, role, size, x, y + (1.5 if fonts.profile == Profile.LARGE else 1.2),
             rl.Color(7, 16, 12, round(color.a * .32)))
  fonts.draw(text, role, size, x, y, color)


def draw_line(profile, start, end, stroke, color):
  radius = 1.4 if profile == Profile.LARGE else 1.
  rl.draw_line_ex(start, end, stroke + 2 * radius, rl.Color(6, 14, 10, round(color.a * .87)))
  rl.draw_line_ex(start, end, stroke, color)


def draw_ink(fonts, text, role, size, x, top, color=INK):
  ink_top, ink_bottom = fonts.vertical_ink(text, role, size)
  draw_text(fonts, text, role, size, x, top - ink_top, color)
  return fonts.measure(text, role, size).width, ink_bottom - ink_top


def draw_caption(fonts, label, x, top, color=MUTED, *, unit=None):
  large = fonts.profile == Profile.LARGE
  width, height = draw_ink(fonts, label, FontRole.MEDIUM, 32 if large else 24, x, top, color)
  if unit:
    size = 28 if large else 20
    unit_top, _ = fonts.vertical_ink(unit, FontRole.NORMAL, size)
    # Exclude the p descender when aligning mph to the caption baseline.
    _, baseline = fonts.vertical_ink('mh' if unit == 'mph' else unit, FontRole.NORMAL, size)
    gap = 12 if large else 8
    unit_width, _ = draw_ink(fonts, unit, FontRole.NORMAL, size, x + width + gap,
                             top + height - (baseline - unit_top), color)
    width += gap + unit_width
  return width, height


class SpeedLimitWidget:
  def __init__(self, fonts: BitmapFonts, profile: Profile):
    self.fonts = fonts
    self.profile = profile
    self.scale = LARGE_SIGN_SCALE if profile == Profile.LARGE else 1
    self.text_scale = self.scale * Profile.COMPACT.font_scale / profile.font_scale
    self.pulse = SpeedLimitPulse()
    self.shapes = SpeedLimitShapes(self.scale, headless_context=getattr(fonts, '_headless_context', False))

  def close(self):
    self.shapes.close()

  def render(self, state: OnroadState) -> None:
    bounds = speed_limit_bounds(self.profile, state)
    now = state.observed_ns / 1e9 if state.observed_ns else time.monotonic()
    self.pulse.update(state, now, visible=bounds is not None)
    if bounds is None:
      return
    self._sign(state, bounds, now)

  def _sign(self, state: OnroadState, bounds, now: float) -> None:
    shown, obs = resolve_unified_speed(state), state.speed_limit
    heading = 'LAST' if str(obs.kind) != 'valid' else SOURCE_LABELS.get(shown.source, 'SPEED')
    x, top = bounds[0] + 12, bounds[1] + 12
    scale = self.scale
    pending = shown.pending and not obs.automatic_adoption_pending
    target = displayed_adjusted_limit_mps(obs) if pending else None
    arrow_direction = 0
    if target is not None and state.speed_mps is not None and target != state.speed_mps:
      arrow_direction = -1 if target > state.speed_mps else 1
    white = self.pulse.color(rl.Color(244, 247, 245, 255), now)
    secondary = self.pulse.color(rl.Color(223, 232, 227, 255), now)

    def ink(text, role, size):
      return tuple(value / scale for value in (*self.fonts.horizontal_ink(text, role, size * self.text_scale),
                                               *self.fonts.vertical_ink(text, role, size * self.text_scale)))

    def centered(text, role, size, ink_top, color, center_x=59):
      left, right, a, b = ink(text, role, size)
      # Snap only the final draw, after fitting in the shared 118 x 132 geometry.
      origin = round(x + (center_x - (left + right) / 2) * scale)
      y = round(top + (ink_top - a) * scale)
      self.fonts.draw(text, role, size * self.text_scale, origin, y, color)
      return origin + left * scale, y + a * scale, origin + right * scale, y + b * scale

    def circle_fits(left, right, a, b):
      return all((px - 59) ** 2 + (py - 67) ** 2 <= 46 ** 2
                 for px in (left, right) for py in (a, b))

    vienna = state.appearance.use_vienna_sign
    color = rl.Color(0, 0, 0, 255) if vienna else white
    if vienna:
      self.shapes.circle(x + 59 * scale, top + 67 * scale, self.pulse.color(rl.Color(201, 34, 49, 255), now))
    else:
      self.shapes.outline(x + 59 * scale, top + 66 * scale, white)

    left, right, a, b = ink(heading, FontRole.SEMI_BOLD, 18)
    heading_width = right - left
    header_y = 47 if vienna else 26
    # The small arrow's visible ink is 12 x 16, with a six-pixel label gap.
    header_left = 59 - (heading_width + (18 if arrow_direction else 0)) / 2
    centered(heading, FontRole.SEMI_BOLD, 18, header_y - (b - a) / 2, color, header_left + heading_width / 2)
    if arrow_direction:
      self.shapes.arrow('compact', round(x + (header_left + heading_width + 12) * scale),
                        round(top + header_y * scale), arrow_direction, color)

    size = 58 if vienna else 64
    offset_size = 30 if vienna else 27
    number_center = (73 if shown.offset_text else 80) if vienna else (67 if shown.offset_text else 81)
    while True:
      left, right, a, b = ink(shown.posted_text, FontRole.BOLD, size)
      width, height = right - left, b - a
      number_top = number_center - height / 2
      if vienna:
        fits = number_top >= 57 and circle_fits(59 - width / 2, 59 + width / 2, number_top, number_top + height)
        if shown.offset_text:
          left, right, a, b = ink(shown.offset_text, FontRole.MEDIUM, offset_size)
          offset_top = number_top + height + 4
          fits = fits and circle_fits(59 - (right - left) / 2, 59 + (right - left) / 2, offset_top, offset_top + b - a)
      else:
        fits = width <= 96 and height <= 54
      if fits:
        break
      size *= .95
      if vienna:
        offset_size *= .95
    number = centered(shown.posted_text, FontRole.BOLD, size, number_top, color)
    if shown.offset_text:
      if not vienna:
        left, right, a, b = ink(shown.offset_text, FontRole.MEDIUM, offset_size)
        offset_size *= min(1, 96 / (right - left), 24 / (b - a))
        offset_top = 97
      centered(shown.offset_text, FontRole.MEDIUM, offset_size, offset_top, color if vienna else secondary)
    if obs.driver_override_active:
      color = rl.Color(197, 163, 255, 240)
      left, top, right, bottom = number
      for start, end in ((rl.Vector2(left + 3 * scale, top + 3 * scale), rl.Vector2(right - 3 * scale, bottom - 3 * scale)),
                         (rl.Vector2(right - 3 * scale, top + 3 * scale), rl.Vector2(left + 3 * scale, bottom - 3 * scale))):
        rl.draw_line_ex(start, end, 4.5 * scale, rl.Color(6, 14, 10, 220))
        rl.draw_line_ex(start, end, 2.5 * scale, color)
