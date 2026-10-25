#!/usr/bin/env python3
"""One hard-cut punch-zoom on the payoff word (add-zooms engine, MIT).
Usage: zooms.py <in.mp4> <out.mp4> [--words words.json] [--payoff SECONDS] [--peak 1.15] [--hold 0.5] [--cy 0.42]
Picks the word nearest the payoff time (the hit / loudest moment; default: the loudest 1.5 s window),
punches in on it, holds, cuts back. Nothing else zooms: rest beats make the punch land. No words -> punch at the payoff time."""
import json, os, subprocess, sys, tempfile
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import now_iso, log

ENGINE = os.path.expanduser("~/autopilot/vendor/add-zooms/scripts/zoom_lib.py")

def opt(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default

def loudest(path):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-vn", "-f", "s16le", "-ac", "1", "-ar", "16000", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    n = 800; k = len(x) // n
    if k < 30:
        return 0.0
    db = 20 * np.log10(np.sqrt((x[: k * n].reshape(k, n) ** 2).mean(axis=1)) + 1e-9)
    w = np.convolve(db, np.ones(30) / 30, mode="valid")
    return float(np.argmax(w)) * 0.05

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "usage"})); return
    src, dst = sys.argv[1], sys.argv[2]
    payoff = float(opt("--payoff", "-1"))
    if payoff < 0:
        payoff = loudest(src)
    words = []
    wj = opt("--words", "")
    if wj and os.path.exists(wj):
        d = json.load(open(wj))
        segs = d.get("segments") if isinstance(d, dict) else None
        words = [w for s in segs for w in s.get("words", [])] if segs else (d.get("words", []) if isinstance(d, dict) else d)
    t = payoff
    label = "payoff time"
    if words:
        w = min(words, key=lambda w: abs(w["start"] - payoff))
        if abs(w["start"] - payoff) <= 2.0:
            t, label = w["start"], "word: " + w.get("word", "").strip()
    ev = [{"type": "punch", "t": round(t, 2), "peak": float(opt("--peak", "1.15")), "hold": float(opt("--hold", "0.5")), "label": label}]
    with tempfile.TemporaryDirectory() as tmp:
        mp = os.path.join(tmp, "map.json")
        json.dump(ev, open(mp, "w"))
        p = subprocess.run([sys.executable, ENGINE, "render", src, dst, mp, "--cy", opt("--cy", "0.42")], capture_output=True, text=True)
        if p.returncode != 0:
            print(json.dumps({"error": (p.stderr or p.stdout)[-300:]})); return
    log("zooms", {"src": os.path.basename(src), "t": ev[0]["t"]})
    print(json.dumps({"at": now_iso(), "out": dst, "events": ev}))

if __name__ == "__main__":
    main()
