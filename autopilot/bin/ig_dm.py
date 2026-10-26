#!/usr/bin/env python3
"""Private replies: one DM to each commenter ("comment anything, link in DMs" format, skand.ai reference).
Usage: ig_dm.py reply <job.json>   job: {"username", "items":[{"commentId","clipId","text"}], "allowUrls":[], "allowHandles":[]}
       ig_dm.py probe <username>   sends nothing; reports whether the token looks able to DM ({"canMessage", "error"})
Instagram "private reply": POST /{ig_user_id}/messages {"recipient":{"comment_id":"..."},"message":{"text":"..."}}.
One DM per comment, within 7 days of the comment, only for comments on the account's own media. Needs the
instagram_business_manage_messages scope on the token; a permission error (kind "permission") means the scope is missing.
State: state/dm-<username>.json {"sent": {commentId: at}}; a commentId already under "sent" is skipped (never two DMs).
Every text passes guard.outbound_ok when guard.py is present (the delivered link goes in allowUrls)."""
import json, sys, time, urllib.request, urllib.error, urllib.parse
from common import api, is_err, ig_secret, GRAPH, NoSecret, read_state, write_state, now_iso, log, emit, TOKEN_CODES
try:
    from guard import outbound_ok
except Exception:  # guard is optional
    outbound_ok = None

def api_json(url, body, token, retries=2):
    """POST a JSON body (common.api is form-encoded). Same return shape as common.api."""
    url = url + "?" + urllib.parse.urlencode({"access_token": token})
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read().decode() or "{}"
                return json.loads(raw) if raw.strip().startswith("{") else {"raw": raw}
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="ignore")
            try:
                err = json.loads(raw).get("error") or {}
            except Exception:
                err = {"message": raw[:300]}
            last = {"error": {"status": e.code, "code": err.get("code"), "subcode": err.get("error_subcode"),
                              "message": str(err.get("message", raw))[:300]}, "kind": "api"}
            if err.get("code") in TOKEN_CODES:
                last["kind"] = "token"
            if e.code < 500:
                return last
        except Exception as e:
            last = {"error": {"status": 0, "code": -1, "message": str(e)[:300]}, "kind": "net"}
        time.sleep(3)
    return last

def classify(err):
    """permission: scope missing (code 10, 200-299, or 'permission' in the text); window: comment too old; else api."""
    code = err.get("code"); msg = (err.get("message") or "").lower()
    if code == 10 or (isinstance(code, int) and 200 <= code <= 299) or "permission" in msg:
        return "permission"
    if any(k in msg for k in ("too old", "outside", "window", "older than", "7 days", "expired")):
        return "window"
    return "api"

def reply(j):
    try:
        s = ig_secret(j["username"])
    except NoSecret:
        return {"error": "token:no-secret"}
    st = read_state(f"dm-{s['username']}.json", {"sent": {}})
    st.setdefault("sent", {})
    res = []
    for it in j.get("items", []):
        cid, clip, text = it["commentId"], it.get("clipId"), it.get("text", "")
        if cid in st["sent"]:
            res.append({"commentId": cid, "clipId": clip, "ok": False, "error": "already sent", "kind": "dup"}); continue
        if not text.strip():
            res.append({"commentId": cid, "clipId": clip, "ok": False, "error": "empty text", "kind": "api"}); continue
        if outbound_ok:
            gok, why = outbound_ok(text, allow_handles=[s["username"]] + list(j.get("allowHandles") or []) + list(it.get("allowHandles") or []),
                                   allow_urls=list(j.get("allowUrls") or []) + list(it.get("allowUrls") or []), allow_price=bool(it.get("allowPrice")))
            if not gok:
                res.append({"commentId": cid, "clipId": clip, "ok": False, "error": "guard: " + why, "kind": "guard"}); continue
        js = api_json(f"{GRAPH}/{s['ig_user_id']}/messages", {"recipient": {"comment_id": cid}, "message": {"text": text}}, s["access_token"])
        if is_err(js):
            e = js["error"]
            res.append({"commentId": cid, "clipId": clip, "ok": False, "error": f"{e.get('code')}:{e.get('message')}"[:200], "kind": js.get("kind") if js.get("kind") == "token" else classify(e)})
            continue
        st["sent"][cid] = now_iso()
        res.append({"commentId": cid, "clipId": clip, "ok": True, "error": None, "kind": None, "messageId": js.get("message_id")})
    write_state(f"dm-{s['username']}.json", st)
    return {"username": s["username"], "results": res, "sent": sum(1 for r in res if r["ok"])}

def probe(username):
    """Read-only: does the token look able to message? GET /me, then GET /{ig_user_id}/conversations?limit=1."""
    try:
        s = ig_secret(username)
    except NoSecret:
        return {"canMessage": False, "error": "token:no-secret"}
    me = api("GET", f"{GRAPH}/me", {"fields": "id,username"}, token=s["access_token"], retries=2)
    if is_err(me):
        return {"canMessage": False, "error": f"me: {me.get('kind')}:{me['error'].get('code')}:{me['error'].get('message')}"[:300]}
    conv = api("GET", f"{GRAPH}/{s['ig_user_id']}/conversations", {"platform": "instagram", "limit": 1}, token=s["access_token"], retries=2)
    if is_err(conv):
        e = conv["error"]
        return {"canMessage": False, "me": me.get("username"), "kind": classify(e), "error": f"conversations: {e.get('code')}:{e.get('message')}"[:300]}
    return {"canMessage": True, "me": me.get("username"), "conversations": len(conv.get("data") or []), "error": None}

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "usage: ig_dm.py reply <job.json> | probe <username>"})); return
    mode = sys.argv[1]
    if mode == "probe":
        o = probe(sys.argv[2]); o["at"] = now_iso(); log("ig_dm", {"mode": "probe", "canMessage": o["canMessage"]}); emit(o); return
    j = json.load(open(sys.argv[2]))
    o = reply(j); o["at"] = now_iso()
    log("ig_dm", {"mode": mode, "sent": o.get("sent", 0), "items": len(j.get("items", []))})
    emit(o, f"dm-{int(time.time())}.json")

if __name__ == "__main__":
    main()
