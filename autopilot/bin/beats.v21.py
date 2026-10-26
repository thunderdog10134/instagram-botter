#!/usr/bin/env python3
"""beats.py <clip.mp4> <words.json> <out beats.json> [--claim "/43"] [--badge "NUMBERED TO 43"] [--chip "LIVE ON KICK · @handle"] [--keyword face] [--cta PULL]
Plans the v2 shot list for a framed clip (card cam + face PiP already composited):
- caption groups of 1-4 words from the whisper words (a new box on every group; keyword highlighted)
- punch-ins (x1.24, 180 ms in / 400 ms hold / 250 ms out) on the loudest 20% of words (the shout), min 1.2 s apart
- a visual event at least every 2.0 s: if no caption/punch lands in a 2 s window, a 'push' (slow 1.0->1.06 zoom) fills it
- badge at the first keyword/loudest word, chip at 1.0 s, claim number from 0.3 s for 1.6 s, CTA for the last 2.5 s
Prints the shot list; nothing still > 2 s is the check."""
import sys, json, subprocess, re, numpy as np
def opt(n, d):
    return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d
clip, wj, out = sys.argv[1:4]
dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", clip]).decode())
W = json.load(open(wj)); words = [w for s in W["segments"] for w in s["words"] if w["word"].strip()]
# loudness per 50 ms
r = subprocess.run(["ffmpeg", "-v", "error", "-i", clip, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True)
a = np.frombuffer(r.stdout, dtype=np.int16).astype(float); hop = 800
rms = np.array([np.sqrt((a[i:i + hop] ** 2).mean() + 1e-9) for i in range(0, len(a) - hop, hop)])
def loud(t):
    i = int(t / 0.05); return float(rms[max(0, i - 2):i + 3].mean()) if len(rms) else 0.0
for w in words: w["loud"] = loud(w["start"])
thr = np.percentile([w["loud"] for w in words], 80) if words else 0
# caption groups: break on gaps > 0.45 s or 4 words
groups, cur = [], []
for w in words:
    if cur and (w["start"] - cur[-1]["end"] > 0.45 or len(cur) >= 4 or re.search(r"[.!?]$", cur[-1]["word"].strip())):
        groups.append(cur); cur = []
    cur.append(w)
if cur: groups.append(cur)
kw = opt("--keyword", "").strip()
caps = [{"t0": max(0, g[0]["start"] - 0.1), "t1": g[-1]["end"] + 0.25, "words": [x["word"].strip() for x in g],
         "keyword": kw if any(x["word"].strip().strip(".,!?").lower() == kw.lower() for x in g) else None} for g in groups]
# punches on loud words
punches, last = [], -9
for w in words:
    if w["loud"] >= thr and w["start"] - last >= 1.2:
        punches.append({"t": round(w["start"], 2), "word": w["word"].strip()}); last = w["start"]
events = sorted([c["t0"] for c in caps] + [p["t"] for p in punches] + [0.3, 1.0, dur - 2.5])
pushes, t = [], 0.0
while t < dur - 0.3:
    nxt = [e for e in events if t < e <= t + 2.0]
    if nxt:
        t = max(nxt)                                   # the latest event inside the window; keep walking from there
    else:
        p = {"t0": round(t + 0.1, 2), "t1": round(min(t + 2.0, dur), 2)}; pushes.append(p); events += [p["t0"], p["t1"]]; events.sort(); t = p["t1"]
first_kw = next((w for w in words if kw and w["word"].strip(".,!?").lower() == kw.lower()), None)
badge_t = first_kw["start"] if first_kw else (punches[0]["t"] if punches else 2.0)
plan = {"clip": clip, "dur": round(dur, 2), "blurtop": int(opt("--blurtop", "0")), "claim": {"text": opt("--claim", ""), "t0": 0.3, "t1": 1.9},
        "chip": {"text": opt("--chip", ""), "t0": 1.0, "t1": round(dur - 0.1, 2)},
        "badge": {"text": opt("--badge", ""), "t0": round(badge_t, 2), "t1": round(min(badge_t + 2.4, dur - 0.1), 2)},
        "captions": caps, "punches": punches, "pushes": pushes, "cta": {"keyword": opt("--cta", "PULL"), "t0": round(dur, 2), "t1": round(dur + 2.5, 2)}}
ev = sorted(set([0.3, 1.0] + [c["t0"] for c in caps] + [p["t"] for p in punches] + [x for p in pushes for x in (p["t0"], p["t1"])] + [plan["cta"]["t0"]]))
gaps = [b - a for a, b in zip(ev, ev[1:] + [dur])]
plan["check"] = {"events": len(ev), "longest_gap": round(max(gaps), 2), "ok": max(gaps) <= 2.05}
json.dump(plan, open(out, "w"), indent=1); print(json.dumps(plan["check"]), len(caps), "caption groups,", len(punches), "punches,", len(pushes), "pushes")
