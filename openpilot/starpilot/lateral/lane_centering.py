"""Bounded lane-centering contribution for lateral control.

The caller owns model freshness, axis authority, and final curvature limiting.
This module neither reads settings nor sends commands.
"""

from dataclasses import dataclass
from enum import StrEnum
import math
from numbers import Real
from typing import Any

import capnp
import numpy as np

from openpilot.cereal import log
from openpilot.common.scalar_clip import clip_scalar


STRENGTH_BASELINE = 1.5
STRENGTH_MAX = 2 * STRENGTH_BASELINE

MIN_SPEED = 5.0
MIN_LANE_PROB = 0.6
MAX_LANE_STD = 0.3
MIN_LANE_WIDTH = 2.6
MAX_LANE_WIDTH = 4.8
MAX_OFFSET = 0.3
MIN_CENTER_TO_LINE = 1.1
MAX_CORRECTION = 0.004 * 0.30
CENTER_ERROR_DEADBAND = 0.08
E2E_MAX_PATH_STD = 0.35
E2E_BREAK_IN_START = 0.15
E2E_BREAK_IN_FULL = 0.50
ACQUIRE_TAU = 0.4
RELEASE_TAU = 0.2

# One good line (the other faded, broken or missing): steer to that line +/- half the lane width.
ONE_LINE_STRENGTH = 0.5          # of the two-line correction
UNKNOWN_WIDTH_STRENGTH = 0.25    # no recent width: a standard lane, weaker still
DEFAULT_LANE_WIDTH = 3.6
WIDTH_MEMORY_M = 300.0           # a width seen with both lines is trusted this far after losing one
WIDTH_AVERAGE_M = 60.0           # the width is averaged over about this distance
MAX_EDGE_STD = 0.5
LINE_NEAR_M = 5.0
MAX_LINE_DIVERGENCE = 0.5        # the line peels away from the model path by more (an exit / merge): off


class ControlMode(StrEnum):
  OFF = "off"
  LATERAL_ONLY = "lateral_only"
  LONGITUDINAL_ONLY = "longitudinal_only"
  COMBINED = "combined"

  @property
  def lateral_authority(self) -> bool:
    return self in (ControlMode.LATERAL_ONLY, ControlMode.COMBINED)


@dataclass(frozen=True)
class LaneCenteringSettings:
  enabled: bool = False
  offset_m: float = 0.0
  e2e_authority: float = 1.0
  pause_on_signal: bool = True
  strength: float = STRENGTH_BASELINE
  one_line: bool = False   # patch 37: also steer by one good line (StarView's switch); off = StarPilot's own


@dataclass(frozen=True)
class LaneCenteringRequest:
  """Optional host configuration; vehicle/model facts come from the host itself."""

  mode: ControlMode
  settings: LaneCenteringSettings
  elapsed_seconds: float
  time_discontinuity: bool = False


@dataclass(frozen=True)
class LaneCenteringInput:
  model: Any
  model_sample_id: int
  model_valid: bool
  base_curvature: float
  speed_mps: float
  mode: ControlMode
  lateral_active: bool
  settings: LaneCenteringSettings
  elapsed_seconds: float
  turn_signal_active: bool = False
  driver_override: bool = False
  time_discontinuity: bool = False


@dataclass(frozen=True)
class LaneCenteringResult:
  # None means the caller's proposed curvature was invalid and must be rejected.
  candidate_curvature: float | None
  correction: float
  direction: int
  reason: str


def _finite_number(value: Any) -> float | None:
  if type(value) is float:
    return value if math.isfinite(value) else None
  if isinstance(value, bool) or not isinstance(value, Real):
    return None
  try:
    result = float(value)
  except (TypeError, ValueError, OverflowError):
    return None
  return result if math.isfinite(result) else None


def _path(model_path: Any) -> tuple[np.ndarray, np.ndarray] | None:
  try:
    return _path_xy(model_path.x, model_path.y)
  except (AttributeError, TypeError, ValueError, OverflowError):
    return None


def _path_xy(xs: Any, ys: Any) -> tuple[np.ndarray, np.ndarray] | None:
  try:
    x = np.asarray(xs)
    y = np.asarray(ys)
  except (TypeError, ValueError, OverflowError):
    return None
  if x.ndim != 1 or y.ndim != 1 or len(x) < 2 or len(x) != len(y):
    return None
  if x.dtype.kind not in "fiu" or y.dtype.kind not in "fiu":
    return None
  x, y = x.astype(float), y.astype(float)
  if not np.isfinite(x).all() or not np.isfinite(y).all() or not np.all(np.diff(x) > 0):
    return None
  return x, y


def _at(path: tuple[np.ndarray, np.ndarray], distance: float) -> float | None:
  x, y = path
  if not x[0] <= distance <= x[-1]:
    return None
  return float(np.interp(distance, x, y))


def _paths_of(model: Any, _paths):
  if _paths is not None:
    return _paths[:4]
  try:
    std_path = _path_xy(model.position.x, model.position.yStd)
  except (AttributeError, TypeError, ValueError, OverflowError):
    std_path = None
  return _path(model.laneLines[1]), _path(model.laneLines[2]), _path(model.position), std_path


def _good_lines(model: Any) -> tuple[bool, bool] | None:
  lines = model.laneLines
  probs = model.laneLineProbs
  stds = model.laneLineStds
  if len(lines) < 3 or len(probs) < 3 or len(stds) < 3:
    return None
  good = []
  for i in (1, 2):
    prob = _finite_number(probs[i])
    std = _finite_number(stds[i])
    good.append(prob is not None and std is not None and MIN_LANE_PROB <= prob <= 1.0 and 0.0 <= std <= MAX_LANE_STD)
  return good[0], good[1]


def _toward(target_y: float, model_y: float, std_path, lookahead: float, authority: float) -> float | None:
  error = target_y - model_y
  error_abs = abs(error)
  error = math.copysign(max(0.0, error_abs - CENTER_ERROR_DEADBAND), error)
  # Reduce lane authority only when path variance establishes confidence.
  if std_path is not None:
    path_std = _at(std_path, lookahead)
    if path_std is not None and 0.0 <= path_std <= E2E_MAX_PATH_STD:
      break_in = clip_scalar((error_abs - E2E_BREAK_IN_START) /
                               (E2E_BREAK_IN_FULL - E2E_BREAK_IN_START), 0.0, 1.0)
      error *= 1.0 - clip_scalar(authority, 0.0, 1.0) * break_in
  correction = 2.0 * error / lookahead ** 2
  return correction if math.isfinite(correction) else None


def _inputs(speed_mps: float, offset_m: float, e2e_authority: float) -> tuple[float, float, float] | None:
  speed = _finite_number(speed_mps)
  offset = _finite_number(offset_m)
  authority = _finite_number(e2e_authority)
  if speed is None or offset is None or authority is None or speed < MIN_SPEED:
    return None
  return speed, offset, authority


def _two_lines(model: Any, speed_mps: float, offset_m: float, e2e_authority: float, _paths=None) -> tuple[float, float] | None:
  """(correction, lane width) with both inner lines good, else None."""
  inputs = _inputs(speed_mps, offset_m, e2e_authority)
  if inputs is None:
    return None
  speed, offset, authority = inputs
  try:
    if _good_lines(model) != (True, True):
      return None
    left_path, right_path, model_path, std_path = _paths_of(model, _paths)
    if left_path is None or right_path is None or model_path is None:
      return None
    lookahead = clip_scalar(speed, 8.0, 35.0)
    left, right, model_y = _at(left_path, lookahead), _at(right_path, lookahead), _at(model_path, lookahead)
    if left is None or right is None or model_y is None:
      return None
    width = right - left
    if not MIN_LANE_WIDTH <= width <= MAX_LANE_WIDTH:
      return None
    safe_offset = min(MAX_OFFSET, max(0.0, width * 0.5 - MIN_CENTER_TO_LINE))
    target_y = (left + right) * 0.5 + clip_scalar(offset, -safe_offset, safe_offset)
    correction = _toward(target_y, model_y, std_path, lookahead, authority)
    return None if correction is None else (correction, width)
  except (AttributeError, IndexError, TypeError, ValueError, OverflowError):
    return None


def raw_correction(model: Any, speed_mps: float, offset_m: float, e2e_authority: float, *, _paths=None) -> float | None:
  """Return a finite raw curvature correction, or None for unqualified model data."""
  both = _two_lines(model, speed_mps, offset_m, e2e_authority, _paths)
  return None if both is None else both[0]


def one_line_correction(model: Any, speed_mps: float, offset_m: float, e2e_authority: float, width_m: float,
                        *, _paths=None) -> tuple[float, int] | None:
  """With exactly one good inner line: (raw correction, -1 = the left line / +1 = the right line), else None.

  The target is that line +/- half of width_m. A confident road edge on the missing side keeps the target at
  least MIN_CENTER_TO_LINE from it. Off when the line peels away from the model path (an exit or a merge).
  """
  inputs = _inputs(speed_mps, offset_m, e2e_authority)
  width = _finite_number(width_m)
  if inputs is None or width is None or not MIN_LANE_WIDTH <= width <= MAX_LANE_WIDTH:
    return None
  speed, offset, authority = inputs
  try:
    good = _good_lines(model)
    if good is None or good[0] == good[1]:
      return None
    side = -1 if good[0] else 1
    left_path, right_path, model_path, std_path = _paths_of(model, _paths)
    line_path = left_path if side < 0 else right_path
    if line_path is None or model_path is None:
      return None
    lookahead = clip_scalar(speed, 8.0, 35.0)
    line, model_y = _at(line_path, lookahead), _at(model_path, lookahead)
    line_near, model_near = _at(line_path, LINE_NEAR_M), _at(model_path, LINE_NEAR_M)
    if line is None or model_y is None or line_near is None or model_near is None:
      return None
    # the line must be on its own side of us, and run with the model path
    if (model_y - line) * side >= 0.0 or (model_near - line_near) * side >= 0.0:
      return None
    if abs((model_y - line) - (model_near - line_near)) > MAX_LINE_DIVERGENCE:
      return None
    safe_offset = min(MAX_OFFSET, max(0.0, width * 0.5 - MIN_CENTER_TO_LINE))
    target_y = line - side * width * 0.5 + clip_scalar(offset, -safe_offset, safe_offset)
    # a confident road edge on the missing side
    edges, edge_stds = model.roadEdges, model.roadEdgeStds
    edge_index = 1 if side < 0 else 0
    if len(edges) > edge_index and len(edge_stds) > edge_index:
      edge_std = _finite_number(edge_stds[edge_index])
      edge_path = _path(edges[edge_index]) if edge_std is not None and 0.0 <= edge_std <= MAX_EDGE_STD else None
      edge = _at(edge_path, lookahead) if edge_path is not None else None
      if edge is not None and (edge - line) * -side > 0.0:
        limit = edge + side * MIN_CENTER_TO_LINE
        target_y = min(target_y, limit) if side < 0 else max(target_y, limit)
    if (target_y - line) * -side < MIN_CENTER_TO_LINE:
      return None   # no room between the line and the edge
    correction = _toward(target_y, model_y, std_path, lookahead, authority)
    return None if correction is None else (correction, side)
  except (AttributeError, IndexError, TypeError, ValueError, OverflowError):
    return None


def _reader_geometry_key(model):
  if not isinstance(model, capnp.lib.capnp._DynamicStructReader):
    return None
  try:
    return (tuple(model.laneLineProbs), tuple(model.laneLineStds),
            *((tuple(line.x), tuple(line.y)) for line in (model.laneLines[1], model.laneLines[2])),
            tuple(model.position.x), tuple(model.position.y), tuple(model.position.yStd))
  except (AttributeError, IndexError, TypeError, ValueError, OverflowError):
    return None


class LaneCenteringController:
  def __init__(self) -> None:
    self._correction = 0.0
    self._geometry_cache = None
    self._width: float | None = None   # lane width averaged while both lines were good
    self._since_two = 0.0              # meters driven since both lines were last good

  def reset(self) -> None:
    self._release()
    self._width = None
    self._since_two = 0.0

  def _release(self) -> None:
    """Drop the correction but keep the remembered lane width (a stop, an override, a lane change)."""
    self._correction = 0.0
    self._geometry_cache = None

  def _result(self, base: float, reason: str) -> LaneCenteringResult:
    correction = self._correction
    return LaneCenteringResult(base + correction, correction, (correction > 0) - (correction < 0), reason)

  def _fade(self, base: float, dt: float, reason: str) -> LaneCenteringResult:
    self._correction *= math.exp(-dt / RELEASE_TAU)
    if abs(self._correction) < 1e-12:
      self._correction = 0.0
    return self._result(base, reason)

  def update(self, observation: LaneCenteringInput) -> LaneCenteringResult:
    if not isinstance(observation, LaneCenteringInput):
      self.reset()
      return LaneCenteringResult(None, 0.0, 0, "invalid_input")
    base = _finite_number(observation.base_curvature)
    speed = _finite_number(observation.speed_mps)
    dt = _finite_number(observation.elapsed_seconds)
    settings = observation.settings
    offset = _finite_number(settings.offset_m) if isinstance(settings, LaneCenteringSettings) else None
    authority = _finite_number(settings.e2e_authority) if isinstance(settings, LaneCenteringSettings) else None
    strength = _finite_number(settings.strength) if isinstance(settings, LaneCenteringSettings) else None
    if (base is None or speed is None or dt is None or dt <= 0 or
        offset is None or authority is None or strength is None or not 0.5 <= strength <= STRENGTH_MAX or type(observation.model_sample_id) is not int or
        observation.model_sample_id < 0 or not isinstance(observation.mode, ControlMode) or
        type(observation.model_valid) is not bool or type(observation.lateral_active) is not bool or
        type(observation.turn_signal_active) is not bool or type(observation.driver_override) is not bool or
        type(observation.time_discontinuity) is not bool or
        type(settings.enabled) is not bool or type(settings.pause_on_signal) is not bool or
        type(settings.one_line) is not bool):
      self.reset()
      return LaneCenteringResult(base, 0.0, 0, "invalid_input")
    if observation.time_discontinuity:
      self.reset()
      return self._result(base, "time_discontinuity")
    if not observation.mode.lateral_authority or not settings.enabled or not observation.lateral_active or \
       not observation.model_valid:
      self.reset()
      return self._result(base, "inactive")
    if speed < MIN_SPEED:
      self._release()
      return self._result(base, "inactive")
    if observation.driver_override:
      self._release()
      return self._result(base, "driver_override")
    if settings.pause_on_signal and observation.turn_signal_active:
      return self._fade(base, dt, "signal_release")
    try:
      if observation.model.meta.laneChangeState != log.LaneChangeState.off:
        self._release()
        return self._result(base, "lane_change")
    except (AttributeError, TypeError, ValueError):
      self.reset()
      return self._result(base, "invalid_model")
    # Filtering runs per control tick, including repeated model samples.
    geometry = _reader_geometry_key(observation.model)
    cache_key = (observation.model_sample_id, geometry)
    cached = self._geometry_cache
    paths = None
    if geometry is not None:
      if cached is not None and cached[0] is observation.model and cached[1] == cache_key:
        paths = cached[2]
      else:
        paths = (_path_xy(*geometry[2]), _path_xy(*geometry[3]),
                 _path_xy(geometry[4], geometry[5]), _path_xy(geometry[4], geometry[6]))
        self._geometry_cache = (observation.model, cache_key, paths)
    else:
      self._geometry_cache = None
    driven = speed * dt
    both = _two_lines(observation.model, speed, offset, authority, paths)
    if both is not None:
      raw, width = both
      share, reason = 1.0, "qualified"
      blend = 1.0 if self._width is None else 1.0 - math.exp(-driven / WIDTH_AVERAGE_M)
      self._width = width if self._width is None else self._width + (width - self._width) * blend
      self._since_two = 0.0
    else:
      self._since_two += driven
      if not settings.one_line:
        return self._fade(base, dt, "unqualified_model")
      remembered = self._width is not None and self._since_two <= WIDTH_MEMORY_M
      width = self._width if remembered and self._width is not None else DEFAULT_LANE_WIDTH
      one = one_line_correction(observation.model, speed, offset, authority, width, _paths=paths)
      if one is None:
        return self._fade(base, dt, "unqualified_model")
      raw = one[0]
      share = ONE_LINE_STRENGTH if remembered else UNKNOWN_WIDTH_STRENGTH
      reason = "one_line_left" if one[1] < 0 else "one_line_right"
    if not math.isfinite(raw):
      return self._fade(base, dt, "unqualified_model")
    target = clip_scalar(raw, -0.004, 0.004) * 0.30
    if strength != 1.0:
      target = clip_scalar(target * strength, -MAX_CORRECTION, MAX_CORRECTION)
    target *= share
    self._correction += (target - self._correction) * (1.0 - math.exp(-dt / ACQUIRE_TAU))
    self._correction = clip_scalar(self._correction, -MAX_CORRECTION, MAX_CORRECTION)
    return self._result(base, reason)
