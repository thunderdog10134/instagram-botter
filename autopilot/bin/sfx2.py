#!/usr/bin/env python3
"""Sound design for format v2.1 — every sound is synthesized here with numpy (ours, royalty-free). Writes 48 kHz stereo WAVs.
bed(sec)     : low pulsing synth bed, ~88 BPM, sub + filtered saw, -22 LUFS-ish before mix
riser(1.6s)  : noise + sine sweep rising into the hit
impact       : 45 Hz sub thump + click, 0.9 s decay (the payoff)
whoosh       : band-passed noise swell, 0.35 s (each overlay / punch)
tick         : soft 2 kHz click, 60 ms (each caption)
pop          : 120 ms filtered chirp (each title plate / before-after chip; v2.2)
chaching     : 1.1 s cash-register click + bell + coin ticks (the price plate; v2.2)
"""
import sys, os, numpy as np, wave
SR = 48000
def save(path, x):
    x = np.clip(x, -1, 1); st = np.stack([x, x], 1) if x.ndim == 1 else x
    with wave.open(path, "wb") as w: w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((st * 32767).astype(np.int16).tobytes())
def env(n, a, d, s=0.0, r=0.0):
    e = np.ones(n); A = int(a * SR); D = int(d * SR); R = int(r * SR)
    e[:A] = np.linspace(0, 1, A); e[A:A + D] = np.linspace(1, s, D); 
    if R: e[-R:] = np.linspace(e[-R], 0, R)
    return e
def lowpass(x, fc):
    a = np.exp(-2 * np.pi * fc / SR); y = np.zeros_like(x); 
    for i in range(1, len(x)): y[i] = a * y[i - 1] + (1 - a) * x[i]
    return y
def bed(sec, bpm=88, root=55.0):
    n = int(sec * SR); t = np.arange(n) / SR; beat = 60 / bpm
    sub = 0.5 * np.sin(2 * np.pi * root * t) * (0.6 + 0.4 * np.clip(np.sin(2 * np.pi * t / (beat * 2)), 0, 1))
    saw = ((t * root * 2) % 1.0 - 0.5); saw = lowpass(saw, 420) * 0.35
    pulse = np.zeros(n)
    for k in range(int(sec / beat) + 1):
        i = int(k * beat * SR); L = int(0.18 * SR)
        if i + L < n: pulse[i:i + L] += np.sin(2 * np.pi * root * 2 * np.arange(L) / SR) * np.exp(-np.arange(L) / (0.05 * SR)) * 0.25
    x = (sub + saw + pulse) * 0.5
    x[:int(0.4 * SR)] *= np.linspace(0, 1, int(0.4 * SR)); return x
def riser(sec=1.6):
    n = int(sec * SR); t = np.arange(n) / SR
    f = 120 * (2 ** (t / sec * 3)); sine = np.sin(2 * np.pi * np.cumsum(f) / SR)
    noise = np.random.default_rng(1).normal(0, 1, n); noise = noise - lowpass(noise, 900)
    e = (t / sec) ** 2.2
    return (0.35 * sine + 0.5 * noise * 0.3) * e * 0.9
def impact():
    n = int(0.9 * SR); t = np.arange(n) / SR
    f = 45 * np.exp(-t * 4) + 38; sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.2)
    click = np.random.default_rng(2).normal(0, 1, n) * np.exp(-t * 60) * 0.5
    return np.tanh(1.8 * (sub + click)) * 0.95
def whoosh(sec=0.35):
    n = int(sec * SR); t = np.arange(n) / SR
    noise = np.random.default_rng(3).normal(0, 1, n); noise = lowpass(noise, 3500) - lowpass(noise, 500)
    e = np.sin(np.pi * t / sec) ** 2
    return noise * e * 0.6
def tick():
    n = int(0.06 * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * 2100 * t) * np.exp(-t * 90) * 0.35
def pop(sec=0.12):
    """Short filtered pop for a plate landing (v2.2): sine chirp 600->180 Hz with a fast decay."""
    n = int(sec * SR); t = np.arange(n) / SR
    f = 600 * np.exp(-t * 18) + 180; x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 28)
    return x * 0.45
def chaching(sec=1.1):
    """Cash-register 'cha-ching' (v2.2 price beat, Josh Oct 25): a short mechanical click + drawer thud, then a bright bell
    (two partials, 2.6 and 3.9 kHz) with a sparkle of coin-like noise ticks. All synthesized here, royalty-free."""
    n = int(sec * SR); t = np.arange(n) / SR; rng = np.random.default_rng(7)
    click = rng.normal(0, 1, n) * np.exp(-t * 120) * 0.5                         # 'cha'
    thud = np.sin(2 * np.pi * 110 * t) * np.exp(-t * 30) * 0.5
    tb = np.clip(t - 0.11, 0, None)                                             # bell starts 110 ms in: 'ching'
    bell = (np.sin(2 * np.pi * 2600 * tb) * 0.55 + np.sin(2 * np.pi * 3900 * tb) * 0.35 + np.sin(2 * np.pi * 5200 * tb) * 0.15)
    bell = bell * np.exp(-tb * 5.5) * (t >= 0.11)
    coins = np.zeros(n)
    for k in range(6):
        i = int((0.16 + k * 0.045) * SR); L = int(0.03 * SR)
        if i + L < n: coins[i:i + L] += np.sin(2 * np.pi * (4200 + 300 * k) * np.arange(L) / SR) * np.exp(-np.arange(L) / (0.006 * SR)) * 0.25
    x = click + thud + bell + coins
    return np.tanh(1.4 * x) * 0.9
if __name__ == "__main__":
    out = sys.argv[1]; os.makedirs(out, exist_ok=True); sec = float(sys.argv[2]) if len(sys.argv) > 2 else 30
    save(f"{out}/bed.wav", bed(sec)); save(f"{out}/riser.wav", riser()); save(f"{out}/impact.wav", impact()); save(f"{out}/whoosh.wav", whoosh()); save(f"{out}/tick.wav", tick()); save(f"{out}/pop.wav", pop()); save(f"{out}/chaching.wav", chaching())
    print("ok", out)
