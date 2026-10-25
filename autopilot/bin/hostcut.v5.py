#!/usr/bin/env python3
"""Assemble a host-intro Reel: AI host says the hook, then a hard cut to the real clip.
Usage: hostcut.py <host.mp4> <clip.mp4> <out.mp4> [--text "BRON BREAKKER REFRACTOR"] [--trim 0.15]
- host is scaled/padded to 1080x1920, audio normalised; optional bold text sticker over the host (upper third)
- clip keeps its own captions/zooms; audio loudness matched to the host
- a 6-frame white flash on the cut; prints JSON {out, seconds, sha256}."""
import json, os, subprocess, sys, hashlib, tempfile
FONT = os.path.expanduser("~/byb/fonts/Poppins-Bold.ttf")
def opt(n, d):
    return sys.argv[sys.argv.index(n)+1] if n in sys.argv else d
def dur(p):
    return float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",p]).decode().strip())
def main():
    host, clip, out = sys.argv[1], sys.argv[2], sys.argv[3]
    text, trim = opt("--text", ""), float(opt("--trim", "0.15"))
    hostcap, credit = opt("--hostcap", ""), opt("--credit", "")   # --hostcap: the spoken line (vocabulary hint) -> word captions on the host; --credit: small label on the clip
    humanize = "--no-humanize" not in sys.argv   # handheld drift + micro shake + grain + slight colour cast + vignette on the host segment
    hd = dur(host) - trim
    with tempfile.TemporaryDirectory() as t:
        h, c = os.path.join(t,"h.mp4"), os.path.join(t,"c.mp4")
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30"
        if humanize:
            # slow push-in with a wobble, a tiny rotation jitter, phone-ish grain, slightly warm/green cast, soft vignette
            vf += (",scale=1188:2112,"
                   # bigger, less regular handheld drift + a faster micro-shake
                   "crop=1080:1920:x='54+26*sin(t*1.1)+9*sin(t*5.7+2)+4*sin(t*13.1)':y='96+20*sin(t*0.8+1)+8*cos(t*6.3)+3*cos(t*11.7)',"
                   "rotate='0.007*sin(t*1.7)+0.002*sin(t*9.3)':ow=1080:oh=1920:c=black,"
                   # auto-exposure hunting: slow brightness wander, evaluated per frame
                   "eq=brightness='0.02*sin(t*0.7+0.4)':eval=frame,"
                   # autofocus 'breath': a brief soft blur every ~2.3 s
                   "boxblur=1:1:enable='between(mod(t\\,2.3)\\,1.1\\,1.3)',"
                   # uneven "one lamp" light: off-centre vignette, warm cast, slightly crushed shadows, phone grain
                   "vignette=angle=PI/4.6:x0=w*0.42:y0=h*0.45,"
                   "colorbalance=rs=.04:gs=.01:bs=-.04:rm=.02:bm=-.02,"
                   "eq=contrast=1.04:brightness=0.0:saturation=0.94,"
                   "noise=alls=9:allf=t+u,"
                   "unsharp=5:5:-0.3")   # a touch soft, like a front camera
        if text:
            safe = text.replace("\\","\\\\").replace(":", "\\:").replace("'", "’")
            fs = min(84, int(1080 * 0.9 / (0.64 * max(len(text), 1))))   # Poppins Bold caps ~0.64 em wide: keep the sticker inside the frame
            vf += (f",drawtext=fontfile={FONT}:text='{safe}':fontsize={fs}:fontcolor=white:borderw=6:bordercolor=black"
                   f":x=(w-text_w)/2:y=300:enable='gte(t,0.3)'")
        enc = ["-ac","2","-ar","48000","-c:v","libx264","-preset","veryfast","-crf","18","-pix_fmt","yuv420p","-c:a","aac","-b:a","160k"]
        if humanize:
            # phone-mic character on the host voice: band-limited, a little boxy, light compression,
            # plus a quiet pink-noise room tone and a faint 60 Hz hum underneath
            fc = (f"[0:v]{vf}[vout];"
                  "[0:a]highpass=f=140,lowpass=f=6800,equalizer=f=420:t=q:w=1.2:g=2,equalizer=f=2800:t=q:w=1.0:g=1.5,"
                  "acompressor=threshold=-20dB:ratio=3:attack=12:release=180:makeup=2,aresample=48000[va];"
                  "anoisesrc=d=60:c=pink:r=48000:a=0.004[n];"
                  "sine=f=60:r=48000:d=60,volume=0.004[h];"
                  "[va][n][h]amix=inputs=3:duration=first:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[aout]")
            subprocess.run(["ffmpeg","-y","-loglevel","error","-i",host,"-t",f"{hd:.2f}","-filter_complex",fc,
                            "-map","[vout]","-map","[aout]"] + enc + [h], check=True)
        else:
            subprocess.run(["ffmpeg","-y","-loglevel","error","-i",host,"-t",f"{hd:.2f}","-vf",vf,
                            "-af","loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000"] + enc + [h], check=True)
        if hostcap:
            hc = os.path.join(t, "hc.mp4")
            subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "captions.py"), h, hc,
                            "--style", "opus", "--margin", "520", "--model", "small.en", "--prompt", hostcap], check=True, capture_output=True)
            h = hc
        clip_vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30"
        if credit:
            safe_c = credit.replace("\\","\\\\").replace(":", "\\:").replace("'", "\u2019")
            # credit sits below the stream ticker, left of the face-cam PiP; '|' in the text becomes a line break
            safe_c = safe_c.replace("|", "\n")
            clip_vf += (f",drawtext=fontfile={FONT}:text='{safe_c}':fontsize=34:fontcolor=white@0.95:line_spacing=6"
                        f":box=1:boxcolor=black@0.45:boxborderw=14:x=40:y=170")
        subprocess.run(["ffmpeg","-y","-loglevel","error","-i",clip,"-vf",clip_vf,
                        "-af","loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000","-ac","2","-ar","48000",
                        "-c:v","libx264","-preset","veryfast","-crf","18","-pix_fmt","yuv420p","-c:a","aac","-b:a","160k",c],check=True)
        lst = os.path.join(t,"l.txt"); open(lst,"w").write(f"file '{h}'\nfile '{c}'\n")
        # concat then a short white flash at the cut
        cat = os.path.join(t,"cat.mp4")
        subprocess.run(["ffmpeg","-y","-loglevel","error","-f","concat","-safe","0","-i",lst,"-c","copy",cat],check=True)
        subprocess.run(["ffmpeg","-y","-loglevel","error","-i",cat,"-vf",
                        f"drawbox=enable='between(t,{hd:.2f},{hd+0.12:.2f})':c=white@0.85:t=fill",
                        "-c:v","libx264","-preset","veryfast","-crf","18","-pix_fmt","yuv420p","-c:a","copy","-movflags","+faststart",out],check=True)
    sha = hashlib.sha256(open(out,"rb").read()).hexdigest()[:16]
    print(json.dumps({"out": out, "seconds": round(dur(out),2), "sha256": sha}))
if __name__ == "__main__": main()
