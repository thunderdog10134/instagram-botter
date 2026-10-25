#!/usr/bin/env python3
"""Vertical reframe with the breaker's face cam as a picture-in-picture in the top corner (v6, quality pass).
Usage: pipframe.py <in.mp4> <out.mp4> --card W:H:X:Y --face W:H:X:Y [--corner tr|tl] [--pipw 460] [--no-sr]
--card: crop of the card cam in source pixels (any aspect; scaled to fill 1080x1920)
--face: crop of the face cam in source pixels. Prints JSON.
v6 (Oct 25, Josh: "camera quality is poop"): the card crop is cleaned (temporal denoise against stream
compression flicker), upscaled with a small super-resolution net (FSRCNN x3, OpenCV dnn_superres, ~0.2 s/frame)
instead of a plain resize, lightly sharpened (CAS), and written near-lossless (CRF 10) so the later steps do not
stack compression on compression. Falls back to lanczos when OpenCV-contrib or the model is missing.
Runtime: about 2-3 min for a 15 s clip on the standard sandbox -> run it in the background and poll."""
import json, os, subprocess, sys
def opt(n, d):
    return sys.argv[sys.argv.index(n)+1] if n in sys.argv else d
src, dst = sys.argv[1], sys.argv[2]
card, face = opt("--card", None), opt("--face", None)
corner, pipw = opt("--corner", "tr"), int(opt("--pipw", "460"))
use_sr = "--no-sr" not in sys.argv
if not card or not face:
    print(json.dumps({"error": "need --card and --face"})); sys.exit(1)
fw, fh = [int(v) for v in face.split(":")[:2]]
_c = [int(v) for v in card.split(":")]
cw, ch = _c[0] // 2 * 2, _c[1] // 2 * 2          # yuv420 frames need even crop sizes
card = f"{cw}:{ch}:{_c[2]}:{_c[3]}"
piph = round(pipw * fh / fw / 2) * 2
x = "W-w-40" if corner == "tr" else "40"
FPS = "30"
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "10", "-pix_fmt", "yuv420p"]
PIP = (f"crop={face},scale={pipw}:{piph}:flags=lanczos,cas=0.5,setsar=1,"
       f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.9:t=4")
MODEL = os.path.expanduser("~/autopilot/ref/sr/FSRCNN_x3.pb")
CVPATH = "/home/user/pylib_cv"

def plain():
    fc = (f"[0:v]fps={FPS},crop={card},hqdn3d=0:0:4:4,"
          f"scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,cas=0.45,setsar=1[base];"
          f"[0:v]fps={FPS},{PIP}[pip];[base][pip]overlay={x}:150:format=auto[v]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-filter_complex", fc, "-map", "[v]", "-map", "0:a?"]
                   + ENC + ["-c:a", "copy", dst], check=True)
    return "lanczos"

def sr():
    sys.path.insert(0, CVPATH)
    import numpy as np, cv2
    from cv2 import dnn_superres
    if not os.path.exists(MODEL):
        raise RuntimeError("no model")
    net = dnn_superres.DnnSuperResImpl_create(); net.readModel(MODEL); net.setModel("fsrcnn", 3)
    # cover-fit size for the upscaled card, then centre-crop to 1080x1920
    k = max(1080 / cw, 1920 / ch)
    tw, th = int(round(cw * k / 2) * 2), int(round(ch * k / 2) * 2)
    ox, oy = (tw - 1080) // 2, (th - 1920) // 2
    dec = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", src, "-vf", f"fps={FPS},crop={card},hqdn3d=0:0:4:4",
                            "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
    fc = f"[0:v]cas=0.35,setsar=1[base];[1:v]fps={FPS},{PIP}[pip];[base][pip]overlay={x}:150:format=auto[v]"
    enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "1080x1920",
                            "-r", FPS, "-i", "-", "-i", src, "-filter_complex", fc, "-map", "[v]", "-map", "1:a?"]
                           + ENC + ["-c:a", "copy", "-shortest", dst], stdin=subprocess.PIPE)
    n, fsz = 0, cw * ch * 3
    while True:
        buf = dec.stdout.read(fsz)
        if len(buf) < fsz:
            break
        f = np.frombuffer(buf, np.uint8).reshape(ch, cw, 3)
        up = net.upsample(f)
        interp = cv2.INTER_AREA if up.shape[1] >= tw else cv2.INTER_LANCZOS4
        up = cv2.resize(up, (tw, th), interpolation=interp)[oy:oy + 1920, ox:ox + 1080]
        enc.stdin.write(np.ascontiguousarray(up).tobytes()); n += 1
    enc.stdin.close(); dec.wait(); rc = enc.wait()
    if rc != 0 or n == 0:
        raise RuntimeError("sr encode failed")
    return f"fsrcnn-x3 ({n} frames)"

method = None
if use_sr:
    try:
        method = sr()
    except Exception as e:
        method = None; err = str(e)[:120]
if not method:
    method = plain()
print(json.dumps({"out": dst, "card": card, "face": face, "pip": [pipw, piph], "corner": corner, "upscale": method}))
