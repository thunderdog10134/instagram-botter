#!/usr/bin/env python3
"""Vertical reframe with the breaker's face cam as a picture-in-picture in the top corner.
Usage: pipframe.py <in.mp4> <out.mp4> --card W:H:X:Y --face W:H:X:Y [--corner tr|tl] [--pipw 460]
--card: crop of the card cam in source pixels (any aspect; scaled to fill 1080x1920)
--face: crop of the face cam in source pixels. Prints JSON."""
import json, subprocess, sys
def opt(n, d):
    return sys.argv[sys.argv.index(n)+1] if n in sys.argv else d
src, dst = sys.argv[1], sys.argv[2]
card, face = opt("--card", None), opt("--face", None)
corner, pipw = opt("--corner", "tr"), int(opt("--pipw", "460"))
if not card or not face:
    print(json.dumps({"error": "need --card and --face"})); sys.exit(1)
fw, fh = [int(v) for v in face.split(":")[:2]]
piph = round(pipw * fh / fw / 2) * 2
x = "W-w-40" if corner == "tr" else "40"
fc = (f"[0:v]crop={card},scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[base];"
      f"[0:v]crop={face},scale={pipw}:{piph},setsar=1,"
      f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.9:t=4[pip];"
      f"[base][pip]overlay={x}:150:format=auto[v]")
subprocess.run(["ffmpeg","-y","-loglevel","error","-i",src,"-filter_complex",fc,"-map","[v]","-map","0:a?",
                "-c:v","libx264","-preset","veryfast","-crf","18","-pix_fmt","yuv420p","-c:a","copy",dst], check=True)
print(json.dumps({"out": dst, "card": card, "face": face, "pip": [pipw, piph], "corner": corner}))
