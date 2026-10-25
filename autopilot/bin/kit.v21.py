#!/usr/bin/env python3
"""Overlay kit v2.1 (Oct 25): heavy condensed display type, gold keyword, outline + drop shadow, no black boxes.
Fonts (OFL, ~/byb/fonts): Anton (claim, badge, CTA), Bebas Neue (captions, chips). Pages: cards (accent #f2c14e gold), tcg (#ffd23f)."""
import os, sys, json
from PIL import Image, ImageDraw, ImageFont, ImageFilter
F = os.path.expanduser("~/byb/fonts")
PAGES = {"cards": {"accent": (242, 193, 78), "dark": (11, 31, 75)}, "tcg": {"accent": (255, 210, 63), "dark": (122, 16, 16)}}
def font(name, size):
    p = os.path.join(F, {"anton": "Anton-Regular.ttf", "bebas": "BebasNeue-Regular.ttf", "archivo": "ArchivoBlack-Regular.ttf", "poppins": "Poppins-Bold.ttf"}[name])
    return ImageFont.truetype(p, size)
def _save(im, path): im.save(path); return path, im.width, im.height
def _shadowed(w, h, draw_fn, blur=14, off=(0, 10), alpha=170):
    """draw_fn(d, dx, dy) draws the text; returns an RGBA with a soft drop shadow under it."""
    pad = 48
    sh = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0)); d = ImageDraw.Draw(sh)
    draw_fn(d, pad + off[0], pad + off[1], (0, 0, 0, alpha), shadow=True)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    im = Image.new("RGBA", sh.size, (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    draw_fn(d, pad, pad, None, shadow=False)
    return Image.alpha_composite(sh, im)
def _tw(f, t): return ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), t, font=f)
def number(text, path, page="cards", size=300):
    """Claim number: Anton, gold→white vertical gradient, thick dark outline, drop shadow, slight italic skew."""
    f = font("anton", size); x0, y0, x1, y1 = _tw(f, text); w, h = x1 - x0 + 40, y1 - y0 + 40
    acc = PAGES[page]["accent"]
    grad = Image.new("RGBA", (w, h)); g = ImageDraw.Draw(grad)
    for y in range(h):
        t = y / max(1, h - 1); c = tuple(int(acc[i] * (1 - t * 0.35) + 255 * t * 0.35) for i in range(3)) + (255,)
        g.line([(0, y), (w, y)], fill=c)
    mask = Image.new("L", (w, h), 0); ImageDraw.Draw(mask).text((20 - x0, 20 - y0), text, font=f, fill=255)
    fill = Image.new("RGBA", (w, h), (0, 0, 0, 0)); fill.paste(grad, (0, 0), mask)
    def draw(d, dx, dy, col, shadow):
        if shadow: d.text((dx + 20 - x0, dy + 20 - y0), text, font=f, fill=col)
        else: d.text((dx + 20 - x0, dy + 20 - y0), text, font=f, fill=(20, 20, 20, 255), stroke_width=14, stroke_fill=(20, 20, 20, 255))
    im = _shadowed(w, h, draw, blur=18, off=(0, 14))
    im.alpha_composite(fill, (48, 48))
    im = im.transform(im.size, Image.AFFINE, (1, -0.08, 0, 0, 1, 0), resample=Image.BICUBIC)   # slight forward lean
    return _save(im, path)
def badge(text, path, page="cards", size=66):
    """Fact badge: Anton caps on a gold slab, dark text, hard shadow, 3° tilt."""
    f = font("anton", size); x0, y0, x1, y1 = _tw(f, text); px, py = 30, 14
    w, h = x1 - x0 + px * 2, y1 - y0 + py * 2
    im = Image.new("RGBA", (w + 60, h + 60), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rectangle([30 + 8, 30 + 10, 30 + w + 8, 30 + h + 10], fill=(0, 0, 0, 140))            # hard shadow
    d.rectangle([30, 30, 30 + w, 30 + h], fill=PAGES[page]["accent"] + (255,))
    d.text((30 + px - x0, 30 + py - y0), text, font=f, fill=PAGES[page]["dark"] + (255,))
    im = im.rotate(-3, resample=Image.BICUBIC, expand=True)
    return _save(im, path)
def chip(text, path, page="cards", size=46):
    """Credit chip: Bebas Neue, white with outline, on a soft dark pill."""
    f = font("bebas", size); x0, y0, x1, y1 = _tw(f, text); px, py = 26, 10
    w, h = x1 - x0 + px * 2, y1 - y0 + py * 2 + 4
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], h // 2, fill=(0, 0, 0, 150))
    d.text((px - x0, py - y0), text, font=f, fill=(255, 255, 255, 255))
    return _save(im, path)
def captionbox(words, path, page="cards", keyword=None, size=110, maxw=980):
    """Caption: Bebas Neue caps, white, keyword in gold, thick dark outline + soft shadow, NO box (sits on the footage)."""
    txt = " ".join(words).upper(); f = font("bebas", size)
    x0, y0, x1, y1 = _tw(f, txt)
    if x1 - x0 > maxw: size = int(size * maxw / (x1 - x0)); f = font("bebas", size); x0, y0, x1, y1 = _tw(f, txt)
    w, h = x1 - x0 + 40, y1 - y0 + 40
    parts = txt.split(" "); acc = PAGES[page]["accent"]
    def draw(d, dx, dy, col, shadow):
        x = dx + 20 - x0
        for p in parts:
            c = col if shadow else ((acc + (255,)) if keyword and p.strip(".,!?") == keyword.strip().upper() else (255, 255, 255, 255))
            d.text((x, dy + 20 - y0), p, font=f, fill=c, stroke_width=(0 if shadow else 9), stroke_fill=(15, 15, 15, 255))
            x += _tw(f, p + " ")[2]
    return _save(_shadowed(w, h, draw, blur=12, off=(0, 8)), path)
def cta(keyword, path, page="cards", line="COMMENT", size=190):
    """CTA: 'COMMENT' small in Bebas, keyword huge in Anton gold with outline, a gold underline bar. No bubble."""
    fa, fb = font("anton", size), font("bebas", 70)
    kx0, ky0, kx1, ky1 = _tw(fa, keyword); lx0, ly0, lx1, ly1 = _tw(fb, line)
    w = max(kx1 - kx0, lx1 - lx0) + 60; h = (ly1 - ly0) + (ky1 - ky0) + 90
    acc = PAGES[page]["accent"]
    def draw(d, dx, dy, col, shadow):
        d.text((dx + (w - (lx1 - lx0)) // 2 - lx0, dy + 10 - ly0), line, font=fb, fill=col or (255, 255, 255, 255), stroke_width=(0 if shadow else 5), stroke_fill=(15, 15, 15, 255))
        ky = dy + (ly1 - ly0) + 40
        d.text((dx + (w - (kx1 - kx0)) // 2 - kx0, ky - ky0), keyword, font=fa, fill=col or (acc + (255,)), stroke_width=(0 if shadow else 12), stroke_fill=(15, 15, 15, 255))
        if not shadow: d.rectangle([dx + 20, ky + (ky1 - ky0) + 18, dx + w - 20, ky + (ky1 - ky0) + 30], fill=acc + (255,))
    return _save(_shadowed(w, h, draw, blur=16, off=(0, 12)), path)
def scrim(path, w=1080, h=520):
    """Bottom gradient scrim (transparent → 70% black) so captions read on any footage."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for y in range(h): d.line([(0, y), (w, y)], fill=(0, 0, 0, int(180 * (y / h) ** 1.6)))
    return _save(im, path)
if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/kit"; os.makedirs(out, exist_ok=True)
    r = {"number": number("/43", f"{out}/number.png"), "badge": badge("NUMBERED TO 43", f"{out}/badge.png"), "chip": chip("LIVE ON KICK  ·  @HONEYHOLECOLLECT", f"{out}/chip.png"),
         "cap": captionbox(["jade", "cargill", "49", "of"], f"{out}/cap.png", keyword="cargill"), "cta": cta("PULL", f"{out}/cta.png"), "scrim": scrim(f"{out}/scrim.png")}
    print(json.dumps(r))
