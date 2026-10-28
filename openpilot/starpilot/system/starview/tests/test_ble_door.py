import json

import pytest

from openpilot.starpilot.system.starview import ble_door, pairing


@pytest.fixture(autouse=True)
def key(tmp_path, monkeypatch):
  monkeypatch.setattr(pairing, "KEY_FILE", tmp_path / "termkey")
  monkeypatch.setattr(pairing, "STARVIEW_DIR", tmp_path)
  pairing.end_sessions()


def handler(calls):
  def door(cmd, sound, beeps=None):
    calls.append((cmd, sound) + ((beeps,) if beeps else ()))
    return {"ok": True, "result": f"{cmd}: sent"}
  return ble_door.Handler(lambda: "6e453c4b", door)


def ask(h, **req):
  return json.loads(h.handle(json.dumps(req).encode()))


def test_hello_then_door_runs_the_command_once():
  calls = []
  h = handler(calls)
  cn = "ab" * 16
  hello = ask(h, op="hello", cn=cn)
  assert hello["proof"] == pairing.server_proof("6e453c4b", cn, hello["sn"])
  proof = pairing.client_proof("6e453c4b", hello["sn"], cn)
  assert ask(h, op="door", cmd="lock", sn=hello["sn"], cn=cn, proof=proof) == {"op": "door", "ok": True, "result": "lock: sent"}
  assert calls == [("lock", "horn")]
  # the challenge is single-use: replaying the same proof does nothing
  assert not ask(h, op="door", cmd="lock", sn=hello["sn"], cn=cn, proof=proof)["ok"]
  assert calls == [("lock", "horn")]
  hello = ask(h, op="hello", cn=cn)
  assert ask(h, op="door", cmd="unlock", sound="horn", sn=hello["sn"], cn=cn,
             proof=pairing.client_proof("6e453c4b", hello["sn"], cn))["ok"]
  assert calls[-1] == ("unlock", "horn")
  hello = ask(h, op="hello", cn=cn)       # StarLock's own horn pattern is handed on to starviewd, which checks it
  assert ask(h, op="door", cmd="unlock", sound="horn", beeps=[3, 100, 200], sn=hello["sn"], cn=cn,
             proof=pairing.client_proof("6e453c4b", hello["sn"], cn))["ok"]
  assert calls[-1] == ("unlock", "horn", [3, 100, 200])


def test_wrong_key_or_command_is_refused():
  calls = []
  h = handler(calls)
  cn = "cd" * 16
  hello = ask(h, op="hello", cn=cn)
  assert not ask(h, op="door", cmd="lock", sn=hello["sn"], cn=cn, proof="00" * 32)["ok"]
  hello = ask(h, op="hello", cn=cn)
  proof = pairing.client_proof("6e453c4b", hello["sn"], cn)
  assert ask(h, op="door", cmd="open", sn=hello["sn"], cn=cn, proof=proof)["error"] == "bad door command"
  assert ask(h, op="hello", cn="xyz")["op"] == "error"
  assert json.loads(h.handle(b"\xff"))["op"] == "error"
  assert calls == []


def test_autolock_settings_need_the_key_and_rssi_does_not():
  saved = []
  h = ble_door.Handler(lambda: "6e453c4b", lambda cmd, sound, beeps=None: {"ok": True},
                       autolock=lambda new: saved.append(new) or {"ok": True, "status": {"phase": "idle"}},
                       signal=lambda: -57)
  assert ask(h, op="rssi") == {"op": "rssi", "dbm": -57}
  cn = "ef" * 16
  hello = ask(h, op="hello", cn=cn)
  assert not ask(h, op="autolock", set={"lock": True}, sn=hello["sn"], cn=cn, proof="00" * 32)["ok"]
  assert saved == []
  hello = ask(h, op="hello", cn=cn)
  r = ask(h, op="autolock", set={"lock": True}, sn=hello["sn"], cn=cn, proof=pairing.client_proof("6e453c4b", hello["sn"], cn))
  assert r["ok"] and r["status"]["phase"] == "idle"
  assert saved == [{"lock": True}]


def test_long_write_in_pieces_and_short_answers():
  h = ble_door.Handler(lambda: "6e453c4b", lambda cmd, sound, beeps=None: {"ok": True},
                       autolock=lambda new: {"ok": True, "status": {"phase": "returning", "event": "x" * 200, "dbm": -100},
                                             "config": {"lock": True, "unlock": True, "lock_dbm": -52, "away_dbm": -75,
                                                        "unlock_dbm": -62, "unlock_min": 30, "sound": "horn",
                                                        "lock_beeps": [1, 80, 170], "unlock_beeps": [2, 80, 170]}})
  cn = "ab" * 16
  hello = json.loads(h.feed(json.dumps({"op": "hello", "cn": cn}).encode()))
  req = json.dumps({"op": "autolock", "set": {"lock": True, "unlock": True, "lock_dbm": -52, "away_dbm": -75, "unlock_dbm": -62,
                                              "unlock_min": 30, "sound": "horn", "lock_beeps": [1, 80, 170],
                                              "unlock_beeps": [2, 80, 170]},
                    "sn": hello["sn"], "cn": cn, "proof": pairing.client_proof("6e453c4b", hello["sn"], cn)}).encode()
  assert len(req) > 244
  pieces = [req[i:i + 200] for i in range(0, len(req), 200)]
  assert h.feed(pieces[0], 0) is None                     # waits for the rest
  out = h.feed(pieces[1], 200)
  assert len(out) <= 244
  r = json.loads(out)
  assert r["ok"] and r["config"]["unlock_min"] == 30 and len(r["status"]["event"]) == 40
  assert json.loads(h.feed(b"\xff"))["op"] == "error"     # junk still gets an answer
  assert h.feed(b"{\"op\":", 0) is None and h.feed(b"\"rssi\"}", 99) is None   # out of order: dropped


def test_announce_queues_for_the_bluetooth_loop():
  woke = []
  ble_door._WAKE["fn"] = lambda: woke.append(1)
  try:
    ble_door.announce({"op": "auto", "cmd": "lock", "ok": True, "result": "lock: confirmed"})
    assert woke == [1]
    assert json.loads(ble_door._OUT.get_nowait()) == {"op": "auto", "cmd": "lock", "ok": True, "result": "lock: confirmed"}
  finally:
    ble_door._WAKE["fn"] = None
