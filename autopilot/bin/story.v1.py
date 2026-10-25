#!/usr/bin/env python3
"""Make one Instagram Story (1080x1920) from real clip footage.
Usage:
  story.py video <clip.mp4> <out.mp4> --start S --len L --top "TEXT" [--bottom "TEXT"] [--credit "@handle on Kick"]
  story.py image <clip.mp4|frame.jpg> <out.jpg> --at S --top "TEXT" [--bottom "TEXT"] [--credit "..."]
Text sits inside Instagram's story safe zone (top UI ~0-220 px, reply bar ~1700-1920 px).
Prints JSON {out, seconds|null, sha256}."""
import json, os, subprocess, sys, hashlib
FONT = os.path.expanduser("~/byb/fonts/Poppins-Bold.ttf")
def opt(n, d=""):
    return sys.argv[sys.argv.index(n)+1] if n in sys.argv else d
def esc(s):
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")
def fs_for(text, maxfs):
    return min(maxfs, int(1080 * 0.86 / (0.64 * max(len(text), 1))))
def overlays(top, bottom, credit):
    v = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
    if top:
        v += (f",drawtext=fontfile={FONT}:text='{esc(top)}':fontsize={fs_for(top, 78)}:fontcolor=black"
              f":box=1:boxcolor=white@0.96:boxborderw=22:x=(w-text_w)/2:y=270")
    if bottom:
        v += (f",drawtext=fontfile={FONT}:text='{esc(bottom)}':fontsize={fs_for(bottom, 60)}:fontcolor=white"
              f":box=1:boxcolor=black@0.62:boxborderw=18:x=(w-text_w)/2:y=1520")
    if credit:
        v += (f",drawtext=fontfile={FONT}:text='{esc(credit)}':fontsize=32:fontcolor=white@0.95"
              f":box=1:boxcolor=black@0.45:boxborderw=12:x=(w-text_w)/2:y=1640")
    return v
def dur(p):
    return float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",p]).decode().strip())
def main():
    mode, src, out = sys.argv[1], sys.argv[2], sys.argv[3]
    top, bottom, credit = opt("--top"), opt("--bottom"), opt("--credit")
    vf = overlays(top, bottom, credit)
    if mode == "video":
        start, ln = float(opt("--start", "0")), float(opt("--len", "7"))
        ln = max(3.2, min(ln, 15))
        subprocess.run(["ffmpeg","-y","-loglevel","error","-ss",f"{start:.2f}","-i",src,"-t",f"{ln:.2f}","-vf",vf+",fps=30",
                        "-af","loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000","-ac","2","-ar","48000",
                        "-c:v","libx264","-preset","veryfast","-crf","19","-pix_fmt","yuv420p","-c:a","aac","-b:a","128k",
                        "-movflags","+faststart",out], check=True)
        secs = round(dur(out), 2)
    else:
        at = float(opt("--at", "0"))
        inp = ["-i", src] if src.lower().endswith((".jpg", ".png")) else ["-ss", f"{at:.2f}", "-i", src]
        subprocess.run(["ffmpeg","-y","-loglevel","error"] + inp + ["-frames:v","1","-vf",vf,"-q:v","3",out], check=True)
        secs = None
    print(json.dumps({"out": out, "seconds": secs, "sha256": hashlib.sha256(open(out,"rb").read()).hexdigest()[:16]}))
if __name__ == "__main__":
    main()
