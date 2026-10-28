"""StarLock over Bluetooth LE: the phone's Lock / Unlock reaches starviewd's "door" action without Wi-Fi.

The comma advertises one GATT service (bluez, via dbus-python) while openpilot is started, and nothing otherwise:
  RX 5a1c0002-... (write)   phone -> comma, JSON
  TX 5a1c0003-... (notify)  comma -> phone, JSON
Same key and proofs as the tablet's Wi-Fi pairing (pairing.py), with "ble" as the peer address:
  {"op":"hello","cn"}                        -> {"op":"hello","dongle","sn","proof"}     (comma proves it has the key)
  {"op":"door","cmd","sound","beeps"?,"sn","cn","proof"} -> {"op":"door","ok","result"/"error"}  (phone proves it;
                                                                                                sn single-use)
  {"op":"autolock","set"?,"sn","cn","proof"} -> {"op":"autolock","ok","config","status"}   (auto-lock settings, autolock.py)
  {"op":"rssi"} -> {"op":"rssi","dbm"}   (the comma's reading of this phone's signal, for tuning; nothing secret)
Costs nothing while idle: bluez advertises from the controller; this thread sleeps in a GLib loop that checks every 2 s
whether openpilot is started.
"""
import ctypes
import json
import threading

from openpilot.starpilot.system.starview import pairing

SERVICE = "5a1c0001-7374-6172-6c6f-636b00000000"
RX = "5a1c0002-7374-6172-6c6f-636b00000000"
TX = "5a1c0003-7374-6172-6c6f-636b00000000"
PEER = "ble"
MAX_REQUEST = 1024


class Handler:
  """The protocol, without Bluetooth: bytes in, bytes out (unit-tested)."""
  def __init__(self, dongle_id, door, autolock=None, signal=None):
    self.dongle_id = dongle_id     # () -> str
    self.door = door               # (cmd, sound, beeps) -> {"ok", "result"/"error"}
    self.autolock = autolock       # (settings to save or None) -> {"ok", "config", "status"} / {"ok": False, "error"}
    self.signal = signal           # () -> dBm | None

  def handle(self, data: bytes) -> bytes:
    try:
      req = json.loads(bytes(data).decode())
      op = req.get("op")
    except (ValueError, UnicodeDecodeError, AttributeError):
      return json.dumps({"op": "error", "error": "bad request"}).encode()
    if op == "hello":
      r = pairing.challenge(PEER, self.dongle_id(), req.get("cn"))
      if r is None:
        return json.dumps({"op": "error", "error": "bad nonce"}).encode()
      return json.dumps({"op": "hello", "dongle": r["dongleId"], "sn": r["sn"], "proof": r["proof"]}).encode()
    if op == "door":
      cmd, sound = req.get("cmd"), req.get("sound") or "horn"
      if cmd not in ("lock", "unlock") or sound not in ("buzzer", "horn", "none"):
        return json.dumps({"op": "door", "ok": False, "error": "bad door command"}).encode()
      if pairing.open_session(PEER, self.dongle_id(), req.get("sn"), req.get("cn"), req.get("proof")) is None:
        return json.dumps({"op": "door", "ok": False, "error": "not paired - pair StarLock again"}).encode()
      ack = self.door(cmd, sound, req.get("beeps"))
      return json.dumps({"op": "door", "ok": bool(ack.get("ok")), "result": ack.get("result", ""),
                         **({"error": ack["error"]} if "error" in ack else {})}).encode()
    if op == "rssi" and self.signal is not None:
      return json.dumps({"op": "rssi", "dbm": self.signal()}).encode()
    if op == "autolock" and self.autolock is not None:
      if pairing.open_session(PEER, self.dongle_id(), req.get("sn"), req.get("cn"), req.get("proof")) is None:
        return json.dumps({"op": "autolock", "ok": False, "error": "not paired - pair StarLock again"}).encode()
      r = self.autolock(req.get("set"))
      # a notification carries at most MTU - 3 (244) bytes: the lines and switches, and a short status
      out = {"op": "autolock", "ok": bool(r.get("ok"))}
      if "error" in r:
        out["error"] = str(r["error"])[:120]
      if "config" in r:
        out["config"] = {k: r["config"][k] for k in ("lock", "unlock", "lock_dbm", "away_dbm", "unlock_dbm", "unlock_min")}
      if "status" in r:
        st = r["status"]
        out["status"] = {"phase": st.get("phase"), "event": str(st.get("event") or "")[:40], "dbm": st.get("dbm")}
      return json.dumps(out, separators=(",", ":")).encode()
    return json.dumps({"op": "error", "error": "unknown op"}).encode()

  def feed(self, data: bytes, offset: int = 0) -> bytes | None:
    """One write from bluez. A request longer than one packet (the auto-lock settings with the pairing proof) arrives
    as a long write in pieces with their offsets: collect them, answer once the JSON is whole."""
    if offset == 0:
      self._buf = bytearray()
    buf = getattr(self, "_buf", bytearray())
    if offset != len(buf) or len(buf) + len(data) > MAX_REQUEST:
      self._buf = bytearray()
      return None
    buf += data
    self._buf = buf
    try:
      json.loads(bytes(buf).decode())
    except (ValueError, UnicodeDecodeError):
      return None if len(buf) > 2 and buf[:1] == b"{" else self.handle(bytes(buf))
    self._buf = bytearray()
    return self.handle(bytes(buf))


def run(handler: Handler, started, log=lambda s: None) -> None:
  """Thread body: register the service + advertisement while started() is true, drop them when it isn't."""
  import dbus
  import dbus.service
  from dbus.mainloop.glib import DBusGMainLoop

  DBusGMainLoop(set_as_default=True)
  bus = dbus.SystemBus()
  glib = ctypes.CDLL("libglib-2.0.so.0")
  glib.g_main_loop_new.restype = ctypes.c_void_p
  glib.g_main_loop_new.argtypes = [ctypes.c_void_p, ctypes.c_int]
  glib.g_main_loop_run.argtypes = [ctypes.c_void_p]
  glib.g_timeout_add.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
  PROPS_IFACE = "org.freedesktop.DBus.Properties"
  base = "/com/starpilot/starlock"

  class Tx(dbus.service.Object):
    def __init__(self):
      super().__init__(bus, base + "/s0/tx")
      self.notifying = False
    def props(self):
      return {"Service": dbus.ObjectPath(base + "/s0"), "UUID": TX, "Flags": dbus.Array(["notify"], signature="s")}
    @dbus.service.method("org.bluez.GattCharacteristic1")
    def StartNotify(self):
      self.notifying = True
      log("phone subscribed")
    @dbus.service.method("org.bluez.GattCharacteristic1")
    def StopNotify(self):
      self.notifying = False
    @dbus.service.method(PROPS_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface):
      return self.props()
    @dbus.service.signal(PROPS_IFACE, signature="sa{sv}as")
    def PropertiesChanged(self, iface, changed, invalidated):
      pass
    def send(self, data: bytes):
      log(f"-> {len(data)} bytes {data[:60]!r}" + ("" if self.notifying else "  (NOT subscribed: dropped)"))
      if self.notifying:
        self.PropertiesChanged("org.bluez.GattCharacteristic1", {"Value": dbus.Array(data, signature="y")}, [])

  tx = Tx()

  class Rx(dbus.service.Object):
    def __init__(self):
      super().__init__(bus, base + "/s0/rx")
    def props(self):
      return {"Service": dbus.ObjectPath(base + "/s0"), "UUID": RX,
              "Flags": dbus.Array(["write", "write-without-response"], signature="s")}
    @dbus.service.method("org.bluez.GattCharacteristic1", in_signature="aya{sv}")
    def WriteValue(self, value, options):
      log(f"<- {len(value)} bytes {bytes(value)[:60]!r} {dict(options)}")
      out = handler.feed(bytes(value), int(options.get("offset", 0)))
      if out is not None:
        tx.send(out)
    @dbus.service.method(PROPS_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface):
      return self.props()

  rx = Rx()

  class App(dbus.service.Object):
    def __init__(self):
      super().__init__(bus, base)
    @dbus.service.method("org.freedesktop.DBus.ObjectManager", out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
      return {dbus.ObjectPath(base + "/s0"): {"org.bluez.GattService1": {"UUID": SERVICE, "Primary": True}},
              dbus.ObjectPath(base + "/s0/rx"): {"org.bluez.GattCharacteristic1": rx.props()},
              dbus.ObjectPath(base + "/s0/tx"): {"org.bluez.GattCharacteristic1": tx.props()}}

  class Adv(dbus.service.Object):
    def __init__(self):
      super().__init__(bus, base + "/adv")
    @dbus.service.method(PROPS_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface):
      return {"Type": "peripheral", "ServiceUUIDs": dbus.Array([SERVICE], signature="s")}
    @dbus.service.method("org.bluez.LEAdvertisement1")
    def Release(self):
      pass

  class Service(dbus.service.Object):
    def __init__(self):
      super().__init__(bus, base + "/s0")

  _app, _adv, _svc = App(), Adv(), Service()   # kept referenced: bluez calls these objects
  hci = bus.get_object("org.bluez", "/org/bluez/hci0")
  gatt = dbus.Interface(hci, "org.bluez.GattManager1")
  advm = dbus.Interface(hci, "org.bluez.LEAdvertisingManager1")
  state = {"on": False}

  # bluez calls back into this process (GetManagedObjects, GetAll, Release) while it handles these, so every call
  # to it is asynchronous: a blocking one would wait on our own loop and time out.
  def failed(what):
    def f(e):
      state["on"] = False
      print(f"bluez {what}: {e}", flush=True)
    return f
  empty = lambda: dbus.Dictionary({}, signature="sv")  # noqa: E731

  def tick(_data):
    want = bool(started())
    if want and not state["on"]:
      state["on"] = True
      gatt.RegisterApplication(base, empty(), reply_handler=lambda: print("StarLock service up", flush=True),
                               error_handler=failed("service"))
      advm.RegisterAdvertisement(base + "/adv", empty(), reply_handler=lambda: print("advertising StarLock", flush=True),
                                 error_handler=failed("advertising"))
    elif not want and state["on"]:
      state["on"] = False
      advm.UnregisterAdvertisement(base + "/adv", reply_handler=lambda: None, error_handler=lambda e: None)
      gatt.UnregisterApplication(base, reply_handler=lambda: print("stopped advertising (openpilot off)", flush=True),
                                 error_handler=lambda e: None)
    return 1                  # keep the 2 s timer

  cb = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p)(tick)
  glib.g_timeout_add(2000, ctypes.cast(cb, ctypes.c_void_p), None)
  glib.g_main_loop_run(glib.g_main_loop_new(None, 0))


def start(dongle_id, door, started, log=lambda s: None, autolock=None, signal=None) -> threading.Thread:
  t = threading.Thread(target=run, args=(Handler(dongle_id, door, autolock, signal), started, log), name="starview-ble-door",
                       daemon=True)
  t.start()
  return t
