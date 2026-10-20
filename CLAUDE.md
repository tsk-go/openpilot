# Commits

- Every commit (including merges) is authored and committed as `tsk-go <cmc686@gmail.com>`. Before committing, run
  `git config user.name tsk-go && git config user.email cmc686@gmail.com`.
- Never mention Claude or Anthropic in commits: no `Co-Authored-By` trailer, no session links, no attribution lines.

# Syncing upstream

"Sync" means: merge https://github.com/firestar5683/StarPilot branch `SecretGoodStarPilot` into this repo's
`SecretGoodStarPilot_v2` with a merge commit (`git fetch https://github.com/firestar5683/StarPilot.git SecretGoodStarPilot
&& git merge --no-edit -m "Merge upstream StarPilot SecretGoodStarPilot" FETCH_HEAD`), then a normal push.
Never rebase or force-push for a sync: the local commits must be kept as they are. On a conflict, stop and ask.

# Fork fixes to drop when upstream fixes them

After every sync, check whether upstream now fixes any of these on its own. If it does, remove our fix in a
normal commit (no revert of history, no force-push) and tell the owner which one was dropped:

1. **Chestnut big model compiles every start** (patches 14 and 16): `openpilot/starpilot/models/program_cache.py`,
   `load_profile.py`, and in `openpilot/selfdrive/modeld/modeld.py` `program_cache.*`, `load_profile.watch`,
   `BIG_MODEL_FIRST_TIMEOUT`, `BIG_MODEL_CACHED_TIMEOUT`. Upstream fixed = the big model's compiled programs survive a
   reboot by themselves (no `do_to_program` codegen at every start), or modeld's load timeout no longer cuts it off.
2. **Galaxy updates refused with the ignition on, offroad and parked**: `openpilot/starpilot/drive_state/park_marker.py`,
   `status(parked_marker=...)` in `openpilot/starpilot/drive_state/evidence.py`, and the `ParkMarker` lines in
   `openpilot/selfdrive/car/card.py`. Upstream fixed = `PhysicalSource.update_status` can allow an update offroad with
   the ignition on (it no longer needs live carState/selfdriveState, which stop offroad).
3. **"Driving Model Lagging" right after the big model loads** (patch 22): `openpilot/starpilot/models/warmup.py` and in
   `openpilot/selfdrive/modeld/modeld.py` `big_warmup` (ChestnutLoading stays on until the big model runs steady).
   Upstream fixed = modeld itself waits for the big model's first real passes before clearing ChestnutLoading, or those
   first passes are no longer slow (no `chestnut.warmup` with slow passes / missed frames in the logs).

# Fork history

Everything this fork changes on top of upstream StarPilot, and why. Keep it current: every new patch adds a line here
in the same commit; a patch that is dropped (merged upstream, fixed upstream, abandoned) moves to "No longer carried".
Paths are under `openpilot/` unless noted.

**StarView (the tablet UI; stays, upstream won't replace it)**
1. StarView bridge: `starpilot/system/starview/` (starviewd, pairing, log archive, external storage, TechStream). Its
   `compat.py` keeps the tablet's wire format working on 7.0.
2. Automatic blinker: `starview/blinker_signal.py`; `selfdrive/controls/lib/desire_helper.py` (`starview_lane`,
   `starview_evidence`: a lane change confirmed on the tablet starts without a nudge) and the wiring in
   `selfdrive/modeld/modeld.py`.
3. Tablet mode + terminal pairing: `starview/tablet_mode.py` hooked into `selfdrive/ui/ui.py`; `starview/pair.py`.
4. One local Galaxy session: `starview/galaxy_local.py` reuses its cookie (Galaxy keeps 64 sessions).
5. Drive replay: `starview/replay.py` + starviewd hooks.
6. Replay fixes and 7.0 cards (patch 8).
7. In-app navigation, Waze removed (patches 9-12): `starview/nav_link.py`; `starpilot/navigation/` owner, runtime,
   route_engine, mapbox_budget (alternatives, traffic refresh, lanes, spoken directions, place search, saved places);
   `navigation/relay.py` sends Mapbox requests through the tablet when the comma has no internet.
8. GPU icon state + quiet mode while the big model loads (patch 13): starviewd `ChestnutState`, `gpu_quiet_tick`.
9. Satellite reports for the tablet's GPS card (patch 15): `starview/compat.py` passes only `ubloxGnss.satReport`.
10. Lane-change nudge strength from the tablet (patch 18): `starview/nudge.py`, `desire_helper.py` `nudge_torque`,
    modeld `NudgeSetting` (Toyota only; no file = stock rule).
11. Update from the tablet on 7.0 (patches 19, 23): starviewd `software_status` / `software_fast` (7.0's software owner;
    action "update" like Galaxy's Update button: fast when allowed, else the full update).

**Fixes to upstream behaviour (drop when upstream fixes them; see the section above)**
12. Chestnut big model compiles every start (patches 14, 16): `starpilot/models/program_cache.py`, `load_profile.py`,
    modeld timeouts.
13. Updates refused offroad + parked with the ignition on (patch 20): `starpilot/drive_state/park_marker.py`,
    `evidence.py` `parked_marker`, card's `ParkMarker`.
14. "Driving Model Lagging" seconds after the big model loads (patch 22): `starpilot/models/warmup.py`; modeld keeps
    ChestnutLoading (no engaging, drops not counted) until 1 s of normal passes, at most 15 s.

**No longer carried**
- AOL on the SecOC Sienna (patch 6): merged upstream (firestar `79fdeb4`, rebuilt panda/pandad `337bb0754`).
- Waze bridge and split screen (patch 3): replaced by the in-app map (patch 9).
- Hash the big model file while modeld waits (patch 17): written, then skipped by the owner.
