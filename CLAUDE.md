# Commits

- Every commit (including merges) is authored and committed as `tsk-go <cmc686@gmail.com>`. Before committing, run
  `git config user.name tsk-go && git config user.email cmc686@gmail.com`.
- Never mention Claude or Anthropic in commits: no `Co-Authored-By` trailer, no session links, no attribution lines.
- Every commit is signed with the owner's SSH signing key so GitHub shows it as Verified. The private key is in the
  environment variable `GIT_SIGNING_KEY_B64` (base64 of the OpenSSH private key file); its public key is on the tsk-go
  account as a Signing Key, fingerprint `SHA256:ituxS1NO/VJowXXhvOv/nUdnZQYSQkHbkSL4fQIDC2E`. Set it up once per session:
  ```
  mkdir -p ~/.ssh && chmod 700 ~/.ssh
  printf '%s' "$GIT_SIGNING_KEY_B64" | base64 -d > ~/.ssh/claude_signing && chmod 600 ~/.ssh/claude_signing
  ssh-keygen -y -f ~/.ssh/claude_signing > ~/.ssh/claude_signing.pub
  echo "cmc686@gmail.com $(cut -d' ' -f1,2 ~/.ssh/claude_signing.pub)" > ~/.ssh/allowed_signers
  git config gpg.format ssh && git config gpg.ssh.program ssh-keygen
  git config user.signingkey ~/.ssh/claude_signing.pub && git config gpg.ssh.allowedSignersFile ~/.ssh/allowed_signers
  git config commit.gpgsign true && git config tag.gpgsign true
  ```
  `gpg.ssh.program ssh-keygen` matters: the cloud environment's global git config signs with its own key
  (`/tmp/code-sign`), which GitHub shows as Unverified. Before every commit, check `ssh-keygen -lf
  ~/.ssh/claude_signing.pub` prints that fingerprint; after it, check `git log -1 --format=%GK` shows it too. If the
  key is missing or doesn't match, don't commit or push: stop and tell the owner (`ssh-keygen` comes from
  `apt-get install -y openssh-client` if it isn't installed).

# Syncing upstream

"Sync" means: merge https://github.com/firestar5683/StarPilot branch `SecretGoodStarPilot` into this repo's
`SecretGoodStarPilot_v2` with a merge commit (`git fetch https://github.com/firestar5683/StarPilot.git SecretGoodStarPilot
&& git merge --no-edit -m "Merge upstream StarPilot SecretGoodStarPilot" FETCH_HEAD`), then a normal push.
Never rebase or force-push for a sync: the local commits must be kept as they are. On a conflict, stop and ask.

# Panda firmware (ours, not upstream's)

This fork ships its own panda firmware: its Toyota safety lets through the 4th-gen Sienna's UDS door lock / unlock
frames (fork history 29). The app images in `panda/board/obj/*.bin.signed` (and `gitversion.h`, `version`) are built
from this repo's own source, not taken from upstream. The comma flashes whatever is in that folder at boot, so a sync
that lands upstream's images there silently removes the door lock.

- On a sync, if the merge touches `opendbc_repo/opendbc/safety/`, `panda/` or `panda/board/obj/`: never keep upstream's
  `*.bin.signed`. After the merge, rebuild the app images from the merged source and commit them:
  ```
  pip install --break-system-packages comma-deps-gcc-arm-none-eabi scons   # arm-none-eabi-gcc 13.2.1
  cd panda && PATH=$(python3 -c "import gcc_arm_none_eabi,os;print(os.path.dirname(gcc_arm_none_eabi.__file__))")/toolchain/bin:$PATH \
    PYTHONPATH=$PWD/../opendbc_repo:$PWD/.. scons -j8
  git checkout -- board/obj/bootstub.* board/obj/body_h7.bin.signed tests/libpanda/libpanda.so   # bootstubs stay
  ```
  Then commit `panda/board/obj/*.bin.signed`, `gitversion.h`, `version`. Don't change the bootstubs.
- Before committing, check the safety change is still in the merged source (`uds_door_start` in
  `opendbc_repo/opendbc/safety/modes/toyota.h`), and that `pytest opendbc/safety/tests/test_toyota.py -k uds_door`
  (from `opendbc_repo`) passes.
- The build is reproducible: rebuilding unchanged source gives the committed image except the version string and the
  signature. A diff bigger than that means the source isn't what was built.
- The comma four uses `panda_h7.bin.signed`.
After the merge, run `pytest openpilot/starpilot/system/starview/tests/test_galaxy_parity.py`. It fails when Galaxy
changed how its settings rows are presented (galaxy-setting-row.js, a new displayScale, new row fields). StarView draws
those rows natively, so tell the owner: the StarView app needs the same change (GalaxyRows.kt / GalaxySettingsView.kt);
record the new fingerprint in the test only after the app matches.

# Fork fixes to drop when upstream fixes them

After every sync, check whether upstream now fixes any of these on its own. If it does, remove our fix in a
normal commit (no revert of history, no force-push) and tell the owner which one was dropped:

1. **Chestnut big model compiles every start** (patches 14 and 16): `openpilot/starpilot/models/program_cache.py`,
   `load_profile.py`, and in `openpilot/selfdrive/modeld/modeld.py` `program_cache.*`, `load_profile.watch`,
   `BIG_MODEL_FIRST_TIMEOUT`, `BIG_MODEL_CACHED_TIMEOUT`. Upstream fixed = the big model's compiled programs survive a
   reboot by themselves (no `do_to_program` codegen at every start), or modeld's load timeout no longer cuts it off.
   Oct 21: upstream `ba6eac26` ("Fix Big Model Cold Startup") keeps its runtime cache on /data and waits 120 s; kept
   until a cold start's log shows that alone loads the big model in time.
2. **"Driving Model Lagging" right after the big model loads** (patch 22): `openpilot/starpilot/models/warmup.py` and in
   `openpilot/selfdrive/modeld/modeld.py` `big_warmup` (ChestnutLoading stays on until the big model runs steady).
   Upstream fixed = modeld itself waits for the big model's first real passes before clearing ChestnutLoading, or those
   first passes are no longer slow (no `chestnut.warmup` with slow passes / missed frames in the logs).
3. **A full update shows "failed" after its own reboot** (patch 29): in `openpilot/system/updated/updated.py`
   `FULL_UPDATE_REBOOT` and the first lines of `recover_fast_state`, plus `system/updated/tests/test_full_update_reboot.py`.
   normal_update's last stage is "rebooting" and the reboot installs it, but recover_fast_state turns every unfinished
   stage into "Update process restarted before completion". Upstream fixed = normal_update ends with stage "complete"
   (like fast_update does) or recover_fast_state accepts a full update's reboot.

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
15. RTK receiver on the hub (patch 25): `starview/rtk.py` reads a u-blox (ZED-F9R) for the tablet's GPS card (params "k")
    and writes the RTCM corrections the tablet fetches from an NTRIP caster (`rtk_rtcm`). Not used for localization.
16. RTK position for navigation (patch 27): `starview/rtk.py` `handoff_fix` / `_hand_off` write the receiver's fix (5 Hz,
    3D fix within 25 m only) to upstream's phone GPS handoff file (`starpilot/gps/phone.py`, /dev/shm). With Galaxy's
    default GPS source "backup", navigation, the comma's map, map speed limits and place search use it only while the
    comma's GPS and the car's have no fix (the comma's GPS can take minutes after a reboot with no internet). Galaxy
    then shows the source as "phone". If upstream's companion phone uplink is ever used too, both write the same file.
17. Route preview before the destination is set (patch 28): `starview/nav_link.py` `preview` / `go` (starviewd actions
    `nav_preview`, `nav_go`). Galaxy sets a destination at once; StarView 2.55 shows the routes and each one's directions
    first. preview asks Mapbox once from the tablet's origin, else the RTK/phone handoff fix, else the saved position;
    go sets the destination (a Mapbox search place stays temporary) and `state()` then chooses the offered route most
    like the one looked at (same "via", closest length/time), once.
18. RTK tools and the car's speed for the receiver (patch 31): `starview/rtk.py` `action` (starviewd action `rtk_action`:
    hot/warm/cold restart, reset the mount alignment, factory reset then our settings back to flash, save to flash,
    speed feed on/off), full ESF-STATUS and MON-VER in the status. The speed feed sends starviewd's carState vEgo as
    UBX-ESF-MEAS 10x a second (only while the tablet's carState stream is open: no new carState reader); its choice is
    in /data/starview/rtk.json and its CFG-SFODO settings go to the receiver's RAM only. RTCM goes out in whole frames
    so a UBX message never lands inside one. Output on UART1 / UART2 / I2C is switched off (nothing is wired there;
    UART1's backlog filled the receiver's send memory and it dropped ESF-STATUS on USB).
19. RTK calibration view (patch 32): `starview/rtk.py` `Calibration` (status "calibration": timeline of every change in
    the fusion's start-up with its time, turns left/right counted from NAV-PVT heading at >= 3 m/s and how many at
    >= 30 km/h, longest stop, time above 30 km/h, share of ESF-STATUS reports with "bad measurements" on the speed),
    ESF-ALG pitch/roll/errors. Speed feed: vEgoRaw on a fixed 0.1 s grid, CFG-SFODO-QUANT_ERROR left to the receiver.
20. RTK fix to the tablet 10x a second (patch 33): starviewd's data socket sends `rtk.Rtk.fast()` as a text frame
    {"type": "rtk", seq, lat, lon, hAccM, headingDeg, fixType, rtk, fusion...} on every new NAV-PVT (the params
    snapshot carries it once a second). For the tablet's lane locator and map arrow.
21. Tablet battery saver (patch 34): `starview/tablet_saver.py`, control action "tablet_saver" {"on", "force"} /
    {"status"}. Over the auto-tether adb pairing: other apps force-stopped, RUN_ANY_IN_BACKGROUND=ignore and the
    "restricted" standby bucket (user apps + a list of heavy preinstalled ones; never StarView, the keyboard, home,
    speech/voice services, Termius, /data/starview/saver_keep), Wi-Fi/BLE scanning off, StarView on the deviceidle
    allow list. The old values in /data/starview/tablet_saver.json are put back on "off". StarView itself is unchanged.
22. RTK mount kept (patch 35): `starview/rtk.py`. The fusion settings (CFG-SFCORE-USE_SF, CFG-SFIMU-AUTO_MNTALG_ENA,
    IMU_MNTALG_YAW/PITCH/ROLL) are no longer written at every connect: VALGET at connect, only what differs is written
    (RAM+BBR+flash). Once ESF-ALG says "fine" with steady angles for 2 min they go into flash with learning off and into
    /data/starview/rtk.json "mount"; realign / factory turn learning back on and forget them. status() "mountKept".
25. StarView's street map in Turn Signal Guidance (patch 38, redone at the Oct 23 sync on upstream's guidance):
    `starview/blinker_turn.py` (starviewd action `turn_intent` {side: left/right/none/null} -> /dev/shm/starview_turn,
    1.5 s old = no say), `navigation/intent.py` `TurnIntent.select(tablet=)` / `signal_desire(tablet=)`, modeld
    `starview_turn`. Upstream turns any blinker under 20 mph into a turn (Galaxy: Turn Signal Guidance, the on/off). With
    StarView's switch on and our street on its map, the tablet says whether there's a street to turn into on that side
    within 250 ft (OSM: not a one-way coming at us, not service): "none" -> no turn (pulling over). No say -> upstream.
26. Advice from StarView's New ideas (patch 39): `starview/advice.py` (starviewd action `advice` {cap, follow, offset,
    why} -> /dev/shm/starview_advice, read at most every 0.25 s, 1.5 s old = none). Only ever gentler: the planner's
    v_cruise lowered to `cap` (never below 10 mph, never raised; `longitudinal_planner.py` after the navigation ceiling),
    up to 0.6 s added to the follow time (`mpc_follow`), Lane Centering's offset shifted by up to 0.3 m
    (`lane_runtime.LaneCenteringHost.sample`). Everything that decides (speed bumps, potholes, cut-ins, lights...) runs
    on the tablet (StarView 2.67).
27. Big UI's cards on the tablet (patch 43): starviewd action `slc_action` {kind accept/reject/adopt, session, decision,
    presentation, speed} sends the same datagram as the car screen's speed-limit taps (`android_auto/projection_slc_action.py`
    SlcActionSender) to /tmp/starpilot-projection-slc.sock; the native UI checks it against the live slcState and
    publishes it. Only while started. Not imported from there (it pulls in the onroad UI); `SLC_ACTION_KINDS` /
    `SLC_ACTION_SOCKET` are checked against it by a test. UI_PARAMS_PERSISTENT also carries the PIPPreview* settings so the
    tablet draws Big UI's cabin-camera side views itself (StarView 2.74).
28. Log archive follows StarPilot 7's drive state (patch 44): `starview/logarchive.py` (copies finished drives to the
    EXTDATA USB stick while parked) read only `IsOnroad`, which 7.0 no longer sets, so it thought the car was always parked
    and a copy kept running into a drive, flooding the USB link the eGPU shares (Chestnut fell back). It now goes by
    `IsOffroad` (unknown = car on), stops within 1 MB when the car starts, and copies at most 20 MB/s.
    Patch 45: while a copy runs, its progress (phase, bytes and files done of total, MB/s, time left) is in
    `/dev/shm/starview_logarchive_progress.json` (RAM only); starviewd's `/storage` adds it as `stick.progress` (ignored
    once its pid is gone) and the auto copy's last start as `stick.auto_last`, for StarView's Storage page.

29. Door lock / unlock while running (patch 46): the 4th-gen Sienna's Main Body module (0x750, sub-address 0x40)
    refuses StarPilot's KWP door command (`7F 30 11`) and takes Toyota's UDS active test instead (GTS+ "Door Lock" DID
    2810, "Door Unlock" 2811). `opendbc/car/toyota/door_locks.py` `DoorLocks.manual` runs it over openpilot's own link:
    10 03 -> 0.1 s -> 2F 28xx 03 01 80 -> 1 s -> 2F 28xx 00 80 -> 0.1 s -> 10 01, only in Park, stopped, no gas,
    handing back at once if that changes. Panda safety (`opendbc/safety/modes/toyota.h`, the 0x750 block) allows
    those exact frames: the start frames behind the existing stationary gate, the hand-back frames always (relay OK).
    Trigger: `/dev/shm/starview_door_request` ("lock" / "unlock"), read by `selfdrive/car/card.py`
    `poll_door_request` every 50th frame; answer in `/dev/shm/starview_door_result`; starviewd action `door` for the
    tablet. Pausing pandad for the same test (TechStream's way) faulted the Sienna's cruise onroad, so never do that.
    Rebuilt panda firmware ships with it (see "Panda firmware"). Touches upstream card.py and door_locks.py: re-check
    after each sync. Confirmed on the car Oct 27 (both lock and unlock, every step answered positively).
    Patch 47: the answer-back - the horn (2F 2802) chirps once for lock, twice for unlock, inside the same session;
    the request can say "horn" (default), "none" or "buzzer" (the wireless buzzer 2F 284A is allowed too, but on the
    Sienna it ignores "return control" and sounds until the session ends). Panda safety allows those exact on frames
    behind the stationary gate and their off frames always. The answer goes back as soon as the doors move; card checks
    for a request 4x a second (20x while one runs).
    Patch 48: the answer is the car's own confirmation - while a request runs, card hands the Main Body module's
    replies on 0x758 to `DoorLocks.response`; its "done" (6F 28 1x 03) gives "lock: confirmed", a 7F gives "refused by
    the car (code xx)", none within 0.3 s gives "sent, no answer from the car". starviewd's `door` is ok only when
    confirmed.
30. StarLock, the phone's Lock / Unlock (patch 47): `starview/ble_door.py` advertises one Bluetooth LE GATT service
    (bluez over dbus-python, GLib loop via ctypes) only while openpilot is started; same pairing key and proofs as the
    tablet (pairing.py, peer "ble"), then starviewd's `door` action. The phone also tries Wi-Fi (starviewd /hello,
    /auth, `door` over /data) at the same time; whichever reaches the comma first does it. Off with
    /data/starview/no_ble_door. The app's source is in the StarView repo (module `starlock`).

**Fixes to upstream behaviour (drop when upstream fixes them; see the section above)**
12. Chestnut big model compiles every start (patches 14, 16): `starpilot/models/program_cache.py`, `load_profile.py`,
    modeld timeouts.
14. "Driving Model Lagging" seconds after the big model loads (patches 22, 24): `starpilot/models/warmup.py`; modeld keeps
    ChestnutLoading (no engaging, drops not counted) until 1 s of normal passes, at most 15 s.
18. A full update shows "failed" after its own reboot (patch 29): `system/updated/updated.py` `recover_fast_state`.

**No longer carried**
- Lane Centering with one line (patch 37, with StarView's one-line tile and blue lines): dropped by the owner at the Oct 26
  sync for upstream's own single-line tracking (firestar `d59a37d3` "Track single lane lines with smooth transitions and
  predicted clearance", `8a5fbf0b`, `35f62c3c`, `8807d791`). /data/starview/lane_one_line is no longer read.
- A route turn forgotten after a long stop (patch 36: turn desire pulsed again every 5 s, stop latch let go after
  pulling away): reverted by the owner at the Oct 23 sync, when upstream added Turn Signal Guidance (`navigation/intent.py`
  `signal_desire`); patch 38 now sits on upstream's TurnIntent as it is.
- AOL on the SecOC Sienna (patch 6): merged upstream (firestar `79fdeb4`, rebuilt panda/pandad `337bb0754`).
- Waze bridge and split screen (patch 3): replaced by the in-app map (patch 9).
- Hash the big model file while modeld waits (patch 17): written, then skipped by the owner.
- Updates refused offroad + parked with the ignition on (patch 20): fixed upstream ("Allow Forced Offroad Updates",
  firestar `defaf64c`: an update forced offroad no longer needs live carState/selfdriveState); `park_marker.py` removed.
- steerlearnerd memory on long drives (patch 26, never pushed): fixed upstream ("Bound FLM replay memory", firestar
  `0b01007a`, which also restarts steerlearnerd when it exits).
