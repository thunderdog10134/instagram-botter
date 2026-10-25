#!/usr/bin/env python3
"""assemble2.py <beats.json> <host.mp4> <out.mp4> [--page cards] [--text "JADE CARGILL AUTO /43"] [--no-bed]
Format v2.2 assembly (Oct 25; v2.1 + Paper Crab additions: a title plate per sentence at y~220, an optional second number
beat at 2/3, a before/after chip above the CTA, a pop sound on every plate, a price plate with a cha-ching when the item has a sold comp; v6 quality: CRF 12 intermediates, CRF 17 final):
  VIDEO  host (handheld humanizer, clean voice) + claim number (Anton, gold) springing in at 0.3 s
         -> white flash -> framed clip: zoom plan (punches x1.24 + pushes), top blur band, bottom scrim,
            chip (Bebas), badge (Anton slab, tilted), captions (Bebas caps, gold keyword, outline+shadow, no box)
         -> last frame held 2.5 s, darkened, CTA type (COMMENT / PULL) -> host first frame 0.4 s (loop)
  AUDIO  host voice: clean (highpass 80, presence +3 dB @ 3 kHz, de-ess, compressor) not phone-mic
         stream audio ducked -9 dB under the host, full after; synth bed under everything (-26 dB), riser 1.6 s into
         the first punch, sub impact on each punch, whoosh on every element fly-in, tick on every caption,
         final loudnorm I=-14 TP=-1.5.  Prints JSON {out, seconds, sha256}."""
import sys, os, json, subprocess, tempfile, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit
def opt(n, d): return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d
def dur(p): return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p]).decode())
def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: sys.stderr.write(r.stderr[-2000:]); sys.exit(1)
def spring(t0, t1, y_final, h, side="down"):
    start = y_final + (h + 40 if side == "down" else -(h + 40))
    k = f"(1-exp(-6.5*(t-{t0}))*cos(9*(t-{t0})))"
    enter = f"({start}+({y_final}-{start})*{k})"; leave = f"({y_final}+({start}-{y_final})*min(1,(t-{t1}+0.18)/0.18))"
    return f"if(lt(t,{t0}+0.42),{enter},if(gt(t,{t1}-0.18),{leave},{y_final}))"
HOST_VF = ("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,scale=1188:2112,"
           "crop=1080:1920:x='54+26*sin(t*1.1)+9*sin(t*5.7+2)+4*sin(t*13.1)':y='96+20*sin(t*0.8+1)+8*cos(t*6.3)+3*cos(t*11.7)',"
           "rotate='0.007*sin(t*1.7)+0.002*sin(t*9.3)':ow=1080:oh=1920:c=black,eq=brightness='0.02*sin(t*0.7+0.4)':eval=frame,"
           "vignette=angle=PI/4.6:x0=w*0.42:y0=h*0.45,colorbalance=rs=.03:bs=-.03,eq=contrast=1.05:saturation=1.02,noise=alls=6:allf=t+u")
HOST_AF = "highpass=f=80,equalizer=f=3000:t=q:w=1.0:g=3,equalizer=f=180:t=q:w=1.2:g=1.5,deesser=i=0.4,acompressor=threshold=-18dB:ratio=3:attack=8:release=120:makeup=3,aresample=48000,aformat=channel_layouts=stereo"
def main():
    bj, host, out = sys.argv[1:4]; page = opt("--page", "cards"); text = opt("--text", ""); bed_on = "--no-bed" not in sys.argv
    P = json.load(open(bj)); clip = P["clip"]; D = P["dur"]; HOLD = 2.5
    with tempfile.TemporaryDirectory() as t:
        # ---- 1. host segment: humanized video, clean voice, sticker text (Anton), claim number
        hd = dur(host) - 0.15
        K = {"num": kit.number(P["claim"]["text"], os.path.join(t, "num.png"), page)} if P["claim"]["text"] else {}
        sticker = kit.badge(text, os.path.join(t, "sticker.png"), page, size=58) if text else None
        hin = ["-i", host]; hchain = f"[0:v]{HOST_VF}[h0]"; cur = "h0"; n = 1
        if sticker:
            hin += ["-i", sticker[0]]; hchain += f";[{cur}][{n}:v]overlay=x='(W-{sticker[1]})/2':y='{spring(0.25, hd, 300, sticker[2], 'up')}':enable='gte(t,0.25)'[h{n}]"; cur = f"h{n}"; n += 1
        if "num" in K:
            w, hgt = K["num"][1:]; hin += ["-i", K["num"][0]]; hchain += f";[{cur}][{n}:v]overlay=x='(W-{w})/2':y='{spring(0.45, hd, 520, hgt, 'down')}':enable='gte(t,0.45)'[h{n}]"; cur = f"h{n}"; n += 1
        hchain += f";[{cur}]fps=30,format=yuv420p[hv];[0:a]{HOST_AF}[ha]"
        hv = os.path.join(t, "host.mp4"); g = os.path.join(t, "hg.txt"); open(g, "w").write(hchain)
        run(["ffmpeg", "-y", "-loglevel", "error"] + hin + ["-filter_complex_script", g, "-map", "[hv]", "-map", "[ha]", "-t", f"{hd:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", hv])
        # ---- 2. clip: zoom plan + overlays (new kit) ; audio plain for now (mixed in step 4)
        K["chip"] = kit.chip(P["chip"]["text"], os.path.join(t, "chip.png"), page) if P["chip"]["text"] else None
        K["badge"] = kit.badge(P["badge"]["text"], os.path.join(t, "badge.png"), page) if P["badge"]["text"] else None
        K["cta"] = kit.cta(P["cta"]["keyword"], os.path.join(t, "cta.png"), page); K["scrim"] = kit.scrim(os.path.join(t, "scrim.png"))
        caps = [(c, kit.captionbox(c["words"], os.path.join(t, f"cap{i}.png"), page, keyword=c["keyword"])) for i, c in enumerate(P["captions"])]
        z = "1"
        for p in P["punches"]:
            a = p["t"]; z = f"if(between(t,{a},{a+0.18}),1+0.24*(t-{a})/0.18,if(between(t,{a+0.18},{a+0.58}),1.24,if(between(t,{a+0.58},{a+0.83}),1.24-0.24*(t-{a+0.58})/0.25,{z})))"
        for p in P["pushes"]:
            a, b = p["t0"], p["t1"]; z = f"if(between(t,{a},{b}),1+0.06*(t-{a})/({b}-{a}),{z})"
        zoom = f"scale=w='iw*({z})':h='ih*({z})':eval=frame,crop=1080:1920:(iw-1080)/2:(ih-1920)*0.42,tpad=stop_mode=clone:stop_duration={HOLD}"
        bt = P.get("blurtop", 0)
        if bt: zoom += f",split[m][tb];[tb]crop=1080:{bt}:0:0,boxblur=20:2[tbb];[m][tbb]overlay=0:0"
        inputs = ["-i", clip]; chain = f"[0:v]{zoom},setsar=1[v0]"; cur = "v0"; n = 1
        def ov(path, x, yexpr, t0, t1):
            nonlocal chain, cur, n, inputs
            inputs += ["-i", path]; chain += f";[{cur}][{n}:v]overlay=x='{x}':y='{yexpr}':enable='between(t,{t0},{t1})'[v{n}]"; cur = f"v{n}"; n += 1
        ov(K["scrim"][0], 0, "1400", 0, D + HOLD)
        if K["chip"]:
            w, hgt = K["chip"][1:]; c = P["chip"]; ov(K["chip"][0], 40, spring(c["t0"], c["t1"], 1300, hgt, "up"), c["t0"], c["t1"])
        if K["badge"]:
            w, hgt = K["badge"][1:]; b = P["badge"]; ov(K["badge"][0], f"(W-{w})/2", spring(b["t0"], b["t1"], 400, hgt, "up"), b["t0"], b["t1"])
        for c, (path, w, hgt) in caps:
            ov(path, f"(W-{w})/2", spring(c["t0"], c["t1"], 1440, hgt, "down"), c["t0"], c["t1"])
        for i, tt in enumerate(P.get("titles") or []):                                    # v2.2 sentence title plates
            path, w, hgt = kit.title(tt["text"], os.path.join(t, f"title{i}.png"), page)
            ov(path, "40", spring(tt["t0"], tt["t1"], 200, hgt, "up"), tt["t0"], tt["t1"])      # left, clear of the face PiP
        c2 = P.get("claim2")
        if c2 and c2.get("text"):                                                           # v2.2 second number beat
            path, w, hgt = kit.number(c2["text"], os.path.join(t, "num2.png"), page, size=200)
            ov(path, f"(W-{w})/2", spring(c2["t0"], c2["t1"], 560, hgt, "down"), c2["t0"], c2["t1"])
        pr = P.get("price")
        if pr and pr.get("text"):                                                   # v2.2 price plate (sold comp only)
            path, w, hgt = kit.price(pr["text"], os.path.join(t, "price.png"), page)
            ov(path, f"(W-{w})/2", spring(pr["t0"], pr["t1"], 640, hgt, "down"), pr["t0"], pr["t1"])
        ct = P["cta"]; w, hgt = K["cta"][1:]
        chain += f";[{cur}]eq=brightness=-0.15:saturation=0.8:enable='gte(t,{ct['t0']})'[vd]"; cur = "vd"
        ov(K["cta"][0], f"(W-{w})/2", spring(ct["t0"], ct["t1"] + 1, 760, hgt, "down"), ct["t0"], ct["t1"] + 1)
        ba = P.get("beforeafter")
        if ba:                                                                               # v2.2 before/after chip above the CTA
            path, w, hgt = kit.beforeafter(ba["before"], ba["after"], os.path.join(t, "ba.png"), page)
            ov(path, f"(W-{w})/2", spring(ct["t0"] + 0.25, ct["t1"] + 1, 600, hgt, "up"), ct["t0"] + 0.25, ct["t1"] + 1)
        chain += f";[{cur}]fps=30,format=yuv420p[vclip]"
        vc = os.path.join(t, "clip2.mp4"); g = os.path.join(t, "graph.txt"); open(g, "w").write(chain)
        run(["ffmpeg", "-y", "-loglevel", "error"] + inputs + ["-filter_complex_script", g, "-map", "[vclip]", "-map", "0:a", "-t", f"{D+HOLD:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", vc])
        # ---- 3. loop tail
        loop = os.path.join(t, "loop.mp4"); f0 = os.path.join(t, "f0.png")
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", hv, "-frames:v", "1", f0])
        run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", f0, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "0.4", "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", loop])
        # ---- 4. video concat + sound design mix
        total = hd + D + HOLD + 0.4; sfx = os.path.join(t, "sfx"); subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "sfx2.py"), sfx, f"{total+1:.1f}"], check=True, capture_output=True)
        ev = []  # (file, time, gain dB)
        off = hd
        ev.append(("whoosh", 0.25, -8)); ev.append(("whoosh", 0.45, -6))                       # sticker + number fly-in on the host
        ev.append(("whoosh", hd - 0.05, -4))                                                   # the cut
        if P["punches"]:
            first = off + P["punches"][0]["t"]; ev.append(("riser", first - 1.6, -10))
            for p in P["punches"]: ev.append(("impact", off + p["t"], -3))
        for p in P["pushes"][:3]: ev.append(("whoosh", off + p["t0"], -14))
        if K["chip"]: ev.append(("whoosh", off + P["chip"]["t0"], -12))
        if K["badge"]: ev.append(("whoosh", off + P["badge"]["t0"], -8)); ev.append(("impact", off + P["badge"]["t0"], -9))
        for c, _ in caps: ev.append(("tick", off + c["t0"], -10))
        for tt in (P.get("titles") or []): ev.append(("pop", off + tt["t0"], -10))          # v2.2: every plate lands with a sound
        if c2 and c2.get("text"): ev.append(("whoosh", off + c2["t0"], -8)); ev.append(("impact", off + c2["t0"], -9))
        if ba: ev.append(("pop", off + ct["t0"] + 0.25, -6))
        if pr and pr.get("text"): ev.append(("chaching", off + pr["t0"], -3))        # the cha-ching lands with the price
        ev.append(("riser", off + ct["t0"] - 1.2, -12)); ev.append(("impact", off + ct["t0"], -2)); ev.append(("whoosh", off + ct["t0"], -6))
        ain = ["-i", hv, "-i", vc, "-i", loop]; k = 3; mix = []
        if bed_on: ain += ["-i", f"{sfx}/bed.wav"]; mix.append(f"[{k}:a]volume=-26dB,atrim=0:{total:.2f}[bed]"); k += 1
        for i, (name, at, gdb) in enumerate(ev):
            if at < 0: continue
            ain += ["-i", f"{sfx}/{name}.wav"]; mix.append(f"[{k}:a]volume={gdb}dB,adelay={int(at*1000)}|{int(at*1000)}[s{i}]"); k += 1
        # programme: host voice (full) + clip audio ducked while host speaks (clip starts after host, so just concat), then loop silence
        prog = (f"[0:a]aresample=48000,aformat=channel_layouts=stereo[a0];[1:a]aresample=48000,aformat=channel_layouts=stereo,"
                f"loudnorm=I=-15:TP=-1.5:LRA=9,afade=t=in:st=0:d=0.25[a1];[2:a]aresample=48000,aformat=channel_layouts=stereo[a2];[a0][a1][a2]concat=n=3:v=0:a=1[prog]")
        labels = "".join(f"[s{i}]" for i, (name, at, g) in enumerate(ev) if at >= 0) + ("[bed]" if bed_on else "")
        nmix = 1 + len([e for e in ev if e[1] >= 0]) + (1 if bed_on else 0)
        fc = (f"[0:v]fps=30,format=yuv420p[va];[1:v]fps=30,format=yuv420p[vb];[2:v]fps=30,format=yuv420p[vc];[va][vb][vc]concat=n=3:v=1:a=0[v];"
              f"[v]drawbox=c=white@0.9:t=fill:enable='between(t,{hd:.2f},{hd+0.17:.2f})'[vo];" + prog + ";" + ";".join(mix) +
              f";[prog]{labels}amix=inputs={nmix}:duration=first:normalize=0,alimiter=limit=0.95,loudnorm=I=-14:TP=-1.5:LRA=11[au]")
        g = os.path.join(t, "mix.txt"); open(g, "w").write(fc)
        run(["ffmpeg", "-y", "-loglevel", "error"] + ain + ["-filter_complex_script", g, "-map", "[vo]", "-map", "[au]", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-maxrate", "14M", "-bufsize", "28M", "-profile:v", "high", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out])
    sha = hashlib.sha256(open(out, "rb").read()).hexdigest()
    print(json.dumps({"out": out, "seconds": round(dur(out), 2), "sha256": sha, "sfxEvents": len(ev), "events": P["check"]}))
if __name__ == "__main__": main()
