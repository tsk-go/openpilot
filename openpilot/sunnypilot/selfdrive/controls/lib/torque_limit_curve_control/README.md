# Torque Limit Curve Control (TLCC)

Slows the car before a curve **only** when the steering system physically cannot
deliver the lateral acceleration the upcoming path requires. There are no comfort
constants: the single limit enforced is the car's own lateral-acceleration ceiling,
i.e. the point where the lateral controller saturates and openpilot raises
*"Turn Exceeds Steering Limit"*.

TLCC is fully independent of Smart Cruise Control (SCC-V / SCC-M). It is a
separate `LongitudinalPlanSource` (`torqueLimitCurve`) and the planner simply
takes the lowest speed target among all sources, as it already does.

## Why

SCC-V targets a fixed `2.0 m/s²` of lateral acceleration. Many cars cannot steer
that hard (Toyota Sienna: `latAccelFactor = 1.69`, measured max ≈ `1.32`), so SCC-V
slows to a speed the EPS still can't handle — and you get a takeover anyway. Other
cars can steer much harder (Genesis G70: `3.85`) and get slowed for nothing.

## How

### 1. Learn the ceiling (`lat_limit_learner.py`)

| Evidence | Meaning |
|---|---|
| `controlsState.lateralControlState.torqueState.saturated` | the measured `actualLateralAccel` at that moment **is** the ceiling |
| lateral accel sustained ≥ 0.5 s *without* saturating | proof the ceiling is at least that high |
| `lateralTorqueParameters` (live `torqued` estimate) | prior: `latAccelFactor × (1 − friction)` |

Saturation samples are filtered slowly (≈ 20 s of saturated driving to converge)
and the estimate blends from the prior to the learned value as evidence accumulates
(fully trusted after 10 s of saturation). The result is cached per car fingerprint in
`TorqueLimitCurveControlCache`.

For angle/curvature-controlled cars the prior is the ISO 11270 limit the car
interface enforces.

### 2. Decide how much to slow, and when (`controller.py`)

For every point `i` of the model's path plan (`modelV2.position / velocity /
orientationRate`, 10 s horizon):

```
kappa_i = |yaw_rate_i| / v_i                           path curvature at that point
v_req_i = sqrt(a_lat_usable / kappa_i)                 fastest speed the steering can take it
a_req_i = (v_ego² − v_req_i²) / (2 · d_i)              constant decel needed to get there in time
```

`a_lat_usable = 0.9 × ceiling` (the PID needs headroom to actually track the path).
`d_i` is reduced by `v_ego × 0.5 s` to compensate the planner's jerk-limited response,
and floored at `v_ego × 1.5 s`: when the limiting point is already under the car, the
excess speed is bled off over 1.5 s rather than treated as an emergency.
Current road roll is applied only within 3 s and only when it *hurts* (bank against
the turn); it is never used to relax the limit.

The most demanding point wins:

* `a_req < 0.8 m/s²` → **nothing happens**. The car can make the curve, or it's
  far enough that no action is needed yet.
* `a_req ≥ 0.8` → **braking**: request exactly `a_req` (capped at `1.2`, the most the
  planner's cruise path delivers).
* `a_req > 1.2` → **limited**: even max braking won't make it; the steering limit
  will be exceeded unless the driver intervenes. (Reported in `longitudinalPlanSP`
  for a future alert.)
* released when `a_req < 0.3` or once below the curve speed.

The request is passed as `v_target = v_ego + a_target`, because the planner's cruise
path computes `target_accel = clip(v_cruise − v_ego, −1.2, …)`; it is never allowed
below the speed the curve itself permits.

## Telemetry

`longitudinalPlanSP.torqueLimitCurveControl` carries the state, targets, the learned
ceiling, the usable limit, the lateral accel the path ahead needs at the current
speed, the limiting point's speed and distance, the required decel and how much
saturation evidence the learner has.

## Toggle

`TorqueLimitCurveControl` — Settings → Cruise → *Torque Limit Curve Control (Alpha)*,
also exposed through the sunnylink settings UI.
