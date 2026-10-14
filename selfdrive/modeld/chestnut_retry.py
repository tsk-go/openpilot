"""Once-per-drive marker for the big (Chestnut) model's load retry (modeld._retry_big_model_once).

A file, not a param: this repo ships prebuilt binaries (the `prebuilt` marker), and params_pyx.so has the key list
compiled in, so a key added only to params_keys.h is unknown on the device - and saving an unknown key raises, which
would crash modeld exactly when the big model failed to load. The file is gone after a reboot, and the manager
removes it at manager start and when the ignition turns on, the same moments it clears CLEAR_ON_IGNITION_ON params.
No heavy imports: the manager imports this too.
"""
from pathlib import Path

RETRY_FLAG = Path("/dev/shm/chestnut_retry")


def retried() -> bool:
  return RETRY_FLAG.exists()


def mark() -> bool:
  """Remember the retry for this drive. False if that's not possible (then don't retry: no cycle loop)."""
  try:
    RETRY_FLAG.touch()
    return True
  except OSError:
    return False


def clear() -> None:
  try:
    RETRY_FLAG.unlink(missing_ok=True)
  except OSError:
    pass
