"""Fork fix 3 (CLAUDE.md "Fork fixes"): a full update shows "failed" after its own reboot.

normal_update's last stage is "rebooting" and that reboot is how it installs, but recover_fast_state turns every
unfinished stage into "Update process restarted before completion". Hook: system/updated/updated.py's
recover_fast_state calls finished(state) first; a full update's reboot then reads as complete. Only the full update's
own words count (FULL_UPDATE_REBOOT, upstream's text in normal_update, checked by a test): the fast update says
"rebooting" a moment before its own "complete", and a restart in between is still an interruption.
"""

FULL_UPDATE_REBOOT = "Update installed. Restarting device."


def finished(state: dict) -> None:
  if state.get('stage') == 'rebooting' and state.get('detail') == FULL_UPDATE_REBOOT:
    state.update(version=1, stage='complete', detail='Update installed.')
