#!/usr/bin/env python3
"""Make one Instagram Story (1080x1920) from real clip footage.  v2 (Oct 25: "make the stories more interesting and unique")
Template mode (use this):
  story.py make <template> <clip.mp4> <out> --at S --title "CARD NAME" --handle "@breaker" --where "Name on Kick"
                [--seed N] [--theme 0-4] [--clip2 other.mp4 --at2 S --title2 "OTHER CARD"] [--question "..."] [--pool cards|tcg]
  --pool tcg  (page 2, the TCG page): wantsee / hottake / question draw from the TCG pools (WANT_OPTIONS_TCG, HOT_TAKES_TCG,
              QUESTIONS_TCG) instead of the sports-card ones. Default cards = today's lists; outputs without --pool are unchanged.
  templates (video -> .mp4, image -> .jpg):
    hit       video  the pull at full speed, themed title bar + breaker credit
    guess     video  pixelated freeze "guess the pull" + 3-2-1, then the reveal
    slowmo    video  the reveal in slow motion with the breaker's face cam ringed ("watch his face")
    rate      image  "rate this pull" with a 1-10 scale to reply with
    versus    image  two different pulls side by side, "which one are you keeping" (needs --clip2)
    spotlight image  the breaker's face cam big + handle ("the breaker who pulled it")
    potd      image  tilted framed still, "pull of the day" + date
    reel      image  "new reel up" teaser with a play badge (post only after that reel is live)
    question  image  a hobby question over a blurred collage, reply A or B (--question or one from the pool)
  v3 engagement templates (Josh, Oct 25 ~5 PM: "ask the people what they want to see, guess the value of cards"):
    wantsee   image  "what do you want to see next?" with four themed options, reply A-D (not about one reel; no --at needed)
    guessvalue image "guess what this sold for" over the card still with four price buckets, reply A-D; never shows a price
    reveal    image  the answer to guessvalue: "it sold for $X" (needs --price = a real sold comp; FACTORY passes it only with compUrl)
    keepsell  image  "keep it or sell it?" over the card, two buttons, reply A or B
    captionthis image the breaker's face cam big, "caption this reaction", reply with a line
    hottake   image  a hobby hot take from the pool (or --question "text"), AGREE / DISAGREE
  The clip is a finished vertical clip (1080x1920, PiP top-right at 580,150 460 wide). --at = reveal second.
  --seed picks the theme and the wording, so the same clip never gets two identical stories.
Old modes (kept for older docs): story.py video|image ... (see v1 usage in story.v1.py)
Text stays inside the story safe zone (Instagram UI ~0-250 px top, reply bar ~1660-1920 px).
Prints JSON {out, template, theme, seconds|null, sha256}."""
import json, os, random, subprocess, sys, hashlib, tempfile, datetime, shutil
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

FD = os.path.expanduser("~/byb/fonts")
HF = "/usr/share/fonts/truetype/higgsfield"
FONTS = {"anton": f"{FD}/Anton-Regular.ttf", "archivo": f"{FD}/ArchivoBlack-Regular.ttf",
         "bebas": f"{FD}/BebasNeue-Regular.ttf", "mont": f"{HF}/Montserrat-ExtraBold.ttf",
         "poppins": f"{FD}/Poppins-Bold.ttf", "metro": f"{HF}/Metropolis-ExtraBold.ttf"}
THEMES = [
    {"name": "gold",   "acc": (255, 212, 59),  "on": (12, 12, 12),   "head": "anton"},
    {"name": "red",    "acc": (255, 59, 59),   "on": (255, 255, 255), "head": "archivo"},
    {"name": "mint",   "acc": (59, 255, 176),  "on": (10, 20, 16),   "head": "bebas"},
    {"name": "white",  "acc": (255, 255, 255), "on": (10, 10, 10),   "head": "mont"},
    {"name": "violet", "acc": (155, 92, 255),  "on": (255, 255, 255), "head": "metro"},
]
WORDS = {
    "guess": ["GUESS THE PULL", "WHAT DID HE HIT?", "NAME THIS CARD", "GUESS BEFORE IT FLIPS"],
    "guess_sub": ["answer in 3 seconds", "don't skip", "most people get this wrong", "first guess counts"],
    "slowmo": ["WATCH HIS FACE", "THE SECOND HE SAW IT", "SLOW IT DOWN", "WAIT FOR THE REACTION"],
    "rate": ["RATE THIS PULL", "1 TO 10?", "HOW BIG IS THIS HIT?", "SCORE IT"],
    "rate_sub": ["reply with a number", "be honest", "reply 1-10"],
    "versus": ["WHICH ONE ARE YOU KEEPING?", "PICK ONE", "YOU CAN ONLY KEEP ONE"],
    "spotlight": ["THE BREAKER WHO PULLED IT", "GIVE HIM A FOLLOW", "MEET THE BREAKER"],
    "potd": ["PULL OF THE DAY", "HIT OF THE DAY", "TODAY'S BEST PULL"],
    "reel": ["NEW REEL UP", "JUST POSTED", "YOU MISSED THIS ONE"],
    "reel_sub": ["tap our profile to watch", "full clip on our page", "watch it on the page"],
    "wantsee": ["WHAT DO YOU WANT TO SEE NEXT?", "YOU PICK TOMORROW'S CLIPS", "WHAT SHOULD WE CLIP NEXT?"],
    "wantsee_sub": ["reply A, B, C or D", "vote with a letter", "most votes wins"],
    "guessvalue": ["GUESS WHAT THIS SOLD FOR", "HOW MUCH IS THIS WORTH?", "PRICE CHECK: YOUR GUESS?", "NAME THE PRICE"],
    "guessvalue_sub": ["reply A, B, C or D", "no googling", "closest guess wins bragging rights"],
    "reveal": ["IT SOLD FOR", "LAST SOLD PRICE", "THE ANSWER"],
    "keepsell": ["KEEP IT OR SELL IT?", "PC OR FLIP?", "WOULD YOU SELL THIS?"],
    "captionthis": ["CAPTION THIS REACTION", "WHAT IS HE THINKING?", "CAPTION THIS FACE"],
    "hottake": ["HOT TAKE", "AGREE OR DISAGREE?", "SETTLE THIS"],
}
WANT_OPTIONS = ["BIGGEST HITS OF THE WEEK", "BREAKER REACTIONS", "1/1 CHASES", "ROOKIE AUTOS", "FOOTBALL BREAKS", "BASEBALL BREAKS",
                "BASKETBALL BREAKS", "POKEMON RIPS", "VINTAGE CUT AUTOS", "CASE HITS", "WORST BEATS (SO CLOSE)", "BIG-NAME NUMBERED CARDS"]
VALUE_BUCKETS = [["UNDER $50", "$50-200", "$200-1,000", "$1,000+"], ["UNDER $100", "$100-500", "$500-2,000", "$2,000+"],
                 ["UNDER $25", "$25-100", "$100-500", "$500+"], ["UNDER $250", "$250-1,000", "$1,000-5,000", "$5,000+"]]
HOT_TAKES = ["Numbered parallels matter more than the player.", "A 1/1 of a nobody beats a base card of a star.", "Grading a card you will never sell is a waste of money.",
             "Breaks are the only fun way to open modern product.", "On-card autos only. Sticker autos don't count.", "Vintage cut autos are the best cards in the hobby.",
             "Pokemon is a better long-term hold than sports cards.", "Retail blasters are never worth it.", "Case hits should always be sold the same week.",
             "The hobby peaked in 2021 and it's still coming down."]
QUESTIONS = [("ONE AUTO /10", "TEN BASE ROOKIES"), ("RIP IT", "KEEP IT SEALED"), ("GRADE IT", "KEEP IT RAW"),
             ("CHROME", "PAPER"), ("FOOTBALL BREAKS", "BASEBALL BREAKS"), ("HOBBY BOX", "RETAIL BLASTER"),
             ("YOUR GUY'S /99", "A RANDOM 1/1"), ("PATCH AUTO", "ON-CARD AUTO"), ("ROOKIE CARD", "VETERAN 1/1"),
             ("POKEMON", "SPORTS"), ("PC IT FOREVER", "FLIP IT"), ("LIVE BREAKS", "OPENING AT HOME")]
# --pool tcg (page 2): generic hobby wording only; game names as plain words, never character or mascot names.
WANT_OPTIONS_TCG = ["GOD PACKS", "ALT ART HITS", "BOOSTER BOX RIPS", "ONE PIECE PULLS", "LORCANA PULLS", "VINTAGE PACK OPENINGS",
                    "WORST PULLS (SO CLOSE)", "SIR CHASES", "ETB OPENINGS", "YUGIOH RIPS", "GRADED REVEALS", "BIGGEST HITS OF THE WEEK"]
HOT_TAKES_TCG = ["Alt arts carry the whole set. Everything else is filler.", "Grading only makes sense for a card you plan to sell.",
                 "Sealed product is a better hold than any single raw card.", "Ripping a vintage pack is never worth it. Keep it sealed.",
                 "Reprints don't hurt the hobby. They bring new collectors in.", "Retail is for fun, hobby boxes are for hits. Don't mix them up.",
                 "Full arts beat gold cards every single time.", "Pull rates don't matter if the chase card is good enough.",
                 "Opening on stream beats opening alone. The hits feel bigger.", "One Piece has the best looking cards in the hobby right now."]
QUESTIONS_TCG = [("RIP IT", "KEEP IT SEALED"), ("ALT ART", "GOLD CARD"), ("BOOSTER BOX", "ETB"), ("GRADE IT", "KEEP IT RAW"),
                 ("VINTAGE", "MODERN"), ("ONE PIECE", "POKEMON"), ("LORCANA", "MAGIC"), ("YUGIOH", "POKEMON"),
                 ("SINGLE PACKS", "A WHOLE CASE"), ("PC IT FOREVER", "FLIP IT"), ("ONE SIR", "TEN FULL ARTS"), ("JAPANESE PACKS", "ENGLISH PACKS")]
POOLS = {"cards": {"want": WANT_OPTIONS, "takes": HOT_TAKES, "questions": QUESTIONS},
         "tcg": {"want": WANT_OPTIONS_TCG, "takes": HOT_TAKES_TCG, "questions": QUESTIONS_TCG}}
POOL = POOLS["cards"]          # set from --pool in main()

def opt(n, d=""):
    return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d

def ff(*a):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *a], check=True)

def dur(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p]).decode().strip())

def font(name, size):
    return ImageFont.truetype(FONTS[name], size)

def grab(clip, at, path):
    ff("-ss", f"{max(at, 0):.2f}", "-i", clip, "-frames:v", "1", path)
    return Image.open(path).convert("RGB").resize((1080, 1920))

def fit(draw, text, fname, maxw, maxsize, minsize=40):
    s = maxsize
    while s > minsize:
        f = font(fname, s)
        if draw.textlength(text, font=f) <= maxw:
            return f
        s -= 4
    return font(fname, minsize)

def wrap(draw, text, fname, size, maxw):
    f = font(fname, size); words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=f) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    lines.append(cur)
    return f, lines

def bar(img, y, text, th, size=96, pad=26, tilt=0):
    """Accent block with headline text, centred; optional small tilt."""
    layer = Image.new("RGBA", (1080, 400), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    f = fit(d, text, th["head"], 930, size)
    w = d.textlength(text, font=f); bb = d.textbbox((0, 0), text, font=f)
    h = bb[3] - bb[1]
    x0 = (1080 - w) / 2 - pad
    d.rounded_rectangle([x0, 200 - h / 2 - pad, x0 + w + 2 * pad, 200 + h / 2 + pad], radius=18, fill=th["acc"] + (255,))
    d.text((x0 + pad, 200 - h / 2 - bb[1]), text, font=f, fill=th["on"])
    if tilt:
        layer = layer.rotate(tilt, resample=Image.BICUBIC)
    img.alpha_composite(layer, (0, int(y - 200)))

def label(img, y, text, size=40, fg=(255, 255, 255), bg=(0, 0, 0, 160), fname="poppins", x=None):
    d = ImageDraw.Draw(img); f = font(fname, size)
    w = d.textlength(text, font=f); bb = d.textbbox((0, 0), text, font=f); h = bb[3] - bb[1]
    x0 = (1080 - w) / 2 - 22 if x is None else x
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); dl = ImageDraw.Draw(layer)
    dl.rounded_rectangle([x0, y, x0 + w + 44, y + h + 30], radius=(h + 30) // 2, fill=bg)
    dl.text((x0 + 22, y + 15 - bb[1]), text, font=f, fill=fg)
    img.alpha_composite(layer)

def credit(img, handle, where, y=1560):
    t = f"{handle} · {where}" if handle and where else (handle or where)
    if t:
        label(img, y, t, size=34)

def blurbg(fr, dark=0.45):
    b = fr.filter(ImageFilter.GaussianBlur(28))
    return Image.blend(b, Image.new("RGB", b.size, (0, 0, 0)), dark).convert("RGBA")

def save_png(img, path):
    img.save(path)
    return path

def video_with_overlays(clip, start, ln, out, overlays, speed=1.0, pre=None):
    """overlays: list of (png, t0, t1). pre: optional (png_still, seconds) prepended (silent)."""
    with tempfile.TemporaryDirectory() as t:
        main = os.path.join(t, "m.mp4")
        ins = ["-ss", f"{max(start, 0):.2f}", "-t", f"{ln:.2f}", "-i", clip]
        fc = "[0:v]scale=1080:1920,setsar=1,fps=30"
        if speed != 1.0:
            fc += f",setpts=PTS/{speed}"
        fc += "[v0]"; last = "v0"
        for i, (png, t0, t1) in enumerate(overlays):
            ins += ["-i", png]
            fc += f";[{last}][{i + 1}:v]overlay=0:0:enable='between(t,{t0},{t1})'[v{i + 1}]"; last = f"v{i + 1}"
        af = "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000"
        if speed != 1.0:
            af = f"atempo={speed}," + af
        fc += f";[0:a]{af}[a]"
        ff(*ins, "-filter_complex", fc, "-map", f"[{last}]", "-map", "[a]", "-ac", "2", "-ar", "48000",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", main)
        if not pre:
            shutil.move(main, out); return
        still, secs, layers = pre
        a = os.path.join(t, "a.mp4")
        ins = ["-loop", "1", "-t", f"{secs:.2f}", "-i", still, "-f", "lavfi", "-t", f"{secs:.2f}", "-i", "anullsrc=r=48000:cl=stereo"]
        fc = "[0:v]scale=1080:1920,setsar=1,fps=30,format=yuv420p[p0]"; last = "p0"
        for i, (png, t0, t1) in enumerate(layers):
            ins += ["-loop", "1", "-t", f"{secs:.2f}", "-i", png]
            fc += f";[{last}][{i + 2}:v]overlay=0:0:enable='between(t,{t0},{t1})'[p{i + 1}]"; last = f"p{i + 1}"
        ff(*ins, "-filter_complex", fc, "-map", f"[{last}]", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", a)
        ff("-i", a, "-i", main, "-filter_complex", "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]", "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", out)

def blank():
    return Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))

def options_card(img, th, header, opts, y0=560, h=None, letters="ABCD", reply="reply A, B, C or D"):
    """A white rounded card with a header and 2-4 lettered option buttons (the question template's look)."""
    n = len(opts); rowh = 120 if n > 2 else 170; gap = 20
    h = h or (120 + n * (rowh + gap) + 70)                    # header + rows + the reply line inside the card
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([70, y0, 1010, y0 + h], radius=40, fill=(255, 255, 255, 240))
    dark = (18, 18, 18, 255)
    fq = font("archivo", 50); w = d.textlength(header, font=fq); d.text((540 - w / 2, y0 + 40), header, font=fq, fill=(20, 20, 20))
    for k, txt in enumerate(opts):
        yy = y0 + 120 + k * (rowh + gap)
        d.rounded_rectangle([120, yy, 960, yy + rowh], radius=28, fill=th["acc"] + (255,), outline=dark, width=4)
        r = min(rowh // 2 - 18, 50); cx, cy = 180, yy + rowh // 2
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0, 0, 0))
        ft = font("archivo", int(r * 1.1)); tag = letters[k]; wt = d.textlength(tag, font=ft); bb = d.textbbox((0, 0), tag, font=ft)
        d.text((cx - wt / 2, cy - (bb[3] - bb[1]) / 2 - bb[1]), tag, font=ft, fill=th["acc"])
        fnt, lines = wrap(d, txt, th["head"], 54 if n > 2 else 64, 660)
        lh = 58 if n > 2 else 72
        for i2, ln in enumerate(lines[:2]):
            d.text((262, cy - len(lines[:2]) * lh / 2 + i2 * lh + 4), ln, font=fnt, fill=th["on"])
    label(img, y0 + h - 78, reply, size=38, fg=(255, 255, 255), bg=(18, 18, 18, 230))
    return y0 + h

def make(tpl, clip, out, at, title, handle, where, rnd, th, t):
    pick = lambda k: rnd.choice(WORDS[k])
    if tpl == "hit":
        o = blank(); bar(o, 330, title, th, tilt=rnd.choice([0, 0, -2, 2])); credit(o, handle, where)
        video_with_overlays(clip, at - 2.2, 7.5, out, [(save_png(o, f"{t}/o.png"), 0, 99)]); return
    if tpl == "slowmo":
        o = blank(); bar(o, 470, pick("slowmo"), th)
        d = ImageDraw.Draw(o)
        d.rounded_rectangle([566, 136, 1054, 400], radius=22, outline=th["acc"] + (255,), width=10)
        # no separate SLOW-MO pill: it collided with the clip's burned captions (y ~1420-1500) and, moved up, with the
        # card. The slow-motion tag rides on the credit line instead (Fable, Oct 25 review).
        credit(o, handle, (where + " · slow-mo") if where else "slow-mo")
        video_with_overlays(clip, at - 1.0, 3.0, out, [(save_png(o, f"{t}/o.png"), 0, 99)], speed=0.6); return
    if tpl == "guess":
        fr = grab(clip, at + 0.6, f"{t}/f.png")
        px = fr.resize((27, 48), Image.BILINEAR).resize((1080, 1920), Image.NEAREST)
        px = Image.blend(px, Image.new("RGB", px.size, (0, 0, 0)), 0.25); px.save(f"{t}/px.png")
        o = blank(); bar(o, 420, pick("guess"), th); label(o, 560, pick("guess_sub"), size=40); credit(o, handle, where)
        layers = [(save_png(o, f"{t}/g.png"), 0, 9)]
        for i, n in enumerate(["3", "2", "1"]):
            c = blank(); d = ImageDraw.Draw(c); f = font(th["head"], 420)
            bb = d.textbbox((0, 0), n, font=f)
            d.ellipse([290, 760, 790, 1260], fill=(0, 0, 0, 150), outline=th["acc"] + (255,), width=14)
            d.text((540 - (bb[2] - bb[0]) / 2 - bb[0], 1010 - (bb[3] - bb[1]) / 2 - bb[1]), n, font=f, fill=th["acc"])
            layers.append((save_png(c, f"{t}/n{i}.png"), round(i * 0.8, 2), round(i * 0.8 + 0.8, 2)))
        r = blank(); bar(r, 330, title, th); credit(r, handle, where)
        video_with_overlays(clip, at - 0.5, 4.8, out, [(save_png(r, f"{t}/r.png"), 0.4, 99)], pre=(f"{t}/px.png", 2.4, layers)); return
    fr = grab(clip, at + 0.6, f"{t}/f.png")
    if tpl == "rate":
        img = fr.convert("RGBA"); grad = Image.new("L", (1, 1920))
        for y in range(1920):
            grad.putpixel((0, y), int(max(0, (y - 900) / 1020) * 210))
        img.alpha_composite(Image.merge("RGBA", [Image.new("L", (1080, 1920), 0)] * 3 + [grad.resize((1080, 1920))]))
        bar(img, 330, pick("rate"), th, tilt=rnd.choice([0, -2]))
        d = ImageDraw.Draw(img); f = font("archivo", 46)
        for i in range(10):
            x = 60 + i * 99; c = (int(255 - i * 22), int(60 + i * 19), 70)
            d.ellipse([x, 1300, x + 84, 1384], fill=c + (255,), outline=(255, 255, 255, 255), width=4)
            s = str(i + 1); w = d.textlength(s, font=f); d.text((x + 42 - w / 2, 1312), s, font=f, fill=(255, 255, 255))
        label(img, 1410, pick("rate_sub"), size=40); label(img, 1200, title, size=44, fname="mont"); credit(img, handle, where)
    elif tpl == "versus":
        c2, at2, t2 = opt("--clip2"), float(opt("--at2", "0")), opt("--title2", "")
        if not c2:
            raise SystemExit(json.dumps({"error": "versus needs --clip2"}))
        f2 = grab(c2, at2 + 0.6, f"{t}/f2.png")
        img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 255))
        img.paste(fr.crop((270, 0, 810, 1920)), (0, 0)); img.paste(f2.crop((270, 0, 810, 1920)), (540, 0))
        d = ImageDraw.Draw(img); d.rectangle([536, 0, 544, 1920], fill=th["acc"])
        d.ellipse([440, 880, 640, 1080], fill=th["acc"], outline=(0, 0, 0), width=8)
        fv = font("archivo", 84); w = d.textlength("VS", font=fv); d.text((540 - w / 2, 925), "VS", font=fv, fill=th["on"])
        bar(img, 330, pick("versus"), th, size=80)
        for x, txt in ((30, "LEFT"), (580, "RIGHT")):
            label(img, 1330, txt, size=44, fg=th["on"], bg=th["acc"] + (240,), fname="archivo", x=x + 120 if txt == "LEFT" else x + 110)
        dd = ImageDraw.Draw(img)
        for x0, txt in ((0, title), (540, t2)):
            fnt, lines = wrap(dd, txt, "mont", 40, 480)
            for k, ln in enumerate(lines[:3]):
                w = dd.textlength(ln, font=fnt)
                dd.text((x0 + 270 - w / 2, 1430 + k * 50), ln, font=fnt, fill=(255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0))
        label(img, 1590, "reply L or R", size=38)
    elif tpl == "spotlight":
        img = blurbg(fr); pip = fr.crop((580, 150, 1040, 382)).resize((1000, 504), Image.LANCZOS)
        pip = ImageOps.expand(pip, border=10, fill=th["acc"]); img.paste(pip, (30, 640))
        bar(img, 420, pick("spotlight"), th, size=78)
        d = ImageDraw.Draw(img); fh = fit(d, handle or where, "archivo", 980, 92)
        w = d.textlength(handle or where, font=fh); d.text((540 - w / 2, 1200), handle or where, font=fh, fill=(255, 255, 255))
        label(img, 1330, where if handle else "", size=40) if handle and where else None
        label(img, 1430, f"pulled: {title.lower()}", size=36, fname="mont")
    elif tpl in ("potd", "reel"):
        img = blurbg(fr, 0.5); card = fr.resize((700, 1244), Image.LANCZOS)
        card = ImageOps.expand(card, border=16, fill=(255, 255, 255)).convert("RGBA")
        ang = rnd.choice([-4, -3, 3, 4]); card = card.rotate(ang, resample=Image.BICUBIC, expand=True)
        sh = Image.new("RGBA", card.size, (0, 0, 0, 0)); sh.paste((0, 0, 0, 150), mask=card.split()[3])
        sh = sh.filter(ImageFilter.GaussianBlur(22))
        x, y = (1080 - card.width) // 2, 400
        img.alpha_composite(sh, (x + 18, y + 26)); img.alpha_composite(card, (x, y))
        if tpl == "potd":
            day = datetime.date.today().strftime("%b %d").upper()
            bar(img, 300, f"{pick('potd')} · {day}", th, size=78)
            label(img, 1500, title, size=46, fg=th["on"], bg=th["acc"] + (245,), fname="mont")
        else:
            bar(img, 300, pick("reel"), th, size=90)
            d = ImageDraw.Draw(img); d.ellipse([400, 880, 680, 1160], fill=(0, 0, 0, 170), outline=(255, 255, 255), width=10)
            d.polygon([(500, 950), (500, 1090), (620, 1020)], fill=(255, 255, 255))
            label(img, 1500, pick("reel_sub"), size=42)
        credit(img, handle, where, y=1590)
    elif tpl == "question":
        qa = opt("--question")
        a, b = qa.split("|", 1) if "|" in qa else rnd.choice(POOL["questions"])
        img = blurbg(fr, 0.55); d = ImageDraw.Draw(img)
        d.rounded_rectangle([70, 560, 1010, 1380], radius=40, fill=(255, 255, 255, 240))
        fq = font("archivo", 54); hdr = "WHICH ONE?"
        w = d.textlength(hdr, font=fq); d.text((540 - w / 2, 610), hdr, font=fq, fill=(20, 20, 20))
        for k, (tag, txt) in enumerate((("A", a), ("B", b))):
            y0 = 740 + k * 300
            d.rounded_rectangle([120, y0, 960, y0 + 240], radius=30, fill=th["acc"] + (255,))
            d.ellipse([150, y0 + 60, 270, y0 + 180], fill=(0, 0, 0))
            ft = font("archivo", 70); wt = d.textlength(tag, font=ft); d.text((210 - wt / 2, y0 + 72), tag, font=ft, fill=th["acc"])
            fnt, lines = wrap(d, txt, th["head"], 70, 640)
            for i2, ln in enumerate(lines[:2]):
                d.text((300, y0 + 120 - len(lines[:2]) * 40 + i2 * 80), ln, font=fnt, fill=th["on"])
        bar(img, 360, "SETTLE THIS", th, size=96, tilt=rnd.choice([-2, 2]))
        label(img, 1440, "reply A or B", size=42); credit(img, handle, where, y=1560)
    elif tpl == "wantsee":
        img = blurbg(fr, 0.55); opts = rnd.sample(POOL["want"], 4)
        bar(img, 330, pick("wantsee"), th, size=80, tilt=rnd.choice([-2, 0, 2]))
        yend = options_card(img, th, "PICK ONE", opts, y0=470, reply=pick("wantsee_sub"))
        credit(img, handle, where, y=1560)
    elif tpl == "guessvalue":
        img = fr.convert("RGBA"); grad = Image.new("L", (1, 1920))
        for y in range(1920):
            grad.putpixel((0, y), int(max(0, (y - 700) / 1220) * 230))
        img.alpha_composite(Image.merge("RGBA", [Image.new("L", (1080, 1920), 0)] * 3 + [grad.resize((1080, 1920))]))
        bar(img, 330, pick("guessvalue"), th, size=78, tilt=rnd.choice([-2, 0]))
        label(img, 470, title, size=44, fname="mont")
        options_card(img, th, "YOUR GUESS", rnd.choice(VALUE_BUCKETS), y0=800, reply=pick("guessvalue_sub"))
        credit(img, handle, where, y=1612)
    elif tpl == "reveal":
        price = opt("--price")
        if not price:
            raise SystemExit(json.dumps({"error": "reveal needs --price (a real sold comp)"}))
        img = blurbg(fr, 0.5); card = fr.resize((560, 995), Image.LANCZOS)
        card = ImageOps.expand(card, border=14, fill=(255, 255, 255)).convert("RGBA").rotate(rnd.choice([-3, 3]), resample=Image.BICUBIC, expand=True)
        img.alpha_composite(card, ((1080 - card.width) // 2, 300))
        bar(img, 300, pick("reveal"), th, size=84)
        d = ImageDraw.Draw(img); fp = font("anton", 190); w = d.textlength(price, font=fp)
        d.rounded_rectangle([540 - w / 2 - 50, 1330, 540 + w / 2 + 50, 1560], radius=40, fill=(10, 10, 10, 225))
        d.text((540 - w / 2, 1340), price, font=fp, fill=th["acc"], stroke_width=8, stroke_fill=(10, 10, 10))
        label(img, 1580, "last sold comp · " + title.lower(), size=34, fname="mont"); credit(img, handle, where, y=1640)
    elif tpl == "keepsell":
        img = fr.convert("RGBA"); grad = Image.new("L", (1, 1920))
        for y in range(1920):
            grad.putpixel((0, y), int(max(0, (y - 900) / 1020) * 220))
        img.alpha_composite(Image.merge("RGBA", [Image.new("L", (1080, 1920), 0)] * 3 + [grad.resize((1080, 1920))]))
        bar(img, 330, pick("keepsell"), th, size=80, tilt=rnd.choice([-2, 2]))
        label(img, 470, title, size=44, fname="mont")
        options_card(img, th, "YOU PULLED THIS", ["KEEP IT (PC FOREVER)", "SELL IT TODAY"], y0=960, letters="AB", reply="reply A or B")
        credit(img, handle, where, y=1612)
    elif tpl == "captionthis":
        img = blurbg(fr, 0.5); pip = fr.crop((580, 150, 1040, 382)).resize((1000, 504), Image.LANCZOS)
        pip = ImageOps.expand(pip, border=12, fill=th["acc"]); img.paste(pip, (28, 600))
        bar(img, 420, pick("captionthis"), th, size=80, tilt=rnd.choice([-2, 0, 2]))
        label(img, 1180, "reply with your best line", size=42); label(img, 1290, "the moment: " + title.lower(), size=36, fname="mont")
        credit(img, handle, where, y=1560)
    elif tpl == "hottake":
        qa = opt("--question"); take = qa if qa else rnd.choice(POOL["takes"])
        img = blurbg(fr, 0.6); d = ImageDraw.Draw(img)
        d.rounded_rectangle([70, 470, 1010, 890], radius=40, fill=(255, 255, 255, 240))
        fnt, lines = wrap(d, take, "archivo", 54, 820)
        for k, ln in enumerate(lines[:4]):
            w = d.textlength(ln, font=fnt); d.text((540 - w / 2, 530 + k * 74), ln, font=fnt, fill=(20, 20, 20))
        bar(img, 360, pick("hottake"), th, size=92, tilt=rnd.choice([-2, 2]))
        options_card(img, th, "YOUR CALL", ["AGREE", "DISAGREE"], y0=930, letters="AB", reply="reply A or B")
        credit(img, handle, where, y=1612)
    else:
        raise SystemExit(json.dumps({"error": f"unknown template {tpl}"}))
    img.convert("RGB").save(out, quality=92)

def main():
    if sys.argv[1] in ("video", "image"):   # v1 compatibility
        v1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "story.v1.py")
        os.execvp(sys.executable, [sys.executable, v1] + sys.argv[1:])
    tpl, clip, out = sys.argv[2], sys.argv[3], sys.argv[4]
    global POOL
    pname = opt("--pool", "cards").lower()
    if pname not in POOLS:
        raise SystemExit(json.dumps({"error": f"unknown --pool {pname}; use one of {sorted(POOLS)}"}))
    POOL = POOLS[pname]
    seed = int(opt("--seed", str(random.randrange(10 ** 6))))
    rnd = random.Random(seed)
    th = THEMES[int(opt("--theme"))] if opt("--theme") else rnd.choice(THEMES)
    at, title = float(opt("--at", "0")), opt("--title")
    with tempfile.TemporaryDirectory() as t:
        make(tpl, clip, out, at, title, opt("--handle"), opt("--where"), rnd, th, t)
    vid = out.endswith(".mp4")
    print(json.dumps({"out": out, "template": tpl, "theme": th["name"], "seed": seed, "pool": pname,
                      "seconds": round(dur(out), 2) if vid else None,
                      "sha256": hashlib.sha256(open(out, "rb").read()).hexdigest()[:16]}))

if __name__ == "__main__":
    main()
