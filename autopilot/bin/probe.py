#!/usr/bin/env python3
"""Check each connected Instagram account. Usage: probe.py <username> | --all"""
import json, sys, time
from common import api, is_err, ig_accounts, ig_secret, GRAPH, NoSecret, write_state, read_state

def probe(s):
    tok = s["access_token"]
    me = api("GET", f"{GRAPH}/me", {"fields": "id,user_id,username,account_type"}, token=tok, retries=2)
    if is_err(me):
        return {"username": s["username"], "ok": False, "error": me.get("kind", "api"), "detail": me["error"]["message"]}
    uid = str(me.get("user_id") or me.get("id"))
    lim = api("GET", f"{GRAPH}/{uid}/content_publishing_limit", {"fields": "quota_usage,config"}, token=tok, retries=2)
    idnote = "user_id"
    if is_err(lim) and me.get("id") and str(me["id"]) != uid:
        lim2 = api("GET", f"{GRAPH}/{me['id']}/content_publishing_limit", {"fields": "quota_usage,config"}, token=tok, retries=2)
        if not is_err(lim2):
            lim, uid, idnote = lim2, str(me["id"]), "id"
    exp = s.get("expires_at")
    days = None
    if exp:
        try:
            days = round((time.mktime(time.strptime(exp[:19], "%Y-%m-%dT%H:%M:%S")) - time.time()) / 86400, 1)
        except Exception:
            pass
    q = None
    if not is_err(lim):
        d = (lim.get("data") or [{}])[0]
        q = d.get("quota_usage")
    ids = read_state("ids.json", {})
    ids[s["username"]] = {"publishId": uid, "which": idnote}
    write_state("ids.json", ids)
    return {"username": me.get("username", s["username"]), "ok": True, "user_id": uid, "id_used": idnote,
            "account_type": me.get("account_type"), "quota_usage": q, "expires_in_days": days,
            "limit_error": lim["error"]["message"] if is_err(lim) else None}

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "--all"
    if target == "--all":
        accts = ig_accounts()
    else:
        try:
            accts = [ig_secret(target)]
        except NoSecret:
            print(json.dumps([{"username": target, "ok": False, "error": "no secret"}])); return
    print(json.dumps([probe(s) for s in accts], indent=1))

if __name__ == "__main__":
    main()
