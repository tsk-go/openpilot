"""Auto USB tethering: the comma turns the tablet's USB tethering on over adb (the pairing in /data/starview/adbhome).

The tablet falls back to charging-only after its cable comes back (unplugged, or the hub's power cut by hub_power.py),
and its "default USB configuration" isn't applied. With USB debugging on and this comma allowed once, starviewd's
auto_tether_thread calls TetherWatch.step every 20 s while there's no USB link:
  * not tethering -> `svc usb setFunctions rndis` (what the tethering toggle does);
  * says rndis but still no link after STUCK_S -> reset its USB like a replug: functions none, 2 s, rndis (in one
    detached shell on the tablet - the adb connection drops in between). Nov 5: switched on right after the hub's
    power came back, the tablet reported rndis and the link never came up; it sat like that until the cable was
    replugged. Resets back off: RESET_GAP_S after each one.
"""
STUCK_S = 30.0
RESET_GAP_S = (60.0, 300.0)       # after the 1st reset, after the 2nd and later
RESET_CMD = "nohup sh -c 'svc usb setFunctions; sleep 2; svc usb setFunctions rndis' >/dev/null 2>&1 &"


class TetherWatch:
  def __init__(self, adb, log=print):
    self.adb = adb                # adb(serial, *args) -> stdout str (raises on failure)
    self.log = log
    self.rndis_since = {}         # serial -> monotonic time it first said rndis without a link
    self.resets = {}              # serial -> resets since the link was last up
    self.next_reset = {}          # serial -> earliest monotonic time for the next reset

  def link_up(self):
    self.rndis_since.clear()
    self.resets.clear()
    self.next_reset.clear()

  def step(self, now: float, serials) -> list:
    """No USB link right now; serials = tablets adb sees. Returns what was done, per serial."""
    done = []
    for sn in serials:
      cur = self.adb(sn, "shell", "svc", "usb", "getFunctions") or ""
      if "rndis" not in cur:
        self.adb(sn, "shell", "svc", "usb", "setFunctions", "rndis")
        self.rndis_since[sn] = now
        self.log(f"starview: tablet {sn} was not tethering ({cur.strip() or 'none'}); switched USB tethering on")
        done.append((sn, "on"))
        continue
      since = self.rndis_since.setdefault(sn, now)
      if now - since < STUCK_S or now < self.next_reset.get(sn, 0.0):
        continue
      n = self.resets.get(sn, 0) + 1
      self.adb(sn, "shell", RESET_CMD)
      self.resets[sn] = n
      self.rndis_since[sn] = now
      self.next_reset[sn] = now + RESET_GAP_S[min(n, len(RESET_GAP_S)) - 1]
      self.log(f"starview: tablet {sn} says tethering but no link for {int(now - since)} s; reset its USB (#{n})")
      done.append((sn, "reset"))
    return done
