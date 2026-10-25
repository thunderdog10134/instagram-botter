#!/usr/bin/env python3
"""Kick / Twitch replay source for Clip Autopilot.
  streams.py kick list <slug> [n]          -> JSON list of recent replays (title, seconds, uuid, source m3u8, created)
  streams.py kick cut <slug> <uuid> <start_s> <len_s> <out.mp4>
  streams.py twitch list <login> [n]       -> JSON list of past broadcasts (id, title, seconds, url)
  streams.py twitch cut <vod_url> <start_s> <len_s> <out.mp4>
  streams.py kick search <word>            -> channels matching a word
Gambling-sponsored streams (title/slug mentions stake, casino, slots, gamble, wager, bet, roobet, rollbit) are
flagged "excluded": "gambling" and must not be cut (Josh's rule, Oct 24).
Never bypass a block: a refused download is reported as {"error": ...}, nothing else is tried.
"""
import json, os, re, subprocess, sys, urllib.request

UA = {"User-Agent": "Mozilla/5.0"}
GAMBLE = re.compile(r"\b(stake|casino|slots?|gambl\w*|wager\w*|bet(ting)?|roobet|rollbit|shuffle\.com)\b|onlyf\w*|\bnsfw\b", re.I)   # + adult-content mentions

def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode())

def kick_list(slug, n=10):
    d = get(f"https://kick.com/api/v2/channels/{slug}/videos")
    vs = d if isinstance(d, list) else d.get("data", [])
    out = []
    for v in vs[:n]:
        title = v.get("session_title") or ""
        item = {"platform": "kick", "channel": slug, "title": title,
                "seconds": int((v.get("duration") or 0) / 1000), "uuid": (v.get("video") or {}).get("uuid"),
                "source": v.get("source"), "created": v.get("created_at"),
                "url": f"https://kick.com/{slug}/videos/{v.get('slug')}"}
        if GAMBLE.search(title) or GAMBLE.search(slug):
            item["excluded"] = "gambling"
        out.append(item)
    return out

def kick_search(word):
    d = get(f"https://kick.com/api/search?searched_word={urllib.request.quote(word)}")
    out = []
    for c in d.get("channels", []):
        slug = c.get("slug")
        item = {"slug": slug, "followers": c.get("followersCount") or c.get("followers_count")}
        if GAMBLE.search(slug or ""):
            item["excluded"] = "gambling"
        out.append(item)
    return out

def cut(src, start, length, out):
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(start), "-t", str(length), "-i", src, "-c", "copy", out]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        return {"error": (p.stderr or "ffmpeg failed")[:300]}
    return {"ok": True, "out": out}

def twitch_list(login, n=10):
    cmd = ["python3", "-m", "yt_dlp", "--no-warnings", "--flat-playlist", "--playlist-end", str(n),
           "--print", "%(id)s\t%(title)s\t%(duration)s", f"https://www.twitch.tv/{login}/videos?filter=archives&sort=time"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    out = []
    for line in p.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3 or "Permission error" in line:
            continue
        item = {"platform": "twitch", "channel": login, "id": parts[0], "title": parts[1],
                "seconds": int(float(parts[2])) if parts[2] not in ("NA", "") else 0,
                "url": f"https://www.twitch.tv/videos/{parts[0].lstrip('v')}"}
        if GAMBLE.search(parts[1]) or GAMBLE.search(login):
            item["excluded"] = "gambling"
        out.append(item)
    if not out and p.stderr and "ERROR" in p.stderr:
        return {"error": p.stderr.strip().splitlines()[-1][:300]}
    return out

def twitch_cut(url, start, length, out, quality="720p60"):
    """Oct 25 (Fable): yt-dlp --download-sections writes an empty file for Twitch VODs (fragmented-mp4 HLS), so the slice is
    cut by hls_slice.py from the playlist url: only the segments that cover the window are fetched (~20 s for 20 min)."""
    g = subprocess.run(["python3", "-m", "yt_dlp", "--no-warnings", "-g", "-f", f"{quality}/best[height<=720]/best", url],
                       capture_output=True, text=True, timeout=120)
    m3u8 = (g.stdout.strip().splitlines() or [""])[0]
    if g.returncode != 0 or not m3u8.startswith("http"):
        return {"error": (g.stderr or "no playlist url").strip().splitlines()[-1][:300]}
    here = os.path.dirname(os.path.abspath(__file__))
    p = subprocess.run(["python3", os.path.join(here, "hls_slice.py"), m3u8, str(int(start)), str(int(length)), out],
                       capture_output=True, text=True, timeout=900)
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        return {"error": (p.stderr or p.stdout or "hls_slice failed").strip()[-300:]}

def main():
    a = sys.argv[1:]
    try:
        if a[:2] == ["kick", "list"]:
            print(json.dumps(kick_list(a[2], int(a[3]) if len(a) > 3 else 10), indent=1))
        elif a[:2] == ["kick", "search"]:
            print(json.dumps(kick_search(a[2]), indent=1))
        elif a[:2] == ["kick", "cut"]:
            slug, uuid, start, length, out = a[2:7]
            v = next((x for x in kick_list(slug, 50) if x["uuid"] == uuid), None)
            if not v:
                print(json.dumps({"error": "replay not found"})); return
            if v.get("excluded"):
                print(json.dumps({"error": "excluded: " + v["excluded"]})); return
            print(json.dumps(cut(v["source"], start, length, out)))
        elif a[:2] == ["twitch", "list"]:
            print(json.dumps(twitch_list(a[2], int(a[3]) if len(a) > 3 else 10), indent=1))
        elif a[:2] == ["twitch", "cut"]:
            print(json.dumps(twitch_cut(a[2], a[3], a[4], a[5])))
        else:
            print(__doc__)
    except Exception as e:
        print(json.dumps({"error": str(e)[:300]}))

if __name__ == "__main__":
    main()
