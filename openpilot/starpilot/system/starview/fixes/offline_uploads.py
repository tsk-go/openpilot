"""Fork fix 5 (CLAUDE.md "Fork fixes"): the uploader spins while StarView's offline mode blocks every upload.

With offline mode on nothing can upload, so no route ever settles and every uploader step rescanned every drive
folder (~960 routes, owns_recording per file): 63 % of a core over a 15-min drive (Nov 3). The uploader's main loop
sleeps on this like on "no network". Hook: system/loggerd/uploader.py imports offline_mode_on and adds it to its
no-network check. One stat(); offline.py (StarView's offline mode, not loaded here) keeps the same FLAG.
"""
import os

FLAG = "/data/starview/offline"


def offline_mode_on() -> bool:
  return os.path.exists(FLAG)
