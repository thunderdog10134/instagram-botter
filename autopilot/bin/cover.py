#!/usr/bin/env python3
"""Reel cover: the pulled card big, the host pointing at it, a price/number tag.
Usage: cover.py <clip_or_frame> <out.jpg> --host <host_cutout.png> [--at 9.4] [--card W:H:X:Y (crop of the card in the frame)]
       [--title "BRON BREAKKER REFRACTOR"] [--tag "$120"] [--tagnote "last sold"] [--pip W:H:X:Y (breaker face from the full frame)]
Frame is taken from the source (full 1280x720 stream frame or any image); the card crop is cut, tilted and dropped on a dark blurred
background; the host cutout (with alpha) is placed bottom-left pointing right; tag = big yellow pill. Prints JSON."""
import json, os, subprocess, sys, tempfile
from PIL import Image, ImageFilter, ImageDraw, ImageFont, ImageOps
FONT = os.path.expanduser("~/byb/fonts/Poppins-Bold.ttf")
def opt(n, d):
    return sys.argv[sys.argv.index(n)+1] if n in sys.argv else d
def crop4(s):
    w,h,x,y = [int(v) for v in s.split(":")]; return (x, y, x+w, y+h)
src, out = sys.argv[1], sys.argv[2]
host, at, card, pip = opt("--host", None), float(opt("--at", "0")), opt("--card", None), opt("--pip", None)
title, tag, tagnote = opt("--title", ""), opt("--tag", ""), opt("--tagnote", "")
W, H = 1080, 1920
with tempfile.TemporaryDirectory() as t:
    frame = os.path.join(t, "f.png")
    if src.lower().endswith((".jpg", ".jpeg", ".png")):
        Image.open(src).convert("RGB").save(frame)
    else:
        subprocess.run(["ffmpeg","-y","-loglevel","error","-ss",str(at),"-i",src,"-frames:v","1",frame], check=True)
    f = Image.open(frame).convert("RGB")
    cardimg = f.crop(crop4(card)) if card else f
    # background: the card region blown up, blurred and darkened
    bg = ImageOps.fit(cardimg, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(28))
    bg = Image.eval(bg, lambda v: int(v * 0.45))
    canvas = bg.convert("RGBA")
    # the card: big, slight tilt, soft shadow
    ch = int(H * 0.52); cw = int(cardimg.width * ch / cardimg.height)
    if cw > int(W * 0.78): cw = int(W * 0.78); ch = int(cardimg.height * cw / cardimg.width)
    c = cardimg.resize((cw, ch), Image.LANCZOS).convert("RGBA")
    c = c.rotate(-6, expand=True, resample=Image.BICUBIC)
    sh = Image.new("RGBA", c.size, (0,0,0,0)); sh.paste((0,0,0,170), (0,0,c.size[0],c.size[1]), c.split()[3]); sh = sh.filter(ImageFilter.GaussianBlur(24))
    cx, cy = W - c.width - 50, int(H * 0.17)
    canvas.alpha_composite(sh, (cx + 18, cy + 28)); canvas.alpha_composite(c, (cx, cy))
    # host cutout bottom-left, pointing at the card
    if host:
        hp = Image.open(host).convert("RGBA")
        hh = int(H * 0.50); hw = int(hp.width * hh / hp.height)
        hp = hp.resize((hw, hh), Image.LANCZOS)
        canvas.alpha_composite(hp, (-int(hw * 0.08), H - hh + 10))
    d = ImageDraw.Draw(canvas)
    def text_w(s, fs):
        return d.textlength(s, font=ImageFont.truetype(FONT, fs))
    # title top, auto-fit
    if title:
        fs = 96
        while text_w(title, fs) > W - 80 and fs > 40: fs -= 4
        fnt = ImageFont.truetype(FONT, fs); tw = text_w(title, fs)
        d.text(((W - tw) / 2, 90), title, font=fnt, fill="white", stroke_width=8, stroke_fill="black")
    # price / number pill, right-middle above the host's pointing hand
    if tag:
        fs = 120; fnt = ImageFont.truetype(FONT, fs); tw = text_w(tag, fs)
        px, py = W - tw - 150, int(H * 0.72)
        d.rounded_rectangle((px - 40, py - 20, px + tw + 40, py + fs + 20), radius=40, fill=(255, 214, 10, 255), outline="black", width=8)
        d.text((px, py - 6), tag, font=fnt, fill="black")
        if tagnote:
            fn = ImageFont.truetype(FONT, 40); nw = text_w(tagnote, 40)
            d.text((px + tw / 2 - nw / 2, py + fs + 36), tagnote, font=fn, fill="white", stroke_width=5, stroke_fill="black")
    canvas.convert("RGB").save(out, quality=92)
print(json.dumps({"out": out, "size": [W, H]}))
