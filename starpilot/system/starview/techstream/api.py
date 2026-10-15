"""TechStream's HTTP layer for starviewd: check the request -> techstream/* -> (status, body).

The methods block (they wait for pandad to stop and for ECUs to answer); starviewd calls them in a thread. A body of
None means 204. Protocol details are in the modules' docstrings; the page's types are in web_src/src/lib/schema.ts.
(toyopilot's lanlinkd/toyota_diag_api.py, translated; parked check and pandad hand-off adapted to StarPilot.)
"""
import subprocess
import threading
from collections.abc import Callable

from openpilot.common.swaglog import cloudlog
from openpilot.starpilot.system.starview.techstream import active_tests, catalog, coding, customization, dtc, live_data
from openpilot.starpilot.system.starview.techstream.backups import BackupStore
from openpilot.starpilot.system.starview.techstream.link import EcuRejectedError, MalformedResponseError, NoResponseError
from openpilot.starpilot.system.starview.techstream.session import DiagSession, SessionError

BACKUP_DIR = "/data/starview/techstream_backups"
WATCHDOG_PERIOD_S = 5
LIVE_READ_LIMIT = 40


def _process_alive(cmd: list[str]) -> bool:
  try:
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
  except FileNotFoundError:  # dev PC without pidof
    return False


def pandad_running(run: Callable[[list[str]], bool] = _process_alive) -> bool:
  """Stopped only once both the native pandad and its Python wrapper are gone."""
  return run(["pidof", "pandad"]) or run(["pgrep", "-f", r"selfdrive\.pandad\.pandad"])


def open_panda_link():
  from opendbc.car.structs import CarParams
  from panda import Panda

  from openpilot.starpilot.system.starview.techstream.link import DiagLink
  panda = Panda()
  try:
    return DiagLink(panda, CarParams.SafetyModel.elm327)
  except Exception:
    panda.close()  # otherwise the handle keeps USB/SPI busy and pandad can't reconnect when it's back
    raise


def create(is_offroad: Callable[[], bool], is_parked: Callable[[], bool]) -> "TechStreamApi":
  session = DiagSession(open_link=open_panda_link, pandad_running=pandad_running, is_offroad=is_offroad, is_parked=is_parked)
  session.reset_on_startup()
  return TechStreamApi(session, BACKUP_DIR)


class RequestError(Exception):
  def __init__(self, status: int, message: str):
    super().__init__(message)
    self.status = status
    self.message = message


def _guarded(operation: Callable[[], dict | None], status: int = 200) -> tuple[int, dict | None]:
  try:
    body = operation()
  except (SessionError, RequestError) as exc:
    return exc.status, {"error": exc.message}
  except NoResponseError as exc:
    return 504, {"error": f"ECU didn't respond: {exc}"}
  except EcuRejectedError as exc:
    return 502, {"error": str(exc)}
  except customization.StaleDataError as exc:
    return 409, {"error": f"{exc} - scan again"}
  except MalformedResponseError as exc:
    return 502, {"error": f"Bad ECU response: {exc}"}
  except customization.BackupError as exc:
    return 500, {"error": str(exc)}
  except Exception as exc:  # unexpected errors still get JSON for the page, and a log line
    cloudlog.exception("techstream: unhandled error")
    return 500, {"error": f"Internal error: {exc}"}
  return (204, None) if body is None else (status, body)


def _value_view(setting: dict, data_hex: str) -> dict:
  """A backup's whole data -> {value, label}: options look up the catalog label, numbers are their own label."""
  value = coding.extract_value(bytes.fromhex(data_hex), setting["byteIndex"], int(setting["mask"], 16))
  return {"value": value, "label": catalog.option_label(setting["options"], value) or str(value)}


def _backup_view(backup: dict) -> dict:
  setting = catalog.setting(backup["key"])
  ecu = catalog.ecu(backup["ecu"])
  return {"id": backup["id"], "time": backup["time"], "key": backup["key"], "name": setting["name"],
          "ecu": ecu["name"] if ecu else backup["ecu"],
          "before": _value_view(setting, backup["data"]), "after": _value_view(setting, backup["after"]),
          "restored": backup.get("restored", False)}


def _is_listable(backup: dict) -> bool:
  """Old-format files without a key, and items no longer in the catalog, are neither listed nor restored."""
  return "key" in backup and catalog.setting(backup["key"]) is not None


def _value_allowed(setting: dict, value) -> bool:
  if not isinstance(value, int) or isinstance(value, bool):
    return False
  if setting["numeric"]:
    return setting["numeric"]["min"] <= value <= setting["numeric"]["max"]
  return any(o["value"] == value for o in setting["options"])


def _catalog_ecu(body: dict) -> dict:
  ecu = catalog.ecu(body.get("ecu")) if isinstance(body.get("ecu"), str) else None
  if ecu is None:
    raise RequestError(400, "invalid ecu")
  return ecu


class TechStreamApi:
  def __init__(self, session: DiagSession, backup_dir: str):
    self.session = session
    self.backups = BackupStore(backup_dir)
    self.tests = active_tests.Runner(lambda fn: self.session.run(fn))

  def watchdog(self, stop: threading.Event) -> None:
    """Background thread: keeps the pandad flag fresh while in diagnostic mode, leaves it after the idle timeout, and
    hands pandad back when starviewd stops."""
    while not stop.wait(WATCHDOG_PERIOD_S):
      try:
        self.session.keepalive()
        if self.tests.active is None:     # a running Active Test counts as activity
          self.session.expire_if_idle()
      except Exception:
        cloudlog.exception("techstream: watchdog")
    self.tests.stop("starviewd stopping")
    self.session.exit()

  # ---- session ----
  def session_get(self):
    return _guarded(self.session.snapshot)

  def session_enter(self):
    def enter():
      self.session.enter()
      return self.session.snapshot()
    return _guarded(enter)

  def session_exit(self):
    def leave():
      self.tests.stop("diagnostic mode exited")
      self.session.exit()
    return _guarded(leave)

  # ---- catalog ----
  def catalog_get(self):
    """Doesn't need diagnostic mode. The trouble-code texts aren't sent: scan results come with them filled in."""
    return _guarded(lambda: {k: v for k, v in catalog.load_sienna().items() if k != "dtcText"})

  # ---- customization ----
  def customizations_scan(self, body: dict):
    """Scan one ECU: the page calls this for each ECU in the catalog and tracks progress itself."""
    def scan():
      ecu = _catalog_ecu(body)
      settings = [s for s in catalog.load_sienna()["settings"] if s["ecu"] == ecu["id"]]
      return self.session.run(lambda link: customization.scan_ecu(link, ecu, settings))
    return _guarded(scan)

  def customization_write(self, key: str, body: dict):
    def write():
      setting = catalog.setting(key)
      if setting is None:
        raise RequestError(404, "unknown setting")
      value = body.get("value")
      if not _value_allowed(setting, value):
        raise RequestError(400, "invalid value")
      before = body.get("before")
      if not isinstance(before, str):
        raise RequestError(400, "missing before (the raw data from the scan)")
      ecu = catalog.ecu(setting["ecu"])
      return self.session.run(lambda link: customization.write_setting(link, ecu, setting, value, before, self.backups))
    return _guarded(write)

  def customization_probe(self, key: str):
    """StarView addition: read an item the ECU didn't list in the scan (see customization.probe_setting)."""
    def probe():
      setting = catalog.setting(key)
      if setting is None:
        raise RequestError(404, "unknown setting")
      ecu = catalog.ecu(setting["ecu"])
      missing = f"{ecu['name']} doesn't have this setting"
      try:
        return self.session.run(lambda link: customization.probe_setting(link, ecu, setting))
      except EcuRejectedError as exc:
        # 31 request out of range (UDS: no such DID), 11 / 12 service / sub-function not supported (CAN window motors)
        reason = {0x31: "request out of range", 0x11: "not supported", 0x12: "not supported"}.get(exc.nrc)
        if reason:
          raise RequestError(404, f"{missing} (it answered \"{reason}\")") from exc
        raise
      except MalformedResponseError as exc:
        if "mask table" in str(exc):   # Toyota CAN ECU whose A8 03 table has no entry for this item
          raise RequestError(404, f"{missing} (not in its setting table)") from exc
        raise
    return _guarded(probe)

  # ---- Active Tests (StarView addition, Toyota's GTS+ definitions) ----
  def tests_list(self):
    return _guarded(active_tests.listing)

  def tests_check(self, body: dict):
    def run():
      ecu = str(body.get("ecu"))
      if not any(e["id"] == ecu for e in active_tests.load()["ecus"]):
        raise RequestError(404, "unknown module")
      return self.session.run(lambda link: active_tests.check(link, ecu))
    return _guarded(run)

  def test_start(self, body: dict):
    def start():
      test = active_tests.find(str(body.get("ecu")), str(body.get("id")))
      if test is None:
        raise RequestError(404, "unknown test")
      choice = body.get("choice")
      try:
        return self.tests.start(test, choice if isinstance(choice, str) else None)
      except active_tests.TestError as exc:
        raise RequestError(400, str(exc)) from exc
      except EcuRejectedError as exc:
        if exc.nrc in (0x31, 0x11, 0x12):
          raise RequestError(404, f"{test['name']}: this module doesn't have this test") from exc
        if exc.nrc == 0x22:
          why = "conditions not correct - power on, parked, doors / gear as the test needs"
          raise RequestError(409, f"{test['name']}: the module refused right now ({why})") from exc
        raise
    return _guarded(start)

  def test_stop(self, body: dict | None = None):
    return _guarded(lambda: self.tests.stop())

  def test_ping(self, body: dict | None = None):
    return _guarded(self.tests.ping)

  # ---- backups ----
  def backups_list(self):
    return _guarded(lambda: {"backups": [_backup_view(b) for b in self.backups.list() if _is_listable(b)]})

  def backup_restore(self, backup_id: str):
    def restore():
      backup = self.backups.get(backup_id)
      if backup is None or not _is_listable(backup):
        raise RequestError(404, "no such backup")
      setting = catalog.setting(backup["key"])
      ecu = catalog.ecu(backup["ecu"])
      return self.session.run(lambda link: customization.restore_setting(link, ecu, setting, backup, self.backups))
    return _guarded(restore)

  # ---- trouble codes ----
  def dtc_scan(self, body: dict):
    """Scan one ECU: the page calls this for each ECU in the catalog. Texts come filled in from the catalog's dtcText."""
    def scan():
      ecu = _catalog_ecu(body)
      return self.session.run(lambda link: dtc.scan_ecu(link, ecu, catalog.load_sienna()["dtcText"]))
    return _guarded(scan)

  def dtc_clear(self, body: dict):
    def clear():
      ecus = body.get("ecus")
      if not isinstance(ecus, list) or not ecus or not all(isinstance(e, str) and catalog.ecu(e) for e in ecus):
        raise RequestError(400, "invalid ecus")
      return {"results": self.session.run(lambda link: [dtc.clear(link, catalog.ecu(e)) for e in ecus])}
    return _guarded(clear)

  # ---- live data ----
  def live_read(self, body: dict):
    def read():
      keys = body.get("keys")
      if (not isinstance(keys, list) or not 0 < len(keys) <= LIVE_READ_LIMIT
          or not all(isinstance(k, str) and catalog.live_item(k) for k in keys)):
        raise RequestError(400, f"keys must be 1 to {LIVE_READ_LIMIT} live-data items from the catalog")
      items = [catalog.live_item(k) for k in keys]
      return {"values": self.session.run(lambda link: live_data.read(link, items))}
    return _guarded(read)
