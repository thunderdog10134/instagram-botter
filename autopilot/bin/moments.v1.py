#!/usr/bin/env python3
"""Find the strongest reaction moments in a source video (fresh pipeline; replaces ~/camps/bin/moments.py for new campaigns).
Usage: moments.py <source.mp4> <out.json> [--max 5] [--gap 60] [--model tiny.en]
Signals: loudness jump vs the previous 3 s (reactions/shouts), sharp transients (clipify detect_transients),
scene cuts near the peak (PySceneDetect, only in a +-15 s window so long VODs stay fast), and the words said.
Output: {"source", "duration", "moments":[{"key","peak","start","end","sceneCut","transients","score","said","words"}]}"""
import json, os, subprocess, sys, tempfile, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import now_iso, log

TRANSIENTS = os.path.expanduser("~/autopilot/vendor/clipify/scripts/detect_transients.py")

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

def words(path, a, b, model):
    from faster_whisper import WhisperModel
    with tempfile.TemporaryDirectory() as tmp:
        w = os.path.join(tmp, "w.wav")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{a}", "-t", f"{b - a}", "-i", path, "-vn", "-ac", "1", "-ar", "16000", w], check=True)
        m = WhisperModel(model, device="cpu", compute_type="int8")
        segs, _ = m.transcribe(w, word_timestamps=True, vad_filter=True)
        return [{"start": round(x.start + a, 2), "end": round(x.end + a, 2), "word": x.word.strip()} for s in segs for x in (s.words or []) if x.probability > 0.35]

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "usage"})); return
    src, outp = sys.argv[1], sys.argv[2]
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
