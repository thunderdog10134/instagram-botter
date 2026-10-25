#!/usr/bin/env python3
"""Read post insights. Usage: ig_insights.py <job.json>
Job: {"items":[{"clipId","username","igMediaId","postedAt","kind":"REELS"|"STORIES"|"IMAGE"|"CAROUSEL"}]}"""
import json, sys, time, calendar
from common import api, is_err, ig_secret, GRAPH, NoSecret, REELS_METRICS, STORY_METRICS, IMAGE_METRICS, now_iso, log, emit

def age_hours(iso):
    try:
        return round((time.time() - calendar.timegm(time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S"))) / 3600, 1)
    except Exception:
        return None

def read(item):
    r = {"clipId": item.get("clipId"), "igMediaId": item.get("igMediaId"), "ageHours": age_hours(item.get("postedAt") or "")}
    try:
        s = ig_secret(item["username"])
    except NoSecret:
        r["error"] = "token:no-secret"; return r
    kind = item.get("kind", "REELS")
    metrics = STORY_METRICS if kind == "STORIES" else (IMAGE_METRICS if kind in ("IMAGE", "CAROUSEL") else REELS_METRICS)
    js = api("GET", f"{GRAPH}/{item['igMediaId']}/insights", {"metric": ",".join(metrics)}, token=s["access_token"], retries=3)
    if is_err(js) and js.get("kind") == "api":
        # drop metrics one by one if a name was rejected (Meta renames metrics)
        good = {}
        for m in metrics:
            one = api("GET", f"{GRAPH}/{item['igMediaId']}/insights", {"metric": m}, token=s["access_token"], retries=2)
            if not is_err(one):
                for d in one.get("data", []):
                    good[d["name"]] = (d.get("values") or [{}])[0].get("value", d.get("total_value", {}).get("value"))
            else:
                r.setdefault("badMetrics", []).append(m)
        js = {"data": [{"name": k, "values": [{"value": v}]} for k, v in good.items()]} if good else js
    if is_err(js):
        r["error"] = js.get("kind", "api") + ":" + js["error"]["message"][:120]; return r
    vals = {}
    for d in js.get("data", []):
        v = (d.get("values") or [{}])[0].get("value")
        if v is None:
            v = (d.get("total_value") or {}).get("value")
        vals[d["name"]] = v
    r.update(views=vals.get("views"), reach=vals.get("reach"), likes=vals.get("likes"), comments=vals.get("comments"),
             shares=vals.get("shares"), saves=vals.get("saved"), replies=vals.get("replies"),
             avgWatchMs=vals.get("ig_reels_avg_watch_time"), totalWatchMs=vals.get("ig_reels_video_view_total_time"))
    return r

def main():
    items = json.load(open(sys.argv[1])).get("items", []) if len(sys.argv) > 1 else []
    results = []
    for it in items:
        try:
            results.append(read(it))
        except Exception as e:
            results.append({"clipId": it.get("clipId"), "error": "crash:" + str(e)[:150]})
    log("ig_insights", {"n": len(results), "errors": sum(1 for x in results if x.get("error"))})
    emit({"at": now_iso(), "results": results}, f"insights-{int(time.time())}.json")

if __name__ == "__main__":
    main()
