"""Galaxy remote pairing from the tablet, through the local Galaxy's own API.

The same requests the comma's settings screen makes (starpilot/ui/galaxy_access.py, which can't be imported here: it
pulls in the whole UI): a local session, then /api/galaxy/pair | unpair | status. Galaxy owns the password, its rules
and when pairing is allowed.
"""
from __future__ import annotations

import http.client
import json
import re
import time

LOCAL_PORT = 8082
LOCAL_ORIGIN = f"http://127.0.0.1:{LOCAL_PORT}"
REMOTE_URL = re.compile(r"https://galaxy\.firestar\.link/[A-Za-z0-9]{16}\Z")
TIMEOUT_S = 3.0
# One local session, kept: Galaxy holds at most 64 sessions (galaxy/auth.py LocalSessions) and drops the oldest -
# a new one per status check would push out the phone's and browser's Galaxy logins within the hour.
_cookie = ""


def _call(path: str, *, cookie: str = "", payload: dict | None = None, deadline: float) -> tuple[int, dict, str]:
  timeout = deadline - time.monotonic()
  if timeout <= 0:
    raise TimeoutError("Galaxy request timed out")
  conn = http.client.HTTPConnection("127.0.0.1", LOCAL_PORT, timeout=timeout)
  headers = {"Host": f"127.0.0.1:{LOCAL_PORT}"}
  if cookie:
    headers["Cookie"] = cookie
  if payload is not None:
    headers["Content-Type"] = "application/json"
    headers["Origin"] = LOCAL_ORIGIN
  try:
    conn.request("POST" if payload is not None else "GET", path, body=json.dumps(payload) if payload is not None else None,
                 headers=headers)
    resp = conn.getresponse()
    raw = resp.read(16_385)
    if len(raw) > 16_384:
      raise ValueError("Galaxy response is too large")
    data = json.loads(raw) if raw else {}
    if type(data) is not dict:
      raise ValueError("Invalid Galaxy response")
    return resp.status, data, resp.getheader("Set-Cookie", "").split(";", 1)[0]
  finally:
    conn.close()


def remote(action: str, password: str = "", call=_call) -> dict:
  """action: "status" | "pair" | "unpair" -> {"ok", "paired", "url", "error"}"""
  global _cookie
  try:
    deadline = time.monotonic() + TIMEOUT_S
    code, auth, new = call("/api/auth/session", cookie=_cookie, deadline=deadline)   # same session while it's valid
    cookie = new or _cookie
    if code != 200 or not auth.get("authenticated") or not auth.get("localAccess") or not cookie.startswith("galaxy_session="):
      return {"ok": False, "paired": False, "url": "", "error": "Local Galaxy is unavailable"}
    _cookie = cookie
    if action in ("pair", "unpair"):
      code, result, _ = call(f"/api/galaxy/{action}", cookie=cookie, payload={"password": password} if action == "pair" else {},
                             deadline=deadline)
      if code != 200:
        err = result.get("error")
        return {"ok": False, "paired": False, "url": "",
                "error": err if type(err) is str and len(err) <= 128 else "Galaxy pairing is unavailable"}
      code, auth, new = call("/api/auth/session", cookie=cookie, deadline=deadline)
      cookie = _cookie = new or cookie
      if code != 200 or not auth.get("authenticated"):
        return {"ok": False, "paired": False, "url": "", "error": "Local Galaxy is unavailable"}
    code, result, _ = call("/api/galaxy/status", cookie=cookie, deadline=deadline)
    if code != 200:
      return {"ok": False, "paired": False, "url": "", "error": "Galaxy pairing status is unavailable"}
    paired = result.get("paired") is True
    url = result.get("url") if paired else ""
    if paired and (type(url) is not str or REMOTE_URL.fullmatch(url) is None):
      return {"ok": False, "paired": False, "url": "", "error": "Galaxy pairing status is unavailable"}
    return {"ok": True, "paired": paired, "url": url, "error": ""}
  except (OSError, ValueError, TimeoutError, http.client.HTTPException):
    return {"ok": False, "paired": False, "url": "", "error": "Local Galaxy is unavailable"}
