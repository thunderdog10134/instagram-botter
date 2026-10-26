#!/usr/bin/env python3
"""Find the strongest reaction moments in a source video (fresh pipeline; replaces ~/camps/bin/moments.py for new campaigns).
Usage: moments.py <source.mp4> <out.json> [--max 5] [--gap 60] [--model tiny.en]
Signals: loudness jump vs the previous 3 s (reactions/shouts), sharp transients (clipify detect_transients),
scene cuts near the peak (PySceneDetect, only in a +-15 s window so long VODs stay fast), and the words said.
Output: {"source", "duration", "moments":[{"key","peak","start","end","sceneCut","transients","score","said","words"}]}

Hype ranking (Josh, Oct 25: "find the most hype pulls, like the reactions are insane"):
  moments.py <source.mp4> <out.json> --rank [--top 8] [--gap 60] [--model tiny.en] [--face W:H:X:Y] [--chat chat.json] [--hype-words file]
  Takes up to 24 loudness-jump peaks (gap rule), scores each hit window (hit-12 s .. hit+12 s) with a `reaction` 0..1:
    audioPeak    0.35  loudest 1 s RMS in the 3 s after the hit vs the replay's median level, dB, 18 dB -> 1.0
    audioSustain 0.25  seconds the 0.5 s-smoothed level stays above median+8 dB after the hit, 8 s -> 1.0
    faceMotion   0.20  mean abs frame difference of the face-cam crop (--face, source pixels) at 6 fps over the 4 s after
                       the hit, divided by the larger of the replay's median (12 sampled 4 s windows) and the median
                       frame difference of the 8 s before the hit (so a layout switch to a big face cam is not a
                       "reaction"); 3x that baseline -> 1.0 (dropped without --face)
    speechHype   0.10  hype words/phrases said from 2 s before to 6 s after the hit (the first shout often precedes the
                       loudness peak; faster-whisper --model) plus a wordless scream (> median+14 dB for >= 0.4 s);
                       3 matches -> 1.0. A bare "what" counts only when exclamatory ("What?!"). --hype-words adds one
                       phrase per line (bin/hype_breaks.txt = card-break hit vocabulary: auto, refractor, one of one ...).
    chatBurst    0.10  --chat json [{t, text}]: messages in the 10 s after vs the 10 s before, ratio 4 -> 1.0 (dropped without --chat)
  Dropped components renormalise the remaining weights to sum to 1. Moments are sorted by reaction (desc), limited to --top,
  and keep the same fields as the plain mode plus "reaction", "components" (null = dropped), "hypeWords", "weights" (as used)
  and "raw" (unscaled values); "allCandidates" lists every scored peak. Keys are slicem0.. in rank order.
  Only the final --top moments get the 27 s transcript and scene-cut lead-in, so FACTORY can cut start..end straight from the output.
  A 20 min 720p60 slice ranks in 2-3 min on 1 CPU. Without --rank the behaviour is exactly the old one."""
import json, os, re, subprocess, sys, tempfile, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import now_iso, log

TRANSIENTS = os.path.expanduser("~/autopilot/vendor/clipify/scripts/detect_transients.py")

HYPE = ["no way", "oh my god", "oh my gosh", "let's go", "lets go", "are you kidding", "what", "holy", "insane", "crazy", "bro",
        "unreal", "stop it", "shut up", "no shot", "wow", "oh my", "yo", "sheesh", "nice", "finally", "we got it", "got him",
        "that's the one", "big", "huge", "bang", "boom"]
WEIGHTS = {"audioPeak": 0.35, "audioSustain": 0.25, "faceMotion": 0.20, "speechHype": 0.10, "chatBurst": 0.10}
PEAK_DB_CAP, SUSTAIN_CAP_S, FACE_CAP_X, HYPE_CAP, CHAT_CAP = 18.0, 8.0, 3.0, 3, 4.0
NCAND = 24

def opt(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default

def duration(path):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(p.stdout.strip() or 0)

def audio(path, wav):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000", wav], check=True)
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", wav, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"], capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

def loudness(x, sr=16000, step=0.05):
    n = int(sr * step)
    k = len(x) // n
    frames = x[: k * n].reshape(k, n)
    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    return 20 * np.log10(rms + 1e-9), step

def scores(db, step):
    k = max(1, int(0.5 / step)); sm = np.convolve(db, np.ones(k) / k, mode="same"); pre = int(3 / step)
    sc = np.full(len(sm), -1e9)
    for i in range(max(int(3.5 / step), pre), len(sm) - int(7 / step)):
        base = np.median(sm[i - pre:i - int(0.4 / step)]); w = sm[i:i + int(1.5 / step)].mean()
        sc[i] = (w - base) + 0.5 * max(-40.0, float(w)) + 10
    return sc

def transients(wav):
    try:
        p = subprocess.run([sys.executable, TRANSIENTS, wav, "--top", "40"], capture_output=True, text=True, timeout=600)
        return [float(t["time"]) for t in json.loads(p.stdout)]
    except Exception:
        return []

def scene_cuts(path, a, b):
    try:
        from scenedetect import open_video, SceneManager, ContentDetector
        v = open_video(path); v.seek(a)
        sm = SceneManager(); sm.add_detector(ContentDetector(threshold=27.0)); sm.auto_downscale = True
        sm.detect_scenes(v, end_time=b)
        return [round(s.seconds if hasattr(s, "seconds") else s.get_seconds(), 2) for s, e in sm.get_scene_list()][1:]
    except Exception:
        return []

def words(path, a, b, model, wm=None):
    from faster_whisper import WhisperModel
    with tempfile.TemporaryDirectory() as tmp:
        w = os.path.join(tmp, "w.wav")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{a}", "-t", f"{b - a}", "-i", path, "-vn", "-ac", "1", "-ar", "16000", w], check=True)
        m = wm or WhisperModel(model, device="cpu", compute_type="int8")
        segs, _ = m.transcribe(w, word_timestamps=True, vad_filter=True)
        return [{"start": round(x.start + a, 2), "end": round(x.end + a, 2), "word": x.word.strip()} for s in segs for x in (s.words or []) if x.probability > 0.35]

# ---------- hype ranking (--rank) ----------

def pick_peaks(sc, step, gap, n):
    peaks = []
    for i in np.argsort(-sc):
        if sc[i] < -1e8:
            break
        t = i * step
        if all(abs(t - p) >= gap for p in peaks):
            peaks.append(t)
        if len(peaks) >= n:
            break
    return peaks

def norm_text(s):
    s = s.lower().replace("'", "").replace("’", "")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()

def hype_matches(text, phrases):
    text = re.sub(r"(?i)\bwhat\b(?![?!])", "whatx", text)   # a bare "what" is not hype; "What?!" is
    t = " " + norm_text(text) + " "
    found = []
    for p in sorted({norm_text(x) for x in phrases if norm_text(x)}, key=len, reverse=True):
        pat = r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])"
        n = len(re.findall(pat, t))
        if n:
            found += [p] * n
            t = re.sub(pat, " # ", t)
    return found

def median_level(db):
    live = db[db > -55.0]
    return float(np.median(live)) if len(live) else float(np.median(db))

def audio_peak_db(db, step, P, med):
    """Loudest 1 s mean power starting in [P, P+3] vs the replay median, in dB."""
    f = int(round(1 / step)); p = 10 ** (db / 10)
    cs = np.concatenate([[0.0], np.cumsum(p)])
    win = (cs[f:] - cs[:-f]) / f
    i0, i1 = int(P / step), min(len(win), int((P + 3) / step) + 1)
    if i1 <= i0:
        return 0.0
    return float(10 * np.log10(win[i0:i1].max() + 1e-12) - med)

def sustain_s(db, step, P, med):
    k = max(1, int(0.5 / step)); sm = np.convolve(db, np.ones(k) / k, mode="same"); thr = med + 8
    j0, j1 = int(max(0.0, P - 0.5) / step), min(len(sm), int((P + 3) / step))
    idx = next((j for j in range(j0, j1) if sm[j] > thr), None)
    if idx is None:
        return 0.0
    j = last = idx; tol = int(0.3 / step); jmax = min(len(sm), idx + int(SUSTAIN_CAP_S / step))
    while j < jmax and j - last <= tol:
        if sm[j] > thr:
            last = j
        j += 1
    return (last - idx + 1) * step

def scream(db, step, P, med, wlist, span=6.0):
    thr = med + 14; i0, i1 = int(P / step), min(len(db), int((P + span) / step)); need = int(0.4 / step)
    i = i0
    while i < i1:
        if db[i] > thr:
            j = i
            while j < i1 and db[j] > thr:
                j += 1
            if j - i >= need and not any(w["start"] < j * step and w["end"] > i * step for w in wlist):
                return True
            i = j
        else:
            i += 1
    return False

def parse_face(s):
    try:
        w, h, x, y = [int(float(v)) for v in s.split(":")]
        return (w, h, x, y) if w > 0 and h > 0 and x >= 0 and y >= 0 else None
    except Exception:
        return None

def face_diffs(path, a, crop, n=4.0, fps=6):
    """Per-frame mean absolute grayscale difference of the face crop at ~fps over [a, a+n] (None on failure)."""
    W, H, X, Y = crop
    w2 = 128; h2 = max(2, int(round(H * w2 / W / 2)) * 2)
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{max(0.0, a):.2f}", "-t", f"{n}", "-i", path, "-an",
           "-vf", f"crop={W}:{H}:{X}:{Y},fps={fps},scale={w2}:{h2},format=gray", "-f", "rawvideo", "-"]
    try:
        raw = subprocess.run(cmd, capture_output=True, timeout=180).stdout
    except Exception:
        return None
    k = len(raw) // (w2 * h2)
    if k < 2:
        return None
    f = np.frombuffer(raw[: k * w2 * h2], dtype=np.uint8).reshape(k, h2, w2).astype(np.float32)
    return np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))

def face_motion(path, a, crop, n=4.0):
    d = face_diffs(path, a, crop, n)
    return None if d is None else float(d.mean())

def face_hit(path, P, crop, base, fps=6):
    """(motion over [P, P+4], local baseline = median frame diff over [P-10, P-2]) in one decode."""
    a0 = max(0.0, P - 10)
    d = face_diffs(path, a0, crop, P + 4 - a0, fps)
    if d is None:
        return None, None
    post = d[int((P - a0) * fps):]; pre = d[: max(0, int((P - 2 - a0) * fps))]
    if len(post) < 2:
        return None, None
    local = float(np.median(pre)) if len(pre) >= fps else base
    return float(post.mean()), local

def chat_burst(ts, P):
    before = sum(1 for t in ts if P - 10 <= t < P); after = sum(1 for t in ts if P <= t < P + 10)
    if not before and not after:
        return 0.0, (before, after)
    return min(1.0, (after / max(1, before)) / CHAT_CAP), (before, after)

def rank(src, outp):
    K, gap, model = int(opt("--top", "8")), float(opt("--gap", "60")), opt("--model", "tiny.en")
    face = parse_face(opt("--face", "")); chatp, hwp = opt("--chat", ""), opt("--hype-words", "")
    phrases = list(HYPE)
    if hwp:
        try:
            phrases += [l.strip() for l in open(hwp) if l.strip() and not l.startswith("#")]
        except Exception:
            pass
    chat = None
    if chatp:
        try:
            chat = sorted(float(m["t"]) for m in json.load(open(chatp)) if isinstance(m, dict) and "t" in m)
        except Exception:
            chat = None
    t0 = time.time(); dur = duration(src); timing = {}
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "a.wav")
        x = audio(src, wav)
        db, step = loudness(x)
        sc = scores(db, step)
        tr = transients(wav)
    med = median_level(db); timing["audio"] = round(time.time() - t0, 1)
    peaks = pick_peaks(sc, step, gap, NCAND)
    base = None
    if face:
        t1 = time.time()
        vals = [v for v in (face_motion(src, a, face) for a in np.linspace(0, max(0.0, dur - 4), 12)) if v is not None]
        base = float(np.median(vals)) if vals else None
        if not base or base <= 0:
            base = None
        timing["faceBase"] = round(time.time() - t1, 1)
    from faster_whisper import WhisperModel
    wm = WhisperModel(model, device="cpu", compute_type="int8")
    sid = os.path.splitext(os.path.basename(src))[0]
    cands = []; t1 = time.time()
    for P in sorted(peaks):
        pk = audio_peak_db(db, step, P, med); sus = sustain_s(db, step, P, med)
        h0 = max(0.0, P - 2)
        wh = words(src, h0, min(dur, P + 6), model, wm); said = " ".join(w["word"] for w in wh)
        hw = hype_matches(said, phrases); scr = scream(db, step, h0, med, wh, span=P + 6 - h0)
        if scr:
            hw.append("<scream>")
        comps = {"audioPeak": round(min(1.0, max(0.0, pk / PEAK_DB_CAP)), 3),
                 "audioSustain": round(min(1.0, sus / SUSTAIN_CAP_S), 3),
                 "faceMotion": None, "speechHype": round(min(1.0, len(hw) / HYPE_CAP), 3), "chatBurst": None}
        raw = {"peakDb": round(pk, 1), "sustainS": round(sus, 2), "faceDiff": None, "faceLocal": None,
               "faceBase": None if base is None else round(base, 2), "saidHit": said[:200], "chat": None}
        if base is not None:
            fd, loc = face_hit(src, P, face, base)
            if fd is not None:
                comps["faceMotion"] = round(min(1.0, fd / (FACE_CAP_X * max(base, loc))), 3)
                raw["faceDiff"], raw["faceLocal"] = round(fd, 2), round(loc, 2)
        if chat is not None:
            comps["chatBurst"], raw["chat"] = chat_burst(chat, P)
            comps["chatBurst"] = round(comps["chatBurst"], 3)
        ws = {k: WEIGHTS[k] for k, v in comps.items() if v is not None}; tot = sum(ws.values()) or 1.0
        reaction = sum(comps[k] * ws[k] / tot for k in ws)
        cands.append({"peak": float(P), "reaction": round(reaction, 3), "components": comps, "hypeWords": hw, "raw": raw,
                      "weights": {k: round(v / tot, 3) for k, v in ws.items()}})
    timing["candidates"] = round(time.time() - t1, 1)
    cands.sort(key=lambda c: (-c["reaction"], c["peak"]))
    top = cands[:K]; moments = []; t1 = time.time()
    for j, c in enumerate(top):
        P = c["peak"]; a0, a1 = max(0.0, P - 15), min(dur, P + 12)
        cuts = [q for q in scene_cuts(src, a0, a1) if a0 <= q <= a1]
        near = [q for q in cuts if abs(q - P) <= 1.0]
        lead = [q for q in cuts if P - 8 <= q <= P - 4]
        start = lead[-1] if lead else max(0.0, P - 6.5)
        end = min(dur, P + 6.0)
        wl = words(src, a0, a1, model, wm)
        moments.append({"key": f"{sid}m{j}", "peak": round(P, 2), "start": round(start, 2), "end": round(end, 2),
                        "sceneCut": near[0] if near else None, "sceneCuts": cuts, "startOnCut": bool(lead),
                        "transients": [round(t, 2) for t in tr if a0 <= t <= a1], "score": round(float(sc[int(P / step)]), 2),
                        "words": wl, "said": " ".join(w["word"] for w in wl)[:800], "reaction": c["reaction"], "components": c["components"],
                        "hypeWords": c["hypeWords"], "raw": c["raw"], "weights": c["weights"]})
    timing["top"] = round(time.time() - t1, 1)
    res = {"at": now_iso(), "source": src, "duration": round(dur, 1), "rank": True, "top": K, "candidates": len(cands), "medianDb": round(med, 1),
           "face": list(face) if face else None, "faceBase": None if base is None else round(base, 2), "chat": chat is not None,
           "moments": moments, "allCandidates": [{k: c[k] for k in ("peak", "reaction", "components", "hypeWords", "raw")} for c in cands],
           "timing": timing, "seconds": round(time.time() - t0, 1)}
    json.dump(res, open(outp, "w"), indent=1)
    log("moments", {"src": sid, "n": len(moments), "rank": True, "candidates": len(cands), "seconds": res["seconds"]})
    print(json.dumps({k: res[k] for k in ("source", "duration", "seconds", "candidates")} |
                     {"moments": [{k: m[k] for k in ("key", "peak", "start", "end", "reaction", "components")} for m in moments]}, separators=(",", ":")))

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "usage"})); return
    src, outp = sys.argv[1], sys.argv[2]
    if "--rank" in sys.argv:
        return rank(src, outp)
    N, gap, model = int(opt("--max", "5")), float(opt("--gap", "60")), opt("--model", "tiny.en")
    t0 = time.time()
    dur = duration(src)
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "a.wav")
        x = audio(src, wav)
        db, step = loudness(x)
        sc = scores(db, step)
        tr = transients(wav)
    n = 1 if dur < 100 else min(N, max(1, int(dur // 240)))
    peaks = []
    for i in np.argsort(-sc):
        if sc[i] < -1e8:
            break
        t = i * step
        if all(abs(t - p) >= gap for p in peaks):
            peaks.append(t)
        if len(peaks) >= n:
            break
    sid = os.path.splitext(os.path.basename(src))[0]
    moments = []
    for j, P in enumerate(sorted(peaks)):
        a0, a1 = max(0.0, P - 15), min(dur, P + 12)
        cuts = [c for c in scene_cuts(src, a0, a1) if a0 <= c <= a1]
        near = [c for c in cuts if abs(c - P) <= 1.0]
        lead = [c for c in cuts if P - 8 <= c <= P - 4]
        start = lead[-1] if lead else max(0.0, P - 6.5)
        end = min(dur, P + 6.0)
        moments.append({"key": sid if n == 1 else f"{sid}m{j}", "peak": round(float(P), 2), "start": round(start, 2), "end": round(end, 2),
                        "sceneCut": near[0] if near else None, "sceneCuts": cuts, "startOnCut": bool(lead),
                        "transients": [round(t, 2) for t in tr if a0 <= t <= a1], "score": round(float(sc[int(P / step)]), 2),
                        "words": words(src, a0, a1, model)})
        moments[-1]["said"] = " ".join(w["word"] for w in moments[-1]["words"])[:800]
    res = {"at": now_iso(), "source": src, "duration": round(dur, 1), "moments": moments, "seconds": round(time.time() - t0, 1)}
    json.dump(res, open(outp, "w"), indent=1)
    log("moments", {"src": sid, "n": len(moments)})
    print(json.dumps({k: res[k] for k in ("source", "duration", "seconds")} | {"moments": [{k: m[k] for k in ("key", "peak", "start", "end", "sceneCut", "startOnCut", "score")} | {"said": m["said"][:80]} for m in moments]}))

if __name__ == "__main__":
    main()
