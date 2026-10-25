#!/usr/bin/env python3
"""Publish Reels / Stories / images / carousels to connected Instagram accounts.
Usage: ig_publish.py <job.json> [--dry-run]
Job: {"jobs":[{"clipId","username","kind":"REELS"|"STORIES"|"IMAGE"|"CAROUSEL","mediaUrl","imageUrl","children":[{"imageUrl"|"mediaUrl"}],
               "caption","coverUrl","collaborators":[],"firstComment","shareToFeed":true,
               "trial":"MANUAL"|"SS_PERFORMANCE" (REELS only: trial reel; if Instagram refuses the trial the job is
               posted once more as a normal Reel and the result carries trialRefused:<message> and trial:false)}]}
   ig_publish.py --whoami <username>  -> followers_count, media_count
Writes ~/autopilot/out/posted-<clipId>.json right after each publish (for reconciliation) and out/publish-<ts>.json."""
import json, os, sys, time
from common import (api, is_err, ig_secret, GRAPH, NoSecret, ffprobe_url, reel_spec_ok, file_hash,
                    read_state, write_state, out, OUT, now_iso, log)

def publish_id(s):
    ids = read_state("ids.json", {})
    return str((ids.get(s["username"]) or {}).get("publishId") or s["ig_user_id"])

def check(j, s, hashes):
    kind = j.get("kind", "REELS")
    url = j.get("mediaUrl") or j.get("imageUrl")
    if kind in ("REELS",) or (kind == "STORIES" and j.get("mediaUrl")):
        p = ffprobe_url(j["mediaUrl"])
        ok, why = reel_spec_ok(p)
        if kind == "STORIES" and not ok and why.startswith("duration") and p.get("duration", 0) <= 60:
            ok = True
        if not ok:
            return "spec:" + why, None
    if url:
        try:
            h = file_hash(url)
        except Exception as e:
            return "fetch:" + str(e)[:120], None
        other = hashes.get(h)
        if other and other != s["username"]:
            return "duplicate:" + other, None
        if other == s["username"] and kind == "REELS" and not j.get("allowRepeat"):
            return "duplicate:same-account", None
        return None, h
    return None, None

def container(j, uid, tok):
    kind = j.get("kind", "REELS")
    if kind == "CAROUSEL":
        kids = []
        for c in j.get("children", []):
            d = {"is_carousel_item": "true"}
            if c.get("mediaUrl"):
                d.update(media_type="VIDEO", video_url=c["mediaUrl"])
            else:
                d["image_url"] = c["imageUrl"]
            r = api("POST", f"{GRAPH}/{uid}/media", data=d, token=tok)
            if is_err(r):
                return r
            kids.append(r["id"])
        for k in kids:
            st = wait(k, tok)
            if st != "FINISHED":
                return {"error": {"message": f"child {st}"}, "kind": "container"}
        d = {"media_type": "CAROUSEL", "children": ",".join(kids), "caption": j.get("caption", "")}
    elif kind == "STORIES":
        d = {"media_type": "STORIES"}
        if j.get("mediaUrl"):
            d["video_url"] = j["mediaUrl"]
        else:
            d["image_url"] = j["imageUrl"]
    elif kind == "IMAGE":
        d = {"image_url": j["imageUrl"], "caption": j.get("caption", "")}
    else:
        d = {"media_type": "REELS", "video_url": j["mediaUrl"], "caption": j.get("caption", ""),
             "share_to_feed": "true" if j.get("shareToFeed", True) else "false"}
        if j.get("coverUrl"):
            d["cover_url"] = j["coverUrl"]
        if j.get("trial") in ("MANUAL", "SS_PERFORMANCE"):
            # trial reel: shown to non-followers first; SS_PERFORMANCE = Instagram shares it to followers if it does well
            d["trial_params"] = json.dumps({"graduation_strategy": j["trial"]})
    if j.get("collaborators") and kind in ("REELS", "IMAGE", "CAROUSEL"):
        d["collaborators"] = json.dumps(j["collaborators"])
    return api("POST", f"{GRAPH}/{uid}/media", data=d, token=tok)

def wait(cid, tok, limit=300):
    t0 = time.time()
    while time.time() - t0 < limit:
        r = api("GET", f"{GRAPH}/{cid}", {"fields": "status_code,status"}, token=tok, retries=3)
        if is_err(r):
            return "ERROR:" + r["error"]["message"][:80]
        sc = r.get("status_code")
        if sc in ("FINISHED", "PUBLISHED"):
            return "FINISHED"
        if sc in ("ERROR", "EXPIRED"):
            return f"{sc}:{r.get('status','')}"[:120]
        time.sleep(10)
    return "TIMEOUT"

def run(j, dry, hashes):
    res = {"clipId": j.get("clipId"), "username": j.get("username"), "kind": j.get("kind", "REELS"), "ok": False}
    try:
        s = ig_secret(j["username"])
    except NoSecret:
        res["error"] = "token:no-secret"; return res
    tok, uid = s["access_token"], publish_id(s)
    err, h = check(j, s, hashes)
    if err:
        res["error"] = err; return res
    lim = api("GET", f"{GRAPH}/{uid}/content_publishing_limit", {"fields": "quota_usage,config"}, token=tok, retries=3)
    if is_err(lim):
        res["error"] = ("token:" if lim.get("kind") == "token" else "limit-check:") + lim["error"]["message"][:100]; return res
    q = ((lim.get("data") or [{}])[0]).get("quota_usage") or 0
    total = (((lim.get("data") or [{}])[0]).get("config") or {}).get("quota_total") or 100
    if q >= total - 5:
        res["error"] = f"limit:{q}/{total}"; return res
    if dry:
        res.update(ok=True, dryRun=True, quota=f"{q}/{total}"); return res
    c = container(j, uid, tok)
    if is_err(c) and j.get("trial") and c.get("kind") != "token":
        # Trial reel refused at container creation. Meta's wording varies (the page may simply not be eligible yet),
        # so ANY non-token error on a trial job counts as a refusal: post it once more as a normal Reel and report
        # trialRefused so the caller can set the account's trialBlockedDate.
        res["trialRefused"] = c["error"]["message"][:160]
        j = {k: v for k, v in j.items() if k != "trial"}
        c = container(j, uid, tok)
    if is_err(c):
        msg = c["error"]["message"][:120]
        res["error"] = ("token:" if c.get("kind") == "token" else "container:") + msg; return res
    cid = c["id"]; res["igContainerId"] = cid
    st = wait(cid, tok)
    if st != "FINISHED" and j.get("trial") and not st.startswith("ERROR:token"):
        # refused while the container was processing: same fallback, once
        res["trialRefused"] = st[:160]
        j = {k: v for k, v in j.items() if k != "trial"}
        c = container(j, uid, tok)
        if is_err(c):
            res["error"] = ("token:" if c.get("kind") == "token" else "container:") + c["error"]["message"][:120]; return res
        cid = c["id"]; res["igContainerId"] = cid
        st = wait(cid, tok)
    if st != "FINISHED":
        res["error"] = "container:" + st; return res
    p = api("POST", f"{GRAPH}/{uid}/media_publish", data={"creation_id": cid}, token=tok)
    if is_err(p):
        res["error"] = "publish:" + p["error"]["message"][:120]; return res
    mid = p["id"]
    out(os.path.join(OUT, f"posted-{j.get('clipId') or mid}.json"), {"clipId": j.get("clipId"), "username": s["username"], "igMediaId": mid, "at": now_iso()})
    if h:
        hashes[h] = s["username"]; write_state("hashes.json", hashes)
    info = api("GET", f"{GRAPH}/{mid}", {"fields": "permalink,timestamp,media_type"}, token=tok, retries=3)
    res.update(ok=True, igMediaId=mid, permalink=None if is_err(info) else info.get("permalink"),
               postedAt=now_iso() if is_err(info) else info.get("timestamp"),
               trial=(j.get("trial") or False))   # the strategy actually used, False after a refusal
    if j.get("firstComment") and j.get("kind", "REELS") != "STORIES":
        cm = api("POST", f"{GRAPH}/{mid}/comments", data={"message": j["firstComment"]}, token=tok, retries=2)
        res["firstComment"] = "error" if is_err(cm) else "ok"
    return res

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"results": [], "error": "usage"})); return
    if sys.argv[1] == "--whoami":
        s = ig_secret(sys.argv[2]); tok, uid = s["access_token"], publish_id(s)
        info = api("GET", f"{GRAPH}/{uid}", {"fields": "username,followers_count,media_count"}, token=tok, retries=3)
        print(json.dumps({"error": info["error"]["message"][:150]} if is_err(info) else info)); return
    dry = "--dry-run" in sys.argv
    jobs = json.load(open(sys.argv[1])).get("jobs", [])
    hashes = read_state("hashes.json", {})
    results = []
    for j in jobs:
        try:
            r = run(j, dry, hashes)
        except Exception as e:
            r = {"clipId": j.get("clipId"), "ok": False, "error": "crash:" + str(e)[:150]}
        results.append(r)
        log("ig_publish", {k: r.get(k) for k in ("clipId", "username", "ok", "error", "igMediaId")})
    o = {"at": now_iso(), "dryRun": dry, "results": results}
    out(os.path.join(OUT, f"publish-{int(time.time())}.json"), o)
    print(json.dumps(o, indent=1))

if __name__ == "__main__":
    main()
