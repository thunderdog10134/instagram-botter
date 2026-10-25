#!/usr/bin/env python3
"""Self-cleaning for the sandbox. Deletes work files nothing needs any more.
Usage: janitor.py [--keep keep.txt] [--days 3] [--dry-run]
  keep.txt: one path per line (the agent writes the localPath of every ready/hold story and the work dir of every ready/hold reel).
Rules:
  - ~/autopilot/work: stream slices / audio (slice*.mp4, s1.mp4, *.wav, raw*.mp4) older than 1 day; every other media file
    (.mp4 .wav .png .jpg .json.tmp) older than --days; never a path in keep.txt or under a kept directory. Empty dirs removed.
  - ~/autopilot/out/*.json older than 14 days, ~/autopilot/queue/* older than 7 days, ~/autopilot/logs/* older than 14 days.
  - never touches ~/autopilot/bin, host, state, ~/secrets, ~/ref, ~/pylib.
Prints JSON {freedMB, files, kept, diskFreeGB, dryRun}."""
import json, os, sys, time, shutil
H = os.path.expanduser("~")
AP = os.path.join(H, "autopilot")
def opt(n, d=None):
    return sys.argv[sys.argv.index(n)+1] if n in sys.argv else d
days = float(opt("--days", "3")); dry = "--dry-run" in sys.argv
keep = set()
if opt("--keep") and os.path.exists(opt("--keep")):
    for l in open(opt("--keep")):
        l = l.strip()
        if l: keep.add(os.path.realpath(os.path.expanduser(l)))
def kept(p):
    rp = os.path.realpath(p)
    return any(rp == k or rp.startswith(k.rstrip("/") + "/") for k in keep)
now = time.time(); freed = 0; n = 0; nkept = 0
def rm(p):
    global freed, n
    try:
        s = os.path.getsize(p)
        if not dry: os.remove(p)
        freed += s; n += 1
    except OSError:
        pass
MEDIA = (".mp4", ".wav", ".png", ".jpg", ".jpeg", ".m4a", ".ts", ".tmp")
SLICE = lambda f: f.startswith("slice") or f in ("s1.mp4", "a.wav") or f.startswith("raw") or f.endswith(".wav")
for root, dirs, files in os.walk(os.path.join(AP, "work")):
    for f in files:
        p = os.path.join(root, f)
        age = (now - os.path.getmtime(p)) / 86400
        if kept(p):
            nkept += 1; continue
        if SLICE(f) and age > 1: rm(p)
        elif f.lower().endswith(MEDIA) and age > days: rm(p)
for sub, d in (("out", 14), ("queue", 7), ("logs", 14)):
    base = os.path.join(AP, sub)
    if not os.path.isdir(base): continue
    for f in os.listdir(base):
        p = os.path.join(base, f)
        if os.path.isfile(p) and (now - os.path.getmtime(p)) / 86400 > d and not f.startswith("posted-"):
            rm(p)
if not dry:
    for root, dirs, files in os.walk(os.path.join(AP, "work"), topdown=False):
        if root != os.path.join(AP, "work") and not os.listdir(root) and not kept(root):
            try: os.rmdir(root)
            except OSError: pass
du = shutil.disk_usage(H)
print(json.dumps({"freedMB": round(freed / 1e6, 1), "files": n, "kept": nkept, "diskFreeGB": round(du.free / 1e9, 1), "dryRun": dry}))
