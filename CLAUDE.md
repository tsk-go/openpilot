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

**Fixes to upstream behaviour (drop when upstream fixes them; see the section above)**
12. Chestnut big model compiles every start (patches 14, 16): `starpilot/models/program_cache.py`, `load_profile.py`,
    modeld timeouts.
14. "Driving Model Lagging" seconds after the big model loads (patches 22, 24): `starpilot/models/warmup.py`; modeld keeps
    ChestnutLoading (no engaging, drops not counted) until 1 s of normal passes, at most 15 s.
18. A full update shows "failed" after its own reboot (patch 29): `system/updated/updated.py` `recover_fast_state`.

**No longer carried**
- AOL on the SecOC Sienna (patch 6): merged upstream (firestar `79fdeb4`, rebuilt panda/pandad `337bb0754`).
- Waze bridge and split screen (patch 3): replaced by the in-app map (patch 9).
- Hash the big model file while modeld waits (patch 17): written, then skipped by the owner.
- Updates refused offroad + parked with the ignition on (patch 20): fixed upstream ("Allow Forced Offroad Updates",
  firestar `defaf64c`: an update forced offroad no longer needs live carState/selfdriveState); `park_marker.py` removed.
- steerlearnerd memory on long drives (patch 26, never pushed): fixed upstream ("Bound FLM replay memory", firestar
  `0b01007a`, which also restarts steerlearnerd when it exits).
