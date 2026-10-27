import json

import pytest

from openpilot.starpilot.system.starview import ble_door, pairing


@pytest.fixture(autouse=True)
def key(tmp_path, monkeypatch):
  monkeypatch.setattr(pairing, "KEY_FILE", tmp_path / "termkey")
  monkeypatch.setattr(pairing, "STARVIEW_DIR", tmp_path)
  pairing.end_sessions()


def handler(calls):
  return ble_door.Handler(lambda: "6e453c4b", lambda cmd, sound: calls.append((cmd, sound)) or {"ok": True, "result": f"{cmd}: sent"})


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
