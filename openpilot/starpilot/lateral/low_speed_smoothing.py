"""Low Speed Smoothing (tsk-go fork, 4th-gen Sienna): calms the steering wheel's back-and-forth in stop-and-go.

Recorded Nov 16 (8 wobbles in 7 minutes of stop-and-go, all at 3 - 11 mph): the wheel swung about 12 degrees each way
every 2 s. A loop between the driving model and the steering: the model asks for a small correction, the Sienna's
steering command may only grow so fast (Toyota's torque rate limit, 1500 units per second up, enforced by the panda) - in
the wobbles it sat on that limit 85 % of the time - so the wheel moved about 0.6 s late and overshot; the model saw the
van swing and asked the other way 0.3 s later. Only at low speed, because the model asks for the same small sideways
push at every speed (about 0.01 m/s2 when calm) and the curvature for it grows as 1 / speed squared: calm, the wheel
already jitters about 1 degree at 5 - 10 mph against 0.3 at 15 - 20 mph. comma raised the floor of that division to
2.5 m/s (#39182, under 5.6 mph); this halves the model's small corrections below 10 mph, back to full by 15 mph, which
halves the loop. Corrections sharper than a 270 ft radius bend (0.012 / m: every turn at an intersection) pass untouched,
and nothing changes with a blinker on or during a lane change.

The switch is Galaxy's "Low Speed Smoothing" (Driving controls, under Highway Smoothing), default On. It isn't a param
(the comma's param list is compiled in): Off is the file /data/starview/low_speed_smoothing_off. controlsd looks at it
once a second from a thread of its own, and a change fades in over half a second.
"""
import math
import os
import threading

from openpilot.common.constants import CV
from openpilot.common.realtime import DT_CTRL

KEY = "starview:low_speed_smoothing"
LABEL = "Low Speed Smoothing"
REASON = ("Halves small steering corrections below about 10 mph, back to full by 15 mph, so the wheel doesn't wobble " +
          "in stop-and-go. Turns, the blinker and lane changes are untouched. Takes effect within a second.")
OFF_FILE = "/data/starview/low_speed_smoothing_off"
FINGERPRINTS = ("TOYOTA_SIENNA_4TH_GEN",)

FULL_SPEED = 10 * CV.MPH_TO_MS     # the corrections halved up to here
NONE_SPEED = 15 * CV.MPH_TO_MS     # and untouched from here
GAIN = 0.5
SMALL = 0.004                      # 1/m: a correction this small is halved in full (an 820 ft radius)
LARGE = 0.012                      # 1/m: and from here untouched (a 270 ft radius; intersection turns are 0.05 - 0.15)
RAMP_S = 0.5
INTERVAL_S = 1.0


def supported(cp) -> bool:
  try:
    return (str(cp.carFingerprint) in FINGERPRINTS and str(cp.steerControlType).split(".")[-1] == "torque" and
            not cp.notCar and not cp.passive and not cp.dashcamOnly)
  except AttributeError:
    return False


def switched_on(path: str | None = None) -> bool:
  return not os.path.exists(path or OFF_FILE)


def factor(curvature: float, v_ego: float) -> float:
  """What the model's curvature is multiplied by: GAIN for small corrections at crawl speed, 1 for turns and above 15 mph.
  curvature x factor rises with curvature (no correction ever comes out smaller than a smaller one would)."""
  if not (math.isfinite(curvature) and math.isfinite(v_ego)) or v_ego >= NONE_SPEED:
    return 1.0
  speed = 1.0 - min(max((v_ego - FULL_SPEED) / (NONE_SPEED - FULL_SPEED), 0.0), 1.0)
  size = 1.0 - min(max((abs(curvature) - SMALL) / (LARGE - SMALL), 0.0), 1.0)
  return 1.0 - (1.0 - GAIN) * speed * size


class LowSpeedSmoothing:
  def __init__(self, cp, *, live: bool = True, path: str | None = None):
    self.supported = supported(cp)
    self.path = path or OFF_FILE
    self.on = self.supported and switched_on(self.path)
    self.amount = 1.0 if self.on else 0.0
    self.last_factor = 1.0
    self._stop = threading.Event()
    self._thread = None
    if self.supported and live:
      self._thread = threading.Thread(target=self._run, name="low-speed-smoothing", daemon=True)
      self._thread.start()

  def _run(self):
    while not self._stop.wait(INTERVAL_S):
      try:
        self.on = switched_on(self.path)
      except OSError:
        pass

  def close(self):
    self._stop.set()

  def update(self, curvature: float, v_ego: float, *, active: bool, blinker: bool, lane_change: bool) -> float:
    """Every control frame with the model's curvature; returns the one to steer by."""
    if not self.supported:
      return curvature
    target = 1.0 if (self.on and active and not blinker and not lane_change) else 0.0
    step = DT_CTRL / RAMP_S
    self.amount = min(self.amount + step, target) if self.amount < target else max(self.amount - step, target)
    self.last_factor = 1.0 - (1.0 - factor(curvature, v_ego)) * self.amount
    return curvature * self.last_factor if active else curvature


def controls_curvature(controls, curvature: float, CS, CC, model_v2) -> float:
  """controlsd's hook, right after it takes the model's desiredCurvature. Controls made without __init__ (some
  upstream tests) have no smoothing: the curvature as it is."""
  owner = getattr(controls, "low_speed_smoothing", None)
  if owner is None:
    return curvature
  from openpilot.cereal import log   # controlsd has it loaded
  return owner.update(curvature, CS.vEgo, active=CC.latActive, blinker=bool(CS.leftBlinker or CS.rightBlinker),
                      lane_change=model_v2.meta.laneChangeState != log.LaneChangeState.off)


# --- Galaxy's switch (feature_settings_owner: TORQUE page row, and its apply for KEY) ---

def _capability(owner):
  from openpilot.starpilot.feature_capabilities import lateral_supported   # steering at all (the SecOC key, safety)
  cp = owner.vehicle_params()
  if cp is None or not supported(cp) or not lateral_supported(cp):
    return None
  return (str(cp.carFingerprint), str(cp.steerControlType), KEY)


def rows(owner, configurable: bool) -> tuple:
  from openpilot.starpilot.ui.feature_settings_state import FeatureRow
  capability = _capability(owner)
  if capability is None:
    return ()
  try:
    on = switched_on()
  except OSError:
    on = True
  return (FeatureRow(KEY, LABEL, "On" if on else "Off", b"1" if on else b"0", ("Off", "On"),
                     available=bool(configurable and owner.authority("torque")), default_value="On",
                     vehicle_fingerprint=owner.vehicle_fingerprint(), capability=capability,
                     reason=REASON if configurable else "Unavailable with the current vehicle or feature settings"),)


def apply(owner, request) -> bool:
  current = rows(owner, owner.authority("preferences"))
  if (not current or request.key != KEY or request.value not in ("Off", "On") or not current[0].available or
      request.expected != current[0].source or request.vehicle_fingerprint != owner.vehicle_fingerprint() or
      request.capability != current[0].capability or request.related_source is not None or request.dependencies or
      request.display_unit or request.direction):
    return False
  try:
    path = OFF_FILE
    if request.value == "On":
      if os.path.exists(path):
        os.unlink(path)
    else:
      os.makedirs(os.path.dirname(path), exist_ok=True)
      with open(path + ".tmp", "w") as f:
        f.write("off\n")
      os.replace(path + ".tmp", path)
  except OSError:
    return False
  return switched_on() == (request.value == "On")
