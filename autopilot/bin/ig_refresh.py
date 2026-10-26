#!/usr/bin/env python3
"""Refresh long-lived Instagram tokens and push them back to the vault.
Usage: ig_refresh.py --all [--min-age-days N]"""
import json, sys, time, calendar, urllib.request
from common import api, is_err, ig_accounts, save_secret, load_secret, NoSecret, now_iso, log, emit

def main():
    min_age = 7.0
    if "--min-age-days" in sys.argv:
        min_age = float(sys.argv[sys.argv.index("--min-age-days") + 1])
    try:
        vault = load_secret("connect")
    except NoSecret:
        vault = {}
    results = []
    for s in ig_accounts():
        r = {"username": s["username"]}
        last = s.get("refreshed_at") or s.get("connected_at") or s.get("pulled_at") or ""
        try:
            age = (time.time() - calendar.timegm(time.strptime(last[:19], "%Y-%m-%dT%H:%M:%S"))) / 86400
        except Exception:
            age = 999
        try:
            left = (calendar.timegm(time.strptime((s.get("expires_at") or "")[:19], "%Y-%m-%dT%H:%M:%S")) - time.time()) / 86400
        except Exception:
            left = 0
        if age < min_age and left > 10:
            r.update(refreshed=False, skipped="young", expiresAt=s.get("expires_at")); results.append(r); continue
        js = api("GET", "https://graph.instagram.com/refresh_access_token", {"grant_type": "ig_refresh_token"}, token=s["access_token"], retries=3)
        if is_err(js):
            r.update(refreshed=False, error=js.get("kind", "api") + ":" + js["error"]["message"][:120]); results.append(r); continue
        exp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + int(js.get("expires_in", 5184000))))
        s.update(access_token=js["access_token"], expires_at=exp, refreshed_at=now_iso())
        save_secret("ig-" + s["username"], s)
        r.update(refreshed=True, expiresAt=exp)
        if vault.get("url"):
            try:
                body = json.dumps({"action": "update", "key": vault["key"], "username": s["username"], "token": js["access_token"], "expiresAt": exp}).encode()
                req = urllib.request.Request(vault["url"], data=body, method="POST", headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    v = json.loads(resp.read().decode() or "{}")
                r["vault"] = "ok" if v.get("ok") else ("error:" + str(v)[:80])
            except Exception as e:
                r["vault"] = "error:" + str(e)[:80]
        results.append(r)
    log("ig_refresh", {"n": len(results)})
    emit({"at": now_iso(), "results": results}, f"refresh-{int(time.time())}.json")

if __name__ == "__main__":
    main()
