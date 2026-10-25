#!/usr/bin/env python3
"""Channel registry + trend-weighted random picker for Clip Autopilot (Josh, Oct 25: "make a list of 200 channels and
randomly pick from them depending on which ones are blowing up more or less, based on trend charts").
State: ~/autopilot/state/channels.json  {"channels":[...], "updatedAt"}  (mirrored to the board: knowledge/clip-channels)
  channels.py import <file.jsonl|json> [...]   merge research rows (dedupe by platform+handle; never drops a channel)
  channels.py probe [--platform kick|twitch] [--limit 60] [--stale-hours 20]
        live check of public numbers: Kick API (followers, live viewers, replays in the last 7 days, replay resolution);
        Twitch via yt-dlp (past broadcasts kept or not). Appends a dated snapshot to each channel's history (keeps 30).
  channels.py score                           recompute trend scores (see below) without probing
  channels.py pick <n> [--exclude a,b] [--seed N]   weighted random pick of n clippable channels (JSON)
  channels.py report [--top 30]               table for humans; JSON with counts
  channels.py set <platform:handle> key=value [...]   manual fields (status=stop, clippable=no, note=...)
Score (0..1) = 0.40 heat (log of live/average viewers vs the registry) + 0.35 growth (follower change per day over
the last snapshots, or the tracker's 30-day trend when no history yet) + 0.15 activity (replays in the last 3/7 days)
+ 0.10 quality (1080p replays 1.0, 720p 0.6, lower 0.2). pick() weight = 0.01 + score**4, so hot channels come up
most but cold ones still get an occasional turn (exploration). Only status in (clipping,new,ok) and clippable "yes"
are picked; "stop"/"declined"/"excluded"/"review" never, nor channels whose recent titles are not English (lang "non-en": captions and hooks are English), nor any with adult-content or gambling mentions in titles. Gambling-sponsored channels are excluded on import and on probe.
Never bypasses a block: a refused fetch is recorded as probeError and the channel just scores lower."""
import json, math, os, random, re, subprocess, sys, time, urllib.request, datetime
ST = os.path.expanduser("~/autopilot/state/channels.json")
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
GAMBLE = re.compile(r"\b(stake|casino|slots?|gambl\w*|wager\w*|betting|roobet|rollbit|shuffle\.com)\b", re.I)
ADULT = re.compile(r"(onlyf\w*|\bnsfw\b|\b18\+)", re.I)
NON_EN = re.compile(r"(\b(med|och|dag|sverige|svensk\w*|norsk\w*|dansk\w*|hele|idag|kväll|afen|heute|abend|mit|und|der|die|das|öffnen|español|hoy|noche|abrimos|abertura|hoje|noite|loja|fechada|aujourd|ouverture|soirée|avec|vandaag|avond|openen|kaarten|gratis|verzending|aanbieding)\b|\.(nl|dk|no|se|de|fr|es|pt)\b|\[(PT|ES|BR|DE|FR|NL|DK|NO|SE)\b)", re.I)
EN = re.compile(r"\b(the|and|with|break|breaks|pack|packs|opening|live|cards?|rips?|ripping|giveaways?|case|box|boxes|night|hobby|pulls?|chase|friday|sunday|today)\b", re.I)

def lang_and_flags(c, titles):
    titles = [t for t in titles if t]
    if not titles:
        return
    c["lastTitles"] = titles[:3]
    non = sum(1 for t in titles if NON_EN.search(t)) / len(titles)
    c["lang"] = "non-en" if non >= 0.5 else "en"      # English unless the titles say otherwise; FACTORY still checks the speech
    if any(ADULT.search(t) for t in titles):
        c["status"] = "excluded"; c["why"] = "adult-content mention in stream titles"
    if any(GAMBLE.search(t) for t in titles):
        c["status"] = "excluded"; c["why"] = "gambling in stream titles"
CLIPPABLE_PLATFORMS = {"kick": "yes", "twitch": "unknown"}   # youtube: bot check from the sandbox; whatnot/tiktok/fanatics/loupe: no public replay download

def now():
    return datetime.datetime.now(datetime.timezone.utc)

def iso(t=None):
    return (t or now()).strftime("%Y-%m-%dT%H:%M:%SZ")

def load():
    try:
        return json.load(open(ST))
    except Exception:
        return {"channels": []}

def save(d):
    d["updatedAt"] = iso(); os.makedirs(os.path.dirname(ST), exist_ok=True)
    tmp = ST + ".tmp"; json.dump(d, open(tmp, "w"), indent=0); os.replace(tmp, ST)

def key(c):
    return f"{c['platform']}:{c['handle'].lstrip('@').lower()}"

def get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def num(v):
    try:
        if v is None or v == "":
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).replace(",", "").strip().upper()
        m = re.match(r"([\d.]+)\s*([KM]?)", s)
        if not m:
            return None
        return float(m.group(1)) * {"": 1, "K": 1e3, "M": 1e6}[m.group(2)]
    except Exception:
        return None

def cmd_import(paths):
    d = load(); idx = {key(c): c for c in d["channels"]}; added = merged = 0
    for p in paths:
        txt = open(p).read().strip()
        rows = json.loads(txt) if txt.startswith("[") else [json.loads(l) for l in txt.splitlines() if l.strip().startswith("{")]
        for r in rows:
            if not r.get("platform") or not r.get("handle"):
                continue
            r["platform"] = r["platform"].lower().strip(); r["handle"] = r["handle"].strip().lstrip("@")
            k = key(r)
            if k in idx:
                c = idx[k]
                for f, v in r.items():
                    if v not in (None, "", []) and c.get(f) in (None, "", []):
                        c[f] = v
                merged += 1; continue
            c = {"id": k, "platform": r["platform"], "handle": r["handle"], "url": r.get("url"), "name": r.get("name"),
                 "niche": r.get("niche"), "followers": num(r.get("followers")), "avgViewers": num(r.get("avgViewers")),
                 "trend": r.get("trend"), "growth30d": r.get("growth30d"), "instagram": r.get("instagram"),
                 "alsoStreamsOn": r.get("alsoStreamsOn"), "evidence": r.get("evidence"), "addedAt": iso(),
                 "status": r.get("status") or "new", "clippable": CLIPPABLE_PLATFORMS.get(r["platform"], "no"), "history": []}
            if r.get("why"):
                c["why"] = r["why"]
            if c["clippable"] == "no" and not c.get("why"):
                c["why"] = {"youtube": "YouTube asks for a sign-in (bot check) from our sandbox; we never work around it. Usable only if the creator sends footage.",
                            }.get(c["platform"], "no public replay download on this platform; usable only if the creator sends footage")
            if GAMBLE.search(" ".join(str(r.get(f) or "") for f in ("handle", "name", "notes"))):
                c["status"] = "excluded"; c["why"] = "gambling"
            idx[k] = c; d["channels"].append(c); added += 1
    save(d); print(json.dumps({"added": added, "merged": merged, "total": len(d["channels"])}))

def kick_probe(c):
    slug = c["handle"].lower()
    ch = get(f"https://kick.com/api/v2/channels/{slug}")
    snap = {"at": iso(), "followers": ch.get("followers_count") or ch.get("followersCount"),
            "live": bool(ch.get("livestream")), "viewers": (ch.get("livestream") or {}).get("viewer_count")}
    u = ch.get("user") or {}
    if u.get("instagram") and not c.get("instagram"):
        c["instagram"] = u.get("instagram")
    if GAMBLE.search(json.dumps(ch.get("livestream") or {})[:4000] + " " + (ch.get("slug") or "")):
        c["status"] = "excluded"; c["why"] = "gambling (stream title/category)"
    try:
        vs = get(f"https://kick.com/api/v2/channels/{slug}/videos")
        vs = vs if isinstance(vs, list) else vs.get("data", [])
    except Exception:
        vs = []
    t = now(); r3 = r7 = 0; views = []
    for v in vs[:30]:
        try:
            ts = datetime.datetime.fromisoformat((v.get("created_at") or "").replace("Z", "+00:00").replace(" ", "T"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=datetime.timezone.utc)
            age = (t - ts).total_seconds() / 86400
            r3 += age <= 3; r7 += age <= 7
        except Exception:
            pass
        if v.get("views") is not None:
            views.append(v.get("views"))
        if GAMBLE.search(v.get("session_title") or ""):
            c["gambleTitles"] = c.get("gambleTitles", 0) + 1
    snap.update(replays3d=r3, replays7d=r7, replayViews=round(sum(views) / len(views), 1) if views else None)
    lang_and_flags(c, [v.get("session_title") or "" for v in vs[:8]])
    if vs and vs[0].get("source") and not c.get("maxRes"):
        try:
            m3 = urllib.request.urlopen(urllib.request.Request(vs[0]["source"], headers=UA), timeout=20).read().decode()
            hs = [int(h) for h in re.findall(r"RESOLUTION=\d+x(\d+)", m3)]
            c["maxRes"] = max(hs) if hs else None
        except Exception:
            pass
    c["clippable"] = "yes" if vs else "no"
    if not vs:
        c["why"] = "no replays kept"
    elif c.get("why") == "no replays kept":
        c.pop("why", None)
    return snap

def twitch_probe(c):
    p = subprocess.run([sys.executable, "-m", "yt_dlp", "--no-warnings", "--flat-playlist", "--playlist-end", "8", "--print",
                        "%(id)s\t%(duration)s\t%(timestamp)s\t%(view_count)s\t%(title)s",
                        f"https://www.twitch.tv/{c['handle']}/videos?filter=archives&sort=time"],
                       capture_output=True, text=True, timeout=90, stdin=subprocess.DEVNULL)
    rows = [l.split("\t") for l in p.stdout.splitlines() if l.count("\t") >= 3]
    t = time.time(); r3 = sum(1 for r in rows if r[2] not in ("NA", "") and t - float(r[2]) < 3 * 86400)
    r7 = sum(1 for r in rows if r[2] not in ("NA", "") and t - float(r[2]) < 7 * 86400)
    vw = [float(r[3]) for r in rows if r[3] not in ("NA", "")]
    if rows and all(r[2] in ("NA", "") for r in rows):
        r3 = r7 = None          # the flat Twitch listing gives no dates: recency unknown, only "replays kept"
    lang_and_flags(c, [r[4] if len(r) > 4 else "" for r in rows])
    c["clippable"] = "yes" if rows else "no"
    if not rows:
        c["why"] = "no past broadcasts kept" if p.returncode == 0 else (p.stderr.strip().splitlines() or ["twitch list failed"])[-1][:160]
    elif str(c.get("why", "")).startswith(("no past broadcasts", "ERROR")):
        c.pop("why", None)
    return {"at": iso(), "replays3d": r3, "replays7d": r7, "replayViews": round(sum(vw) / len(vw), 1) if vw else None,
            "followers": None, "live": None, "viewers": None}

def cmd_probe(args):
    plat = args[args.index("--platform") + 1] if "--platform" in args else None
    lim = int(args[args.index("--limit") + 1]) if "--limit" in args else 60
    stale = float(args[args.index("--stale-hours") + 1]) if "--stale-hours" in args else 20
    d = load(); done = errs = 0
    cands = [c for c in d["channels"] if c["platform"] in ("kick", "twitch") and (not plat or c["platform"] == plat)
             and c.get("status") not in ("excluded", "stop", "declined")]
    def last(c):
        h = c.get("history") or []
        return h[-1]["at"] if h else ""
    cands.sort(key=last)
    for c in cands:
        if done >= lim:
            break
        if last(c) and (now() - datetime.datetime.fromisoformat(last(c).replace("Z", "+00:00"))).total_seconds() < stale * 3600:
            continue
        try:
            s = kick_probe(c) if c["platform"] == "kick" else twitch_probe(c)
            c.setdefault("history", []).append(s); c["history"] = c["history"][-30:]
            c["lastChecked"] = s["at"]; c.pop("probeError", None)
            s["followers"] = num(s.get("followers")); s["viewers"] = num(s.get("viewers")); s["replayViews"] = num(s.get("replayViews"))
            if s.get("followers"):
                c["followers"] = s["followers"]
        except Exception as e:
            c["probeError"] = str(e)[:160]; c["lastChecked"] = iso(); errs += 1
        done += 1
        if done % 10 == 0:
            save(d)
        time.sleep(0.6)
    score(d); save(d)
    print(json.dumps({"probed": done, "errors": errs, "clippableYes": sum(1 for c in d["channels"] if c.get("clippable") == "yes")}))

def score(d):
    chans = d["channels"]
    def heat_raw(c):
        h = [x for x in (c.get("history") or []) if x.get("viewers")]
        v = max([x["viewers"] for x in h[-7:]] or [0]) or c.get("avgViewers") or 0
        rv = [x.get("replayViews") for x in (c.get("history") or [])[-3:] if x.get("replayViews")]
        return math.log10(1 + max(num(v) or 0, (num(rv[-1]) / 3) if rv and num(rv[-1]) else 0, (num(c.get("followers")) or 0) / 200))
    hmax = max([heat_raw(c) for c in chans] or [1]) or 1
    for c in chans:
        heat = heat_raw(c) / hmax
        hs = [x for x in (c.get("history") or []) if x.get("followers")]
        growth = None
        if len(hs) >= 2:
            a, b = hs[0], hs[-1]
            days = max(0.5, (datetime.datetime.fromisoformat(b["at"].replace("Z", "+00:00")) -
                             datetime.datetime.fromisoformat(a["at"].replace("Z", "+00:00"))).total_seconds() / 86400)
            fa, fb = num(a["followers"]) or 0, num(b["followers"]) or 0
            pct_day = (fb - fa) / max(fa, 50) / days * 100
            growth = max(0.0, min(1.0, 0.5 + pct_day / 2))      # +1 %/day -> 1.0, flat -> 0.5, -1 %/day -> 0
        if growth is None:
            growth = {"up": 0.8, "flat": 0.5, "down": 0.25}.get((c.get("trend") or "").lower(), 0.5)
        last = (c.get("history") or [{}])[-1]
        if c.get("history") and last.get("replays7d") is None and c.get("clippable") == "yes":
            act = 0.6
        else:
            act = 1.0 if last.get("replays3d") else 0.6 if last.get("replays7d") else (0.3 if not c.get("history") else 0.0)
        mr = c.get("maxRes") or 0
        qual = 1.0 if mr >= 1080 else 0.6 if mr >= 720 else 0.2 if mr else 0.5
        c["score"] = round(0.40 * heat + 0.35 * growth + 0.15 * act + 0.10 * qual, 3)
        c["scoreParts"] = {"heat": round(heat, 2), "growth": round(growth, 2), "activity": act, "quality": qual}

def pickable(c):
    return (c.get("clippable") == "yes" and c.get("status") in ("new", "ok", "clipping") and not c.get("probeError")
            and c.get("lang") != "non-en")

def cmd_pick(args):
    n = int(args[0]); ex = set(args[args.index("--exclude") + 1].lower().split(",")) if "--exclude" in args else set()
    rnd = random.Random(int(args[args.index("--seed") + 1])) if "--seed" in args else random.Random()
    d = load(); score(d)
    pool = [c for c in d["channels"] if pickable(c) and c["handle"].lower() not in ex]
    total = len(pool); out = []
    while pool and len(out) < n:
        w = [0.01 + (c.get("score") or 0) ** 4 for c in pool]
        c = rnd.choices(pool, weights=w, k=1)[0]; pool.remove(c)
        out.append({"platform": c["platform"], "handle": c["handle"], "score": c.get("score"), "maxRes": c.get("maxRes"),
                    "instagram": c.get("instagram"), "name": c.get("name"), "parts": c.get("scoreParts")})
    print(json.dumps({"picked": out, "pool": total}))

def cmd_report(args):
    top = int(args[args.index("--top") + 1]) if "--top" in args else 30
    d = load(); score(d); save(d); ch = d["channels"]
    by = {}
    for c in ch:
        by.setdefault(c["platform"], 0); by[c["platform"]] += 1
    rows = sorted(ch, key=lambda c: -(c.get("score") or 0))[:top]
    print(json.dumps({"total": len(ch), "byPlatform": by, "clippable": sum(1 for c in ch if pickable(c)),
                      "top": [{"id": c["id"], "score": c.get("score"), "clippable": c.get("clippable"), "status": c.get("status"),
                               "followers": c.get("followers"), "maxRes": c.get("maxRes")} for c in rows]}, indent=0))

def cmd_set(args):
    d = load(); k = args[0].lower(); hit = [c for c in d["channels"] if c["id"] == k]
    if not hit:
        print(json.dumps({"error": "not found"})); return
    for kv in args[1:]:
        f, v = kv.split("=", 1); hit[0][f] = v
    save(d); print(json.dumps({"ok": True, "id": k}))

if __name__ == "__main__":
    a = sys.argv[1:]
    {"import": lambda: cmd_import(a[1:]), "probe": lambda: cmd_probe(a[1:]), "score": lambda: (lambda d: (score(d), save(d), print(json.dumps({"ok": True}))))(load()),
     "pick": lambda: cmd_pick(a[1:]), "report": lambda: cmd_report(a[1:]), "set": lambda: cmd_set(a[1:])}.get(a[0] if a else "", lambda: print(__doc__))()
