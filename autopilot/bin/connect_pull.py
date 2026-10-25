#!/usr/bin/env python3
"""Pull Instagram tokens from the Pullshot Connect vault into ~/secrets/ig-<username>.json.
Usage: connect_pull.py --all | --since ISO   Prints accounts without tokens."""
import json, sys, urllib.parse, urllib.request
from common import load_secret, save_secret, NoSecret, now_iso, log

def main():
    since = ""
    if len(sys.argv) > 2 and sys.argv[1] == "--since":
        since = sys.argv[2]
    try:
        cfg = load_secret("connect")
    except NoSecret:
        print(json.dumps({"accounts": [], "error": "no connect.json"})); return
    if not cfg.get("url"):
        print(json.dumps({"accounts": [], "error": "connect url not set yet (J1)"})); return
    q = {"action": "pull", "key": cfg["key"]}
    if since:
        q["since"] = since
    try:
        with urllib.request.urlopen(cfg["url"] + "?" + urllib.parse.urlencode(q), timeout=60) as r:
            js = json.loads(r.read().decode())
    except Exception as e:
        print(json.dumps({"accounts": [], "error": "vault: " + str(e)[:200]})); return
    if js.get("error"):
        print(json.dumps({"accounts": [], "error": "vault: " + js["error"]})); return
    shown = []
    for a in js.get("accounts", []):
        u = a["username"].lower()
        save_secret("ig-" + u, {"username": u, "ig_user_id": str(a.get("user_id") or a.get("id")), "app_scoped_id": str(a.get("id")),
                                "access_token": a["token"], "expires_at": a.get("expiresAt"), "kind": a.get("kind", "pool"),
                                "connected_at": a.get("connectedAt"), "pulled_at": now_iso()})
        shown.append({"username": u, "user_id": str(a.get("user_id") or a.get("id")), "expiresAt": a.get("expiresAt"),
                      "kind": a.get("kind", "pool"), "connectedAt": a.get("connectedAt")})
    log("connect_pull", {"count": len(shown)})
    print(json.dumps({"accounts": shown}, indent=1))

if __name__ == "__main__":
    main()
