#!/usr/bin/env python3
"""hls_slice.py <m3u8 url> <start_s> <len_s> <out.mp4>  -> cuts a slice out of an HLS VOD by downloading only the segments
that cover [start, start+len] (parallel curl), concatenating them and remuxing to mp4 (no re-encode). Used for Twitch VODs,
where ffmpeg -ss on the playlist stalls. Prints JSON {ok, out, segments, seconds}."""
import json, os, subprocess, sys, time, tempfile, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor
url, start, length, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
t0 = time.time()
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
text = urllib.request.urlopen(req, timeout=30).read().decode()
base = url.rsplit("/", 1)[0] + "/"
segs, t, dur, init = [], 0.0, None, None
for line in text.splitlines():
    if line.startswith("#EXT-X-MAP:"):
        m = line.split('URI="', 1)[1].split('"', 1)[0]; init = urllib.parse.urljoin(base, m)
    if line.startswith("#EXTINF:"):
        dur = float(line[8:].split(",")[0])
    elif line and not line.startswith("#") and dur is not None:
        segs.append((t, dur, urllib.parse.urljoin(base, line))); t += dur; dur = None
pick = [s for s in segs if s[0] + s[1] > start and s[0] < start + length]
if not pick:
    print(json.dumps({"error": "no segments in range", "total": t})); sys.exit(1)
tmp = tempfile.mkdtemp(prefix="hls_")
def get(i_s):
    i, (st, d, u) = i_s
    p = os.path.join(tmp, f"{i:05d}.ts")
    for attempt in range(3):
        r = subprocess.run(["curl", "-sS", "-f", "-L", "-A", "Mozilla/5.0", "-o", p, u], capture_output=True)
        if r.returncode == 0 and os.path.getsize(p) > 0:
            return p
        time.sleep(1 + attempt)
    raise RuntimeError(f"segment {i} failed")
with ThreadPoolExecutor(max_workers=6) as ex:
    files = list(ex.map(get, enumerate(pick)))
off = start - pick[0][0]
if init:   # fragmented mp4 (CMAF): init segment + fragments concatenated byte-wise is one valid stream
    ip = os.path.join(tmp, "init.mp4")
    subprocess.run(["curl", "-sS", "-f", "-L", "-A", "Mozilla/5.0", "-o", ip, init], check=True)
    big = os.path.join(tmp, "all.mp4")
    with open(big, "wb") as w:
        for f in [ip] + files:
            w.write(open(f, "rb").read())
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", big, "-ss", f"{off:.2f}", "-t", f"{length}", "-c", "copy",
                        "-movflags", "+faststart", out], capture_output=True, text=True)
    os.remove(ip); os.remove(big)
else:      # MPEG-TS segments
    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("".join(f"file '{f}'\n" for f in files))
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-ss", f"{off:.2f}", "-t", f"{length}",
                        "-c", "copy", "-bsf:a", "aac_adtstoasc", "-movflags", "+faststart", out], capture_output=True, text=True)
    os.remove(lst)
for f in files: os.remove(f)
os.rmdir(tmp)
if r.returncode != 0:
    print(json.dumps({"error": r.stderr.strip()[-300:]})); sys.exit(1)
print(json.dumps({"ok": True, "out": out, "segments": len(pick), "firstSegStart": round(pick[0][0], 1), "seconds": round(time.time() - t0, 1)}))
