#!/usr/bin/env python3
"""Make original warm-up content for a page (no credits; ffmpeg + ImageMagick only).
Usage: warm_post.py <job.json>
Job: {"username","kind":"intro"|"textreel"|"carousel"|"story","lines":[...],"title","displayName","source",
      "colors":{"bg","accent"},"iconUrl","coverUrl","outName","uploads":{"<file name>":"<PUT url>"}}
Output: {"files":[{"name","path","bytes","upload"}]} — files in ~/autopilot/out/warm/."""
import json, os, subprocess, sys, tempfile, time, urllib.request
from common import now_iso, log, emit, AP

FONT_DIR = os.path.expanduser("~/byb/fonts")
FONT = next((os.path.join(FONT_DIR, f) for f in ("Poppins-Bold.ttf", "Montserrat-VF.ttf", "TikTokSans.ttf") if os.path.exists(os.path.join(FONT_DIR, f))), "DejaVu-Sans-Bold")
WARM = os.path.join(AP, "out", "warm")

def sh(cmd, timeout=600):
    p = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout)[-400:])
    return p.stdout

def fetch(url, path):
    with urllib.request.urlopen(url, timeout=60) as r, open(path, "wb") as f:
        f.write(r.read())
    return path

def rgba(hexc, a):
    hexc = hexc.lstrip("#")
    return f"rgba({int(hexc[0:2],16)},{int(hexc[2:4],16)},{int(hexc[4:6],16)},{a})"

def bg(path, w, h, colors):
    sh(["convert", "-size", f"{w}x{h}", f"gradient:{colors.get('bg','#0b1f4b')}-#05050c",
        "(", "-size", f"{w}x{h}", "radial-gradient:" + rgba(colors.get("accent", "#e2b84a"), 0.16) + "-none", ")", "-compose", "over", "-composite", path])

def esc_file(tmp, i, text):
    p = os.path.join(tmp, f"l{i}.txt")
    open(p, "w").write(text)
    return p.replace(":", "\\:")

def reel(j, tmp, dest):
    lines = j.get("lines") or ["New page."]
    dur = max(9.0, min(12.0, 2.6 + 1.3 * len(lines) + 2.4))
    colors = j.get("colors", {})
    bgp = os.path.join(tmp, "bg.png"); bg(bgp, 1188, 2112, colors)
    inputs = ["-loop", "1", "-t", f"{dur}", "-i", bgp]
    filt = ["[0:v]scale=1188:2112,crop=1080:1920:x='54+40*sin(t/3)':y='96+60*sin(t/4)',format=yuv420p[b]"]
    last = "b"
    if j.get("iconUrl"):
        ip = fetch(j["iconUrl"], os.path.join(tmp, "icon.png"))
        inputs += ["-loop", "1", "-t", f"{dur}", "-i", ip]
    y0 = 1000 - 70 * len(lines)
    if j.get("iconUrl"):
        filt.append("[1:v]scale=260:260,format=rgba[ic]")
        filt.append(f"[{last}][ic]overlay=(W-w)/2:{y0 - 360}[bi]"); last = "bi"
    end = dur - 2.4
    for i, t in enumerate(lines):
        T = 0.6 + 1.3 * i
        tf = esc_file(tmp, i, t)
        alpha = f"if(lt(t,{T}),0,if(lt(t,{end}),min(1,(t-{T})/0.4),max(0,1-(t-{end})/0.4)))"
        filt.append(f"[{last}]drawtext=fontfile='{FONT}':textfile='{tf}':fontsize=84:fontcolor=white:borderw=3:bordercolor=black@0.35:"
                    f"x=(w-text_w)/2:y={y0 + 140 * i}:alpha='{alpha}'[t{i}]"); last = f"t{i}"
    name = j.get("displayName") or j.get("username", "")
    nf = esc_file(tmp, 99, name)
    filt.append(f"[{last}]drawtext=fontfile='{FONT}':textfile='{nf}':fontsize=110:fontcolor={colors.get('accent','#e2b84a')}:borderw=3:bordercolor=black@0.4:"
                f"x=(w-text_w)/2:y=(h-text_h)/2:alpha='if(lt(t,{end + 0.2}),0,min(1,(t-{end + 0.2})/0.4))'[v]")
    tone = f"aevalsrc='0.07*sin(2*PI*220*t)+0.05*sin(2*PI*277.18*t)+0.045*sin(2*PI*329.63*t)+0.03*sin(2*PI*440*t)':s=44100:d={dur}"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-f", "lavfi", "-i", tone,
           "-filter_complex", ";".join(filt) + f";[{2 if j.get('iconUrl') else 1}:a]tremolo=f=0.4:d=0.3,afade=t=in:d=1.5,afade=t=out:st={dur - 2}:d=2,aformat=channel_layouts=stereo[a]",
           "-map", "[v]", "-map", "[a]", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-t", f"{dur}", "-movflags", "+faststart", dest]
    sh(cmd)
    return [dest]

def card(text, path, colors, w=1080, h=1350, pointsize=70):
    bgp = path + ".bg.png"; bg(bgp, w, h, colors)
    sh(["convert", bgp, "(", "-size", f"{w - 160}x", "-background", "none", "-fill", "white", "-font", FONT, "-pointsize", str(pointsize),
        "-gravity", "center", f"caption:{text}", ")", "-gravity", "center", "-composite", "-quality", "92", path])
    os.remove(bgp)
    return path

def carousel(j, tmp, base):
    cards = (j.get("lines") or [])[:5] + [j.get("displayName") or j.get("username", "")]
    out = []
    for i, t in enumerate(cards):
        out.append(card(t, f"{base}-{i + 1}.jpg", j.get("colors", {}), pointsize=90 if i == len(cards) - 1 else 70))
    return out

def story(j, tmp, dest):
    colors = j.get("colors", {})
    if j.get("coverUrl"):
        cp = fetch(j["coverUrl"], os.path.join(tmp, "cover.jpg"))
        sh(["convert", cp, "-resize", "1080x1920^", "-gravity", "center", "-extent", "1080x1920",
            "-fill", colors.get("accent", "#e2b84a"), "-draw", "roundrectangle 290,1560 790,1680 30,30",
            "-fill", "black", "-font", FONT, "-pointsize", "52", "-annotate", "+0+700", "NEW ON THE PAGE", "-quality", "92", dest])
    else:
        card((j.get("lines") or ["New on the page"])[0], dest, colors, 1080, 1920, 84)
    return [dest]

def main():
    j = json.load(open(sys.argv[1]))
    os.makedirs(WARM, exist_ok=True)
    name = j.get("outName") or f"{j.get('username','page')}-{j.get('kind','textreel')}-{int(time.time())}"
    files = []
    with tempfile.TemporaryDirectory() as tmp:
        kind = j.get("kind", "textreel")
        try:
            if kind in ("intro", "textreel"):
                paths = reel(j, tmp, os.path.join(WARM, name + ".mp4"))
            elif kind == "carousel":
                paths = carousel(j, tmp, os.path.join(WARM, name))
            elif kind == "story":
                paths = story(j, tmp, os.path.join(WARM, name + ".jpg"))
            else:
                raise RuntimeError("unknown kind " + kind)
        except Exception as e:
            emit({"at": now_iso(), "files": [], "error": str(e)[-300:]}); return
    ups = j.get("uploads") or {}
    for p in paths:
        fn = os.path.basename(p)
        rec = {"name": fn, "path": p, "bytes": os.path.getsize(p)}
        if fn in ups:
            ctype = "video/mp4" if fn.endswith(".mp4") else "image/jpeg"
            r = subprocess.run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "-X", "PUT", "-H", f"Content-Type: {ctype}", "-H", "If-None-Match: *",
                                "--data-binary", f"@{p}", ups[fn]], capture_output=True, text=True, timeout=300)
            rec["upload"] = r.stdout.strip()
        files.append(rec)
    log("warm_post", {"kind": j.get("kind"), "files": len(files)})
    emit({"at": now_iso(), "files": files})

if __name__ == "__main__":
    main()
