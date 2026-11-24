"""card's side of StarView's doors (fork patches 46-53): the tablet's / phone's lock and unlock, the Main Body module's
replies, the doors' real lock state and the driver's door for StarLock's auto-lock.

selfdrive/car/card.py calls `car_doors.update(self, CS, can_list)` once a frame, right after `self.CI.update`; the
Toyota controller's StarViewDoorLocks (opendbc/car/toyota/starview_doors.py) does the work on the CAN side. Files in
/dev/shm (RAM only) to and from starviewd:
  DOOR_REQUEST  "lock" / "unlock" [+ sound [+ pattern]] from starviewd's `door` action; read and removed here
  DOOR_RESULT   what happened to it, for the tablet
  LOCKS         the doors' real lock state (4th-gen Sienna), written only on a change
  DRIVER_DOOR   the driver's door, any door and Park (starview/autolock.py), written only on a change
"""
import json
import os
import time

from opendbc.car import structs

DOOR_REQUEST = "/dev/shm/starview_door_request"
DOOR_RESULT = "/dev/shm/starview_door_result"
DRIVER_DOOR = "/dev/shm/starview_driver_door"
LOCKS = "/dev/shm/starview_locks"
REPLY_ADDRESS = 0x758   # the Main Body module's replies


def update(car, CS, can_list) -> None:
  """card's hook (Car.state_update). The state lives on card's Car, made on the first call."""
  doors = car.__dict__.get('_starview_doors')
  if doors is None:
    doors = car._starview_doors = CarDoors()
  doors.update(car.CI, CS, can_list)


def _write(path, data) -> None:
  try:
    with open(path + '.tmp', 'w') as f:
      f.write(json.dumps(data))
    os.replace(path + '.tmp', path)
  except OSError:
    pass


class CarDoors:
  def __init__(self):
    self.polls = 0
    self.locks_written = -1
    self.driver_door_prev = None
    self.driver_door_n = 0
    self.driver_door_closes = 0

  def update(self, CI, CS, can_list) -> None:
    door_locks = getattr(CI.CC, 'door_locks', None) if CI.CC is not None else None
    if door_locks is not None:
      self.replies(door_locks, can_list)
      self.poll_request(door_locks)
    self.publish_driver_door(CI, CS)

  @staticmethod
  def replies(door_locks, can_list) -> None:
    """A door request running (about a second, rarely), or 0.3 s after the lock-state reads (every 2 s, Sienna): hand
    the body module's replies to it - the car's own confirmation and its real lock state. Nothing is scanned otherwise."""
    if not getattr(door_locks, 'listening', False):
      return
    for _, frames in can_list:
      for address, dat, src in frames:
        if address == REPLY_ADDRESS and src == 0:
          door_locks.response(dat)

  def poll_request(self, door_locks) -> None:
    """A lock / unlock from the tablet or phone (starviewd writes DOOR_REQUEST). Checked 4x a second - one stat() when
    nothing is asked - and handed to the Toyota controller, which sends it once over the normal link (no pandad pause,
    so cruise never sees a gap). What happened goes to DOOR_RESULT for the tablet."""
    self.polls += 1
    # 4x a second while idle; 20x while a request runs, so the answer is back as soon as the doors move
    busy = door_locks.sequence is not None or door_locks.manual is not None or bool(door_locks.manual_result)
    if self.polls % (5 if busy else 25):
      return
    # written once at start too (nothing known yet), so the last drive's state is never shown as this drive's
    if door_locks.read_locks and door_locks.locks_version != self.locks_written:
      self.locks_written = door_locks.locks_version
      _write(LOCKS, {'v': door_locks.locks_version, 'doors': door_locks.locks, 'time': time.time()})  # noqa: TID251
    if door_locks.manual_result:
      _write(DOOR_RESULT, {'result': door_locks.manual_result, 'time': time.time()})  # noqa: TID251  shown on the tablet
      door_locks.manual_result = ''
    try:
      age = time.time() - os.stat(DOOR_REQUEST).st_mtime  # noqa: TID251  file mtime is wall clock
    except OSError:
      return
    try:
      with open(DOOR_REQUEST) as f:
        cmd = f.read().strip()
      os.unlink(DOOR_REQUEST)
    except OSError:
      return
    if cmd.split(' ')[0] in ('lock', 'unlock') and len(cmd) <= 32 and 0 <= age < 5:   # "lock" / "unlock horn 2x8x17" ...
      door_locks.manual = cmd

  def publish_driver_door(self, CI, CS) -> None:
    """StarLock auto-lock: the driver's door, any door and Park, written to DRIVER_DOOR only when one of them changes
    (a few times per stop). starviewd's autolock arms on the driver's door closing in Park."""
    drv = getattr(CI.CS, 'driver_door_open', None)
    if drv is None:
      return
    now = (bool(drv), bool(CS.doorOpen), CS.gearShifter == structs.CarState.GearShifter.park)
    if now == self.driver_door_prev:
      return
    prev, self.driver_door_prev = self.driver_door_prev, now
    self.driver_door_n += 1
    if prev is not None and prev[0] and not now[0]:   # the driver's door just closed (counted, so none is missed)
      self.driver_door_closes += 1
    _write(DRIVER_DOOR, {'n': self.driver_door_n, 'driver': 'open' if now[0] else 'shut', 'any_open': now[1],
                         'park': now[2], 'closes': self.driver_door_closes})
