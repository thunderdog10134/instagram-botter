#!/usr/bin/env python3
"""Burn word-by-word captions. Usage: captions.py <in.mp4> <out.mp4> [--style opus|karaoke|minimal] [--font "Poppins Bold"] [--model tiny.en] [--margin 420] [--prompt "names, set names"] [--words corrected.json]
Writes <out>.words.json (whisper-format: segments[].words[]{start,end,word}) next to the output; prints JSON summary."""
import json, os, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import now_iso, log

VENDOR = os.path.expanduser("~/autopilot/vendor/clipify/scripts/build_ass.py")
FONTS = os.path.expanduser("~/byb/fonts")

def opt(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default

def words_json(audio, model_name, prompt=None):
    from faster_whisper import WhisperModel
    m = WhisperModel(model_name, device="cpu", compute_type="int8")
    segs, _ = m.transcribe(audio, word_timestamps=True, vad_filter=True, initial_prompt=prompt or None)
    out = {"segments": []}
    for s in segs:
        out["segments"].append({"start": s.start, "end": s.end, "text": s.text,
                                "words": [{"start": w.start, "end": w.end, "word": w.word} for w in (s.words or [])]})
    return out

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "usage"})); return
    src, dst = sys.argv[1], sys.argv[2]
    style, font, model = opt("--style", "opus"), opt("--font", "Poppins Bold"), opt("--model", "tiny.en")
    margin = int(opt("--margin", "420"))
    prompt, words_in = opt("--prompt", None), opt("--words", None)   # --prompt: vocabulary hint (names, set names); --words: reuse/corrected words json
    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "a.wav")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000", wav], check=True)
        wj = json.load(open(words_in)) if words_in else words_json(wav, model, prompt)
        wpath = dst + ".words.json"
        json.dump(wj, open(wpath, "w"))
        n = sum(len(s["words"]) for s in wj["segments"])
        if n == 0:
            subprocess.run(["cp", src, dst], check=True)
            print(json.dumps({"at": now_iso(), "out": dst, "words": 0, "note": "no speech, copied"})); return
        ass = os.path.join(tmp, "c.ass")
        subprocess.run([sys.executable, VENDOR, wpath, ass, style], check=True, capture_output=True)
        txt = open(ass).read()
        txt = txt.replace("Arial Black", font).replace("Helvetica", font)
        # bottom margin keeps captions clear of the hook (top) and payoff (upper-middle) stickers
        lines = []
        for ln in txt.splitlines():
            if ln.startswith("Style:"):
                parts = ln.split(",")
                if len(parts) >= 23:
                    parts[18] = "2"          # alignment: bottom centre
                    parts[21] = str(margin)  # MarginV
                ln = ",".join(parts)
            lines.append(ln)
        open(ass, "w").write("\n".join(lines) + "\n")
        vf = f"subtitles={ass}:fontsdir={FONTS}"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "12", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", dst], check=True)
    log("captions", {"src": os.path.basename(src), "words": n})
    print(json.dumps({"at": now_iso(), "out": dst, "words": n, "wordsJson": wpath, "seconds": round(time.time() - t0, 1)}))

if __name__ == "__main__":
    main()
