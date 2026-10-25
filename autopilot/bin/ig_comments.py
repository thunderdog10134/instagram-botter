#!/usr/bin/env python3
"""Fetch new comments, or reply/hide.
Usage: ig_comments.py fetch <job.json>   job: {"items":[{"clipId","username","igMediaId"}]}
       ig_comments.py act <job.json>     job: {"username", "replies":[{"commentId","message", "allowHandles":[], "allowUrls":[], "allowPrice":false}], "hide":["commentId"], "allowHandles":[], "allowUrls":[]}
Every reply passes guard.outbound_ok before it is sent (no foreign urls/mentions, no secrets, no phishing or price text, <= 300 chars); a refused reply is reported as error "guard: <why>" and never sent."""
import json, sys, time
from common import api, is_err, ig_secret, GRAPH, NoSecret, read_state, write_state, now_iso, log, emit
from guard import outbound_ok, clean_inbound

def fetch(items):
    out = []
    for it in items:
        try:
            s = ig_secret(it["username"])
        except NoSecret:
            out.append({"clipId": it.get("clipId"), "error": "token:no-secret"}); continue
        st = read_state(f"comments-{s['username']}.json", {"seen": {}, "replied": {}})
        js = api("GET", f"{GRAPH}/{it['igMediaId']}/comments", {"fields": "id,text,username,timestamp,hidden,replies{id,username}", "limit": 50}, token=s["access_token"], retries=3)
        if is_err(js):
            out.append({"clipId": it.get("clipId"), "error": js.get("kind", "api") + ":" + js["error"]["message"][:100]}); continue
        for c in js.get("data", []):
            if c["id"] in st["seen"]:
                continue
            st["seen"][c["id"]] = c.get("timestamp")
            if (c.get("username") or "").lower() == s["username"]:
                continue
            ours = any((r.get("username") or "").lower() == s["username"] for r in (c.get("replies") or {}).get("data", []))
            out.append({"clipId": it.get("clipId"), "username": s["username"], "commentId": c["id"], "text": clean_inbound(c.get("text", "")),
                        "by": c.get("username"), "at": c.get("timestamp"), "hidden": c.get("hidden"), "alreadyReplied": ours or c["id"] in st["replied"]})
        write_state(f"comments-{s['username']}.json", st)
    return {"comments": out}

def act(j):
    res = {"replies": [], "hidden": []}
    try:
        s = ig_secret(j["username"])
    except NoSecret:
        return {"error": "token:no-secret"}
    st = read_state(f"comments-{s['username']}.json", {"seen": {}, "replied": {}})
    today = time.strftime("%Y-%m-%d")
    sent_today = set(m for cid, (d, m) in st.get("replyText", {}).items() if d == today) if st.get("replyText") else set()
    st.setdefault("replyText", {})
    for r in j.get("replies", []):
        if r["commentId"] in st["replied"]:
            res["replies"].append({"commentId": r["commentId"], "ok": False, "error": "already replied"}); continue
        if r["message"].strip().lower() in sent_today:
            res["replies"].append({"commentId": r["commentId"], "ok": False, "error": "same text already used today"}); continue
        gok, why = outbound_ok(r["message"], allow_handles=[s["username"]] + list(j.get("allowHandles") or []) + list(r.get("allowHandles") or []),
                               allow_urls=list(j.get("allowUrls") or []) + list(r.get("allowUrls") or []), allow_price=bool(r.get("allowPrice")))
        if not gok:
            res["replies"].append({"commentId": r["commentId"], "ok": False, "error": "guard: " + why}); continue
        js = api("POST", f"{GRAPH}/{r['commentId']}/replies", data={"message": r["message"]}, token=s["access_token"], retries=2)
        ok = not is_err(js)
        if ok:
            st["replied"][r["commentId"]] = now_iso()
            st["replyText"][r["commentId"]] = [today, r["message"].strip().lower()]
            sent_today.add(r["message"].strip().lower())
        res["replies"].append({"commentId": r["commentId"], "ok": ok, "error": None if ok else js["error"]["message"][:100]})
    for cid in j.get("hide", []):
        js = api("POST", f"{GRAPH}/{cid}", data={"hide": "true"}, token=s["access_token"], retries=2)
        res["hidden"].append({"commentId": cid, "ok": not is_err(js)})
    write_state(f"comments-{s['username']}.json", st)
    return res

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "usage"})); return
    mode, j = sys.argv[1], json.load(open(sys.argv[2]))
    o = fetch(j.get("items", [])) if mode == "fetch" else act(j)
    o["at"] = now_iso()
    log("ig_comments", {"mode": mode})
    emit(o, f"comments-{mode}-{int(time.time())}.json")

if __name__ == "__main__":
    main()
