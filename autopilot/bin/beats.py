#!/usr/bin/env python3
"""beats.py <clip.mp4> <words.json> <out beats.json> [--claim "/43"] [--badge "NUMBERED TO 43"] [--chip "LIVE ON KICK · @handle"] [--keyword face] [--cta PULL]
         [--claim2 "2ND NUMBER"] [--before "ONE PACK" --after "1/1 AUTO"] [--price "$1,250" [--price-at S]] [--check]
         [--cta-style pill|type] [--cta-text "COMMENT ANYTHING ✅\nFULL REPLAY IN YOUR DMS"] [--pill "COMMENT ANYTHING · REPLAY IN DMS"]
         --cta-style pill (v2.3, skand.ai "comment anything, link in DMs" reference): the end card is a white pill with a green check
         (--cta-text, two lines on \n) instead of the COMMENT/PULL type, same timing (last 2.5 s), and a small one-line pill
         (--pill) sits under the title plate from 1.0 s to the end as plan["pillTop"]; the default "type" is today's output, byte for byte
         --price: the sold-comp price (ONLY when the item has compUrl); shows for 2.4 s with a cha-ching, at --price-at or 1.0 s after the badge
v2.2 (Paper Crab additions, Oct 25): a title plate per spoken sentence (kit.title, y~220), an optional second number
beat at 2/3 of the clip (--claim2: only a real number the stream gave), a before/after chip above the CTA, and --check:
four persona checks (sound-off, caption-only, stranger, rival) printed as pass/fail; "hold": true when two or more fail
(FACTORY holds such a clip instead of queueing it).
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
# sentences -> title plates (v2.2): a sentence ends on . ! ? ; the plate shows the sentence in at most 7 words
sentences, cur_s = [], []
for g in groups:
    cur_s.append(g)
    if re.search(r"[.!?]$", g[-1]["word"].strip()):
        sentences.append(cur_s); cur_s = []
if cur_s: sentences.append(cur_s)
titles = []
for sgs in sentences:
    ws = [x["word"].strip() for g in sgs for x in g]
    text = " ".join(ws if len(ws) <= 7 else ws[:6] + ["\u2026"])
    titles.append({"t0": max(0, sgs[0][0]["start"] - 0.1), "t1": round(sgs[-1][-1]["end"] + 0.35, 2), "text": text})
claim2_text = opt("--claim2", "").strip()
claim2 = {"text": claim2_text, "t0": round(dur * 2 / 3, 2), "t1": round(min(dur * 2 / 3 + 1.6, dur - 0.2), 2)} if claim2_text else None
price_text = opt("--price", "").strip()
before, after = opt("--before", "").strip(), opt("--after", "").strip()
beforeafter = {"before": before, "after": after} if before and after else None
# punches on loud words
punches, last = [], -9
for w in words:
    if w["loud"] >= thr and w["start"] - last >= 1.2:
        punches.append({"t": round(w["start"], 2), "word": w["word"].strip()}); last = w["start"]
events = sorted([c["t0"] for c in caps] + [p["t"] for p in punches] + [t["t0"] for t in titles] + ([claim2["t0"]] if claim2 else []) + [0.3, 1.0, dur - 2.5])
pushes, t = [], 0.0
while t < dur - 0.3:
    nxt = [e for e in events if t < e <= t + 2.0]
    if nxt:
        t = max(nxt)                                   # the latest event inside the window; keep walking from there
    else:
        p = {"t0": round(t + 0.1, 2), "t1": round(min(t + 2.0, dur), 2)}; pushes.append(p); events += [p["t0"], p["t1"]]; events.sort(); t = p["t1"]
first_kw = next((w for w in words if kw and w["word"].strip(".,!?").lower() == kw.lower()), None)
badge_t = first_kw["start"] if first_kw else (punches[0]["t"] if punches else 2.0)
price = None
if price_text:
    pt0 = float(opt("--price-at", str(min(badge_t + 1.0, dur - 2.8))))
    price = {"text": price_text, "t0": round(pt0, 2), "t1": round(min(pt0 + 2.4, dur - 0.1), 2)}
plan = {"clip": clip, "dur": round(dur, 2), "blurtop": int(opt("--blurtop", "0")), "claim": {"text": opt("--claim", ""), "t0": 0.3, "t1": 1.9}, "price": price,
        "chip": {"text": opt("--chip", ""), "t0": 1.0, "t1": round(dur - 0.1, 2)},
        "badge": {"text": opt("--badge", ""), "t0": round(badge_t, 2), "t1": round(min(badge_t + 2.4, dur - 0.1), 2)},
        "captions": caps, "punches": punches, "pushes": pushes, "titles": titles, "claim2": claim2, "beforeafter": beforeafter,
        "cta": {"keyword": opt("--cta", "PULL"), "t0": round(dur, 2), "t1": round(dur + 2.5, 2)}}
if beforeafter: beforeafter.update(t0=plan["cta"]["t0"], t1=plan["cta"]["t1"])
if opt("--cta-style", "type") == "pill":                                                   # v2.3 pill end card + top pill
    plan["cta"].update(style="pill", text=opt("--cta-text", "COMMENT ANYTHING \u2705\nFULL REPLAY IN YOUR DMS").replace("\\n", "\n"))
    plan["pillTop"] = {"text": opt("--pill", "COMMENT ANYTHING \u00b7 REPLAY IN DMS"), "t0": 1.0, "t1": round(dur, 2)}
ev = sorted(set([0.3, 1.0] + [c["t0"] for c in caps] + [p["t"] for p in punches] + [t["t0"] for t in titles] + ([claim2["t0"]] if claim2 else []) + ([price["t0"]] if price else [])
                + [x for p in pushes for x in (p["t0"], p["t1"])] + [plan["cta"]["t0"]]))
gaps = [b - a for a, b in zip(ev, ev[1:] + [dur])]
plan["check"] = {"events": len(ev), "longest_gap": round(max(gaps), 2), "ok": max(gaps) <= 2.05}
# v2.2 persona checks (Paper Crab: "ten viewers try to scroll past"). Deterministic rules, no model:
spoken = (words[-1]["end"] - words[0]["start"]) if words else 0.0
covered = sum(min(c["t1"], dur) - c["t0"] for c in caps)
personas = {
    # watches with the sound off: the claim and the card fact are on screen and the captions cover the speech
    "soundOff": bool(plan["claim"]["text"]) and bool(plan["badge"]["text"]) and (spoken == 0 or covered / spoken >= 0.7),
    # only reads the captions: short groups that stay long enough to read, and a title plate per sentence
    "captionOnly": all(len(c["words"]) <= 4 and (c["t1"] - c["t0"]) >= 0.3 for c in caps) and len(titles) >= 1 and bool(plan["chip"]["text"]),
    # a stranger: who, what and the number inside 1.5 s; the breaker credited on screen
    "stranger": bool(plan["chip"]["text"]) and plan["claim"]["t0"] <= 1.5 and bool(plan["claim"]["text"]) and bool(plan["badge"]["text"]),
    # a rival who has seen it before: a beat every <= 2 s, at least one punch, a second number or a before/after, a CTA
    "rival": plan["check"]["ok"] and len(punches) >= 1 and (bool(plan["cta"]["keyword"]) or bool(plan["cta"].get("text")) or bool((plan.get("pillTop") or {}).get("text"))) and 10 <= dur <= 40 and (claim2 is not None or beforeafter is not None or price is not None),
}
failed = [k for k, v in personas.items() if not v]
plan["personas"] = {"result": {k: ("pass" if v else "fail") for k, v in personas.items()}, "failed": failed, "hold": len(failed) >= 2}
json.dump(plan, open(out, "w"), indent=1)
if "--check" in sys.argv:
    print(json.dumps({"check": plan["check"], "personas": plan["personas"]["result"], "failed": failed, "hold": plan["personas"]["hold"]}))
else:
    print(json.dumps(plan["check"]), len(caps), "caption groups,", len(punches), "punches,", len(pushes), "pushes,", len(titles), "titles;",
          "personas:", json.dumps(plan["personas"]["result"]), "hold" if plan["personas"]["hold"] else "")
