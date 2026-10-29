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

"Sync" means: merge https://github.com/StarPilotHQ/StarPilot branch `Dom` into this repo's `Dom` with a merge commit
(`git fetch https://github.com/StarPilotHQ/StarPilot.git Dom && git merge --no-edit -m "Merge upstream StarPilot Dom"
FETCH_HEAD`), then a normal push. firestar's repo moved from firestar5683/StarPilot to StarPilotHQ/StarPilot (the old
address still redirects). Oct 29: firestar folded `SecretGoodStarPilot` into `Dom` and deleted it, so this repo's
`Dom` branch was started from `SecretGoodStarPilot_v2` (all our patches through 57) and syncs from `Dom` now;
`SecretGoodStarPilot_v2` and `SecretGoodStarPilot_v2-pre-oct26` are kept as they were and no longer synced.

The repo: since Oct 29 tsk-go/openpilot is a fork in firestar's network (the old sunnypilot-network repo is kept as
tsk-go/openpilot-sunnypilot-old). That matters for Git LFS: a push must not reference LFS files the network lacks,
and the sunnypilot network's LFS budget was used up; in firestar's network every LFS file of his history is already
there, so syncs push without uploading any.
Never rebase or force-push for a sync: the local commits must be kept as they are. On a conflict, stop and ask.

# Panda firmware (ours, not upstream's)

This fork ships its own panda firmware: its Toyota safety lets through the 4th-gen Sienna's UDS door lock / unlock
frames (fork history 29) and StarLock's lock-state reads (fork history 33). The app images in `panda/board/obj/*.bin.signed` (and `gitversion.h`, `version`) are built
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
   until a cold start's log shows that alone loads the big model in time. Oct 29 (Dom sync): upstream `6effaaa3`
   ("Accelerate Chestnut model loading") only pins the loader thread to core 7 - kept ours beside it.
2. **"Driving Model Lagging" right after the big model loads** (patch 22): `openpilot/starpilot/models/warmup.py` and in
   `openpilot/selfdrive/modeld/modeld.py` `big_warmup` (ChestnutLoading stays on until the big model runs steady).
   Upstream fixed = modeld itself waits for the big model's first real passes before clearing ChestnutLoading, or those
   first passes are no longer slow (no `chestnut.warmup` with slow passes / missed frames in the logs).
3. **A full update shows "failed" after its own reboot** (patch 29): in `openpilot/system/updated/updated.py`
   `FULL_UPDATE_REBOOT` and the first lines of `recover_fast_state`, plus `system/updated/tests/test_full_update_reboot.py`.
   normal_update's last stage is "rebooting" and the reboot installs it, but recover_fast_state turns every unfinished
   stage into "Update process restarted before completion". Upstream fixed = normal_update ends with stage "complete"
   (like fast_update does) or recover_fast_state accepts a full update's reboot.
4. **The comma four restarts all night once it shut down while parked** (patch 50): in
   `openpilot/system/hardware/power_monitoring.py` `PARKED_OFF_MARKER`, `PARKED_RESTART_SHUTDOWN_S`, `mark_parked_off`,
   `clear_parked_off` and the `quick` lines of `should_shutdown`; in `hardwared.py` the two calls; the
   `test_parked_restart_shuts_down_quickly` test. After a parked shutdown the panda's deep sleep wakes on the car's CAN,
   resets and bootkicks (board init sets BOOT_BOOTKICK), and every such start stayed on for MIN_ON_TIME_S (an hour) on a
   battery already below the cutoff - 14 restarts in one night (Oct 27). Upstream fixed = a parked wake no longer stays
   up an hour (the panda stops bootkicking without ignition, or the minimum on time doesn't apply after a parked
   shutdown). Oct 29 (Dom sync): upstream `2567a32f` re-applies the panda's power-save CAN interrupt state after a CAN
   re-init (a CAN wake may have come from that); kept ours until a parked night shows no restarts without it.

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
    presentation, speed} sends the same datagram as the car screen's speed-limit taps (`starport/projection_slc_action.py`
    SlcActionSender; the folder was android_auto/ until upstream renamed it Oct 28) to /tmp/starpilot-projection-slc.sock; the native UI checks it against the live slcState and
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
    Patch 49: StarLock's own horn pattern - `door` takes optional `beeps` [n 1-5, ms on 30-1000, ms between 50-1000] (a
    list so the BLE request stays inside one 244-byte write; BLE passes it through); starviewd writes it to card as frames ("unlock horn 3x15x30"). `schedule` places one output per
    frame (a clash moves to the next free frame), adds tester present (40 02 3E 00, already a return frame) every 1.5 s
    in a long pattern, and ends the session 0.1 s after the last beep. No firmware change.
30. StarLock, the phone's Lock / Unlock (patch 47): `starview/ble_door.py` advertises one Bluetooth LE GATT service
    (bluez over dbus-python, GLib loop via ctypes) only while openpilot is started; same pairing key and proofs as the
    tablet (pairing.py, peer "ble"), then starviewd's `door` action. The phone also tries Wi-Fi (starviewd /hello,
    /auth, `door` over /data) at the same time; whichever reaches the comma first does it. Off with
    /data/starview/no_ble_door. The app's source is in the StarView repo (module `starlock`).
32. StarLock auto-lock / auto-unlock (patch 51): `starview/autolock.py`. card publishes the driver's door (Toyota
    `CarState.driver_door_open` from BODY_CONTROL_STATE DOOR_OPEN_FL), any door and Park to /dev/shm/starview_driver_door
    only on a change, with a count of driver's-door closes. A close in Park with the phone connected arms it for 60 s;
    the comma's own reading of the phone (`sudo -n btmgmt con` / `conn-info`, 2x a second while armed) below the lock
    line, or the phone dropping off, locks through `door`. Auto-unlock (optional, only after an auto-lock, within
    unlock_min): the phone must go below the walk-away line first, then come back above the unlock line. Any door opening
    or leaving Park disarms. Settings in /data/starview/autolock.json (StarLock writes them: BLE op `autolock` with the
    pairing proof, or starviewd action `autolock`); live reading: BLE op `rssi` / action `autolock_rssi`. Idle cost: two
    stat() calls every 0.5 s while started.
    Patch 52: ble_door sends the registration paths as dbus.ObjectPath. Untyped, dbus-python only sent "o" when its
    introspection of hci0 had finished; on some boots it hadn't, and bluez refused every registration ('Method
    "RegisterApplication" with signature "sa{sv}" ... doesn't exist'), so the phone connected and found no service.
    The proxies are also made fresh per call and it registers again when org.bluez changes owner (a bluetoothd
    restart). starviewd stops within 2 s (aiohttp shutdown_timeout) so the watcher's restart doesn't fall back.
    Also: btmgmt gets a stdin pipe held open (under the service stdin is /dev/null and btmgmt quit before printing, so
    every reading was None), and StarLock's live reading (BLE op `rssi`, action `autolock_rssi`) answers from the last
    reading while a fresh one is taken in the background - btmgmt never runs inside the Bluetooth callback.
    Also: auto-lock tells StarLock what it did (`ble_door.announce`: {"op":"auto","cmd","ok","done","result"} pushed
    on the TX characteristic, queued from any thread and sent from the Bluetooth loop via g_idle_add), and StarLock
    sends its current answer-back and horn patterns (`autolock` set) whenever they change and on every connect.
33. StarLock's real lock state and hold-to-close windows (patch 53).
    Lock state: on the 4th-gen Sienna (`DoorLocks.read_locks`, set by the Toyota CarController for
    TOYOTA_SIENNA_4TH_GEN) `door_locks.py` reads the Main Body module every 2 s - UDS 22 101A (driver), 1019
    (passenger), 101B / 101C (sliding doors), 101E (back door), one request per frame, default session, 00 = locked /
    01 = unlocked (found on the car Oct 28) - never while a lock / unlock runs, and 0.5 s after one ends; a lock /
    unlock asked right after a read waits 50 ms for its reply. card hands it
    the 0x758 replies only while `DoorLocks.listening` (a request running, or 0.3 s after a burst) and writes
    /dev/shm/starview_locks on a change (and once at start, all unknown, so a drive never shows the last one's). Panda safety allows those five exact read frames like the return frames
    (rebuilt firmware). starviewd `lock_state` / action `locks`; BLE op `locks`, and `locks_watch` pushes
    {"op":"locks","d":{dr,pa,s1,s2,bk: L/U/?},"live"} to StarLock on every change (one stat() a second).
    Windows: relay 3 of the Pico relay box (GP4 -> IN3, COM3 / NO3 across the driver's door key switch, lock side) is
    the key held to lock - with the car off the Sienna closes every window and the sunroof with its own anti-pinch (and
    locks). The Pico program (`starpilot/tools/pico/main.py`, loaded with `pico/load.py`) takes 'W' for it; latched
    blinkers no longer close relay 3. `PicoBlinker.window` holds it while asked (1.2 s keep); starviewd `window_close`
    (action `window` {hold}) refuses while openpilot is started; BLE op `window`: the first request carries the
    pairing proof and gets a key, the 250 ms keep-alives only the key, `stop` always works. StarLock's Bluetooth now
    stays up for 30 min after the car turns off (`Hub.ble_wanted`), and starviewd follows deviceState.started in its
    1 s openpilot check too - before, `started` only updated while a tablet was connected, so StarLock's Bluetooth,
    auto-lock and lock / unlock depended on the tablet. `blink.py window [SECS]` holds relay 3 by hand.
34. Comma offline mode and the download door (patch 54): `starpilot/system/starview/offline.py` (standard library only).
    The comma's kernel has no nf_tables, so it's policy routing: rule 9000 lets GitHub's ranges (updates) and Amazon
    CloudFront's (Mapbox: maps, routes, live traffic - refreshed from ip-ranges.amazonaws.com at "on", saved in
    /data/starview/offline_cloudfront) use the normal routes, 9050 the download door, 9100 every non-default route
    (USB tablet, hotspot, Wi-Fi's own network), 9200 everything else unreachable; IPv6 the same or switched off.
    /data/starview/offline remembers it; the sv-offline boot service (`offline.py install`, runs this file before
    openpilot) puts it back. starviewd action `offline` {on} (installs the service), `offline_door` {close} /
    {autoClose}, and a 30 s `offline_tick` (closes a door held too long; car off, puts back a missing or old boot
    service - AGNOS updates remove it). The door: the model manager (`_work`) and sound downloads (`_run`) run inside
    `offline.download_door`, and their default opener is `offline.urlopen` - with offline mode on, Hugging Face
    (huggingface.co redirects every file to rotating plain-Amazon us.aws.cdn.hf.co) is let through at its current
    addresses before every request, after every redirect and every 20 s while a download runs; after the last one it
    closes, or with "close after downloads" off (/data/starview/offline_door.json) stays open until "Close now" or 1 h.
    State in /dev/shm/starview_offline_door.json (jobs by pid, monotonic times). Nothing runs without a download.
35. Doors & belts (patch 55): `starpilot/system/starview/doorbelt.py`. Every door and seat-belt switch, checked after
    each drive from that drive's rlogs - nothing extra runs while driving. Standard bits: BODY_CONTROL_STATE 0x620 bus
    0 (driver's / passenger / both sliding doors, driver's belt). The rest come from the tablet's Learn (car on, in
    Park): `CanWatch` reads the "can" socket only while the tablet asks, keeps bit changes (counters dropped after 40
    changes), and per switch picks the bit that changed at least twice inside its step and more there than everywhere
    else (so the dome light and "a door is open" drop out); saved in /data/starview/doorbelt/bits.json, learned wins.
    starviewd `doorbelt_thread`: car off and new finished segments (last 7 days) -> `python3 -m ...doorbelt scan` at
    nice 19 / ionice idle; the rlog is streamed (capnp framing by hand, a few MB), stops when the car turns on, and
    writes events.jsonl (time, speed, fast = within 3 s of the last change, moving); scanned.json holds the read
    segments, per-drive lines (also when nothing changed) and the events file's size, saved after every segment, so a
    killed scan never repeats a change (flock: one scan at a time). A new Learn starts the history over. Learn's
    "elsewhere" counts only the other steps and the first 5 s (walking through a door between steps is fine); "Again"
    forgets the earlier try. Action `doorbelt` {op: status | live |
    begin | start | done | skip | save | cancel}; live and Learn need the car on in Park, standing still.
    Patch 57: change times come from the `clocks` messages (the latest before each change, carried across segments);
    loggerd writes the route's first initData into every segment, so a clock set mid-drive left a whole drive on the
    old time and the list out of order. The tablet's list is sorted by time; SCAN_VERSION in the state key makes a
    new version read the last week again.
36. The clock in offline mode (patch 56): offline mode blocked the time servers, so parked without a GPS fix the clock
    fell months behind (Oct 29: July 28) and every TLS connection failed ("certificate is not yet valid": updates,
    Mapbox). `offline.py`: rule 9030 lets the time servers through - what `timedatectl show-timesync` lists plus
    TIME_HOSTS, and Google's / Cloudflare's fixed anycast addresses (TIME4, also at boot) - NTP only (`ipproto udp
    dport 123`; a kernel that refuses that gets the whole address); timesyncd is restarted when it isn't synced yet.
    `clock_fix` sets the clock from GitHub's Date header (read without the certificate check) when it's > 60 s off.
    starviewd `offline_tick` runs both in a thread of its own every 30 min (1 min after a failure, 5 min while the car
    is on; the clock only with the car off - driving, GPS sets it). `offline.py clock` does it by hand.
37. Car on keeps the tablet where it was (patch 59): starviewd's `tablet_power_thread` woke the tablet and ran `am start`
    of StarView's MainActivity at every ignition on. MainActivity is singleTask, so that closed every StarView screen
    above it (Settings, Doors & belts...) even with the tablet on and showing StarView. `_tablet_wake` now asks
    `dumpsys window` which app is in front (mFocusedApp, then mCurrentFocus) and starts StarView only when it isn't.

**Fixes to upstream behaviour (drop when upstream fixes them; see the section above)**
12. Chestnut big model compiles every start (patches 14, 16): `starpilot/models/program_cache.py`, `load_profile.py`,
    modeld timeouts.
14. "Driving Model Lagging" seconds after the big model loads (patches 22, 24): `starpilot/models/warmup.py`; modeld keeps
    ChestnutLoading (no engaging, drops not counted) until 1 s of normal passes, at most 15 s.
18. A full update shows "failed" after its own reboot (patch 29): `system/updated/updated.py` `recover_fast_state`.
31. The comma four restarts all night after a parked shutdown (patch 50): a marker in /data/starview from the parked
    shutdown makes a CAN wake with no drive since shut down again after 2 minutes instead of an hour; a drive clears it.

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
