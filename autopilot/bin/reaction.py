#!/usr/bin/env python3
"""reaction.py <video> [--top 5] [--gap 40]  -> the most insane reactions in a source, scored, JSON lines.
Score = loudness jump (dB over the previous 4 s) + sustain (seconds the level stays within 6 dB of the peak, capped 3 s) * 4
      + high-band share (screams have energy > 2 kHz) * 20.  A 'wow' with no jump scores ~8; a real scream scores 25+."""
import sys, subprocess, json, numpy as np
f = sys.argv[1]; top = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 5
gap = float(sys.argv[sys.argv.index("--gap") + 1]) if "--gap" in sys.argv else 40
r = subprocess.run(["ffmpeg", "-v", "error", "-i", f, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True)
a = np.frombuffer(r.stdout, dtype=np.int16).astype(float) / 32768; hop = 1600  # 100 ms
n = len(a) // hop; rms = np.array([np.sqrt((a[i*hop:(i+1)*hop] ** 2).mean() + 1e-9) for i in range(n)]); db = 20 * np.log10(rms)
# high-band share per 100 ms
hb = np.array([(lambda w: (np.abs(np.fft.rfft(w))[int(2000/16000*len(w)):].sum() / (np.abs(np.fft.rfft(w)).sum() + 1e-9)))(a[i*hop:(i+1)*hop]) for i in range(n)])
sm = np.convolve(db, np.ones(5) / 5, mode="same")
cands = []
for i in range(40, n - 30):
    base = np.median(sm[i - 40:i - 5]); jump = sm[i] - base
    if jump < 6 or base < -45: continue   # base < -45 dB = a muted stretch, not a room
    peak = sm[i:i + 30].max(); sus = sum(1 for x in sm[i:i + 30] if x > peak - 6) / 10.0
    score = jump + min(sus, 3) * 4 + hb[i:i + 15].mean() * 20
    cands.append((score, i / 10.0, round(jump, 1), round(sus, 1), round(float(hb[i:i+15].mean()), 2)))
cands.sort(reverse=True); picked = []
for s, t, j, su, h in cands:
    if all(abs(t - p[1]) >= gap for p in picked): picked.append((s, t, j, su, h))
    if len(picked) >= top: break
for s, t, j, su, h in picked: print(json.dumps({"t": t, "score": round(s, 1), "jumpDb": j, "sustainS": su, "highShare": h}))
