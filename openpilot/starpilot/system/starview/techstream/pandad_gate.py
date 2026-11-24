"""pandad's should_run (system/manager/process_config.py imports it): StarView TechStream's diagnostic mode has the
panda to itself (session.py), so pandad stays stopped while DIAG_FLAG is fresh. starviewd renews it every 5 s, so a
flag nobody renews (starviewd gone) is ignored after FLAG_FRESH_S and pandad comes back on its own. os and time only:
the manager loads this.
"""
import os
import time

DIAG_FLAG = "/dev/shm/starview_diag"   # session.py's own
FLAG_FRESH_S = 20


def pandad_run(started, params, CP) -> bool:
  try:
    age = time.time() - os.path.getmtime(DIAG_FLAG)  # noqa: TID251  file mtimes are wall clock
    return not 0 <= age < FLAG_FRESH_S    # a clock set back can't hold pandad off
  except OSError:
    return True
