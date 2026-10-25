#!/usr/bin/env python3
"""16:9 -> 9:16 reframe that follows faces, with hard cuts at scene changes (never pans across a cut).
Usage: reframe.py <in.mp4> <out.mp4> [--every 0.5] [--deadzone 0.08]
Per scene: faces sampled every 0.5 s (MediaPipe BlazeFace). One face -> crop centred on the scene's median face x
(re-centres only when the face drifts beyond the deadzone, hard cut, anti-jitter). Two faces steady -> SPLIT
(each face cropped 9:8, stacked). No face -> centre crop. Output 1080x1920, H.264 + AAC."""
import json, os, statistics, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import now_iso, log

MODEL = os.path.expanduser("~/autopilot/models/blaze_face_short_range.tflite")

def opt(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default

def scenes(path):
    from scenedetect import detect, ContentDetector
    sc = detect(path, ContentDetector(threshold=27.0))
    return [(s.seconds if hasattr(s, "seconds") else s.get_seconds(), e.seconds if hasattr(e, "seconds") else e.get_seconds()) for s, e in sc]

def faces(path, every):
    import cv2, mediapipe as mp
    from mediapipe.tasks.python.vision import face_detector
    from mediapipe.tasks.python.core import base_options as bo
    det = face_detector.FaceDetector.create_from_options(face_detector.FaceDetectorOptions(
        base_options=bo.BaseOptions(model_asset_path=MODEL), min_detection_confidence=0.5))
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    W, H = cap.get(3), cap.get(4)
    step = max(1, int(round(fps * every)))
    out, i = [], 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if i % step == 0:
            r = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)))
            fs = sorted(((d.bounding_box.origin_x + d.bounding_box.width / 2) / W, d.bounding_box.width / W) for d in r.detections)
            out.append((i / fps, fs))
        i += 1
    dur = i / fps
    try:
        det.close()
    except Exception:
        pass
    return out, W, H, fps, dur

def plan(samples, scs, dur, dead):
    if not scs:
        scs = [(0.0, dur)]
    segs = []
    for a, b in scs:
        pts = [(t, f) for t, f in samples if a <= t < b]
        two = [fs for t, fs in pts if len(fs) == 2]
        if pts and len(two) >= 0.6 * len(pts):
            segs.append({"a": a, "b": b, "mode": "split", "x1": statistics.median(f[0][0] for f in two), "x2": statistics.median(f[1][0] for f in two)})
            continue
        seen = [(t, fs[0][0] if len(fs) == 1 else max(fs, key=lambda z: z[1])[0]) for t, fs in pts if fs]
        if not seen:
            segs.append({"a": a, "b": b, "mode": "centre", "x": 0.5}); continue
        # anti-jitter: hold a position until the face leaves the deadzone for 3 samples, then hard-cut to the new spot
        cur, start, run = seen[0][1], a, []
        for t, x in seen:
            run.append(x)
            if len(run) >= 3 and all(abs(r - cur) > dead for r in run[-3:]) and max(run[-3:]) - min(run[-3:]) < dead:
                cut_at = t - (len(run[-3:]) - 1) * 0.5
                if cut_at - start >= 1.0:
                    segs.append({"a": start, "b": cut_at, "mode": "track", "x": cur}); start = cut_at
                cur, run = statistics.median(run[-3:]), []
        segs.append({"a": start, "b": b, "mode": "track", "x": cur})
    return segs

def render(src, dst, segs, W, H):
    cw = int(H * 9 / 16) // 2 * 2
    parts, labels = [], []
    for k, s in enumerate(segs):
        a, b = s["a"], s["b"]
        if s["mode"] == "split":
            hw = int(H * 9 / 8) // 2 * 2 if int(H * 9 / 8) <= W else int(W) // 2 * 2
            hh = int(hw * 8 / 9) // 2 * 2
            x1 = max(0, min(W - hw, s["x1"] * W - hw / 2)); x2 = max(0, min(W - hw, s["x2"] * W - hw / 2))
            parts.append(f"[0:v]trim={a}:{b},setpts=PTS-STARTPTS,split[s{k}a][s{k}b];"
                         f"[s{k}a]crop={hw}:{hh}:{int(x1)}:{int((H - hh) / 2)},scale=1080:960[t{k}];"
                         f"[s{k}b]crop={hw}:{hh}:{int(x2)}:{int((H - hh) / 2)},scale=1080:960[u{k}];"
                         f"[t{k}][u{k}]vstack,setsar=1[v{k}]")
        else:
            x = max(0, min(W - cw, s["x"] * W - cw / 2))
            parts.append(f"[0:v]trim={a}:{b},setpts=PTS-STARTPTS,crop={cw}:{int(H)}:{int(x)}:0,scale=1080:1920:flags=lanczos,setsar=1[v{k}]")
        labels.append(f"[v{k}]")
    fc = ";".join(parts) + ";" + "".join(labels) + f"concat=n={len(segs)}:v=1:a=0,fps=30,format=yuv420p[v]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-filter_complex", fc, "-map", "[v]", "-map", "0:a?",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", dst], check=True)

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "usage"})); return
    src, dst = sys.argv[1], sys.argv[2]
    every, dead = float(opt("--every", "0.5")), float(opt("--deadzone", "0.08"))
    t0 = time.time()
    samples, W, H, fps, dur = faces(src, every)
    scs = scenes(src)
    segs = plan(samples, scs, dur, dead)
    render(src, dst, segs, W, H)
    info = {"at": now_iso(), "out": dst, "scenes": len(scs), "segments": [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in s.items()} for s in segs],
            "seconds": round(time.time() - t0, 1)}
    json.dump(info, open(dst + ".plan.json", "w"))
    log("reframe", {"src": os.path.basename(src), "segments": len(segs)})
    print(json.dumps(info))

if __name__ == "__main__":
    main()
