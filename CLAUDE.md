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

After every sync, check whether upstream now fixes either of these on its own. If it does, remove our fix in a
normal commit (no revert of history, no force-push) and tell the owner which one was dropped:

1. **Chestnut big model compiles every start** (patches 14 and 16): `openpilot/starpilot/models/program_cache.py`,
   `load_profile.py`, and in `openpilot/selfdrive/modeld/modeld.py` `program_cache.*`, `load_profile.watch`,
   `BIG_MODEL_FIRST_TIMEOUT`, `BIG_MODEL_CACHED_TIMEOUT`. Upstream fixed = the big model's compiled programs survive a
   reboot by themselves (no `do_to_program` codegen at every start), or modeld's load timeout no longer cuts it off.
2. **Galaxy updates refused with the ignition on, offroad and parked**: `openpilot/starpilot/drive_state/park_marker.py`,
   `status(parked_marker=...)` in `openpilot/starpilot/drive_state/evidence.py`, and the `ParkMarker` lines in
   `openpilot/selfdrive/car/card.py`. Upstream fixed = `PhysicalSource.update_status` can allow an update offroad with
   the ignition on (it no longer needs live carState/selfdriveState, which stop offroad).
