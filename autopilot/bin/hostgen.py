#!/usr/bin/env python3
"""AI-host line generation through Muapi.ai (Kling 3.0 image-to-video from an approved portrait).

Usage:
  hostgen.py muapi line <portrait_url> "<line text>" <out.mp4> [--prompt-file f] [--model <slug>]
             [--duration 5] [--poll 10] [--max-usd 0.40] [--max-usd-day 2.00] [--no-audio] [--dry-run]
  hostgen.py muapi balance

Muapi facts (checked Oct 25, 2026 against https://muapi.ai/docs/api-reference, https://api.muapi.ai/openapi.json
and Open-Higgsfield-AI packages/studio/src/muapi.js):
  - base https://api.muapi.ai/api/v1, header x-api-key, submit-then-poll
  - POST /api/v1/kling-v3.0-standard-image-to-video  body {prompt, image_url, duration 3..15, generate_audio, last_image?}
    (no aspect_ratio field: Kling keeps the portrait's aspect; use a 9:16 portrait)
    -> {"request_id": "...", "status": "processing", "cost": {"amount_usd": ...}}
  - GET  /api/v1/predictions/{request_id}/result -> {"id", "status": queued|pending|processing|completed|failed|cancelled,
    "outputs": ["https://cdn.muapi.ai/...mp4"], "cost": {...}}
  - POST /api/v1/models/{slug}/estimate-cost (no key needed) -> {"cost": 0.6, "currency": "USD"}  (the billed price)
  - GET  /api/v1/account/balance (key)
  - errors: 401/403 {"detail": "...", "error": {"code": "FORBIDDEN", "message": "..."}}; 422 {"detail": [{loc, msg, type}]}
Rules: the key is never printed; every path exits 0 and reports errors in JSON; every real call is written to
~/autopilot/state/muapi-spend.json and the daily / per-job USD caps are enforced before a job is submitted.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from common import now_iso, log
except Exception:  # standalone fallback
    def now_iso():
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def log(task, event):
        pass

HOME = os.path.expanduser("~")
KEY_PATH = os.path.join(HOME, "secrets", "muapi.json")
LEDGER = os.path.join(HOME, "autopilot", "state", "muapi-spend.json")
BASE = "https://api.muapi.ai/api/v1"
DEFAULT_MODEL = "kling-v3.0-standard-image-to-video"
MAX_WAIT_S = 15 * 60
WHISPER_MODEL = "small.en"
FRAME_TIMES = (0.3, 2.0, 3.5)
MATCH_MIN = 0.8

# USD per second, (with audio, without audio). From /models/{slug}/estimate-cost on Oct 25, 2026:
# standard 5s+audio 0.60, 5s no audio 0.40, 3s 0.36/0.24, 10s 1.20/0.80; pro 5s+audio 0.80; turbo-standard 5s+audio 0.56.
PRICE_PER_S = {
    "kling-v3.0-standard-image-to-video": (0.12, 0.08),
    "kling-v3.0-pro-image-to-video": (0.16, None),
    "kling-v3-turbo-standard-image-to-video": (0.112, None),
}

PROMPT_TEMPLATE = (
    "Handheld selfie video on a phone, slight natural drift, we join him mid-sentence. The same guy in the dark grey "
    "t-shirt in his card room late at night, warm and relaxed, like he's showing a close friend something on his phone. "
    "He leans in a little, lets out a short quiet laugh, and says in a warm, natural, unhurried voice with a small pause "
    "before the last word: \"<line>\". Easy half-grin that fades, slow blink, no pointing, no eyebrow raise, no big smile, "
    "hands out of frame. Warm lamp light, no harsh shadows. Accurate lip sync, quiet room tone, no music, no captions, "
    "no text on screen."
)


def opt(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def emit(obj):
    print(json.dumps(obj, indent=1))


def load_key():
    """Returns the api key string or None. Never prompts, never invents."""
    try:
        with open(KEY_PATH) as f:
            k = json.load(f).get("api_key")
        return k if isinstance(k, str) and k.strip() else None
    except Exception:
        return None


def mask(key):
    if not key:
        return "<missing: ~/secrets/muapi.json>"
    return key[:4] + "…" + "*" * 8


def http(method, path, key=None, body=None, timeout=60):
    """Returns (status, json_or_dict). Network errors -> (0, {...})."""
    url = path if path.startswith("http") else BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "clip-autopilot-hostgen/1.0")
    if key:
        req.add_header("x-api-key", key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode(errors="ignore")
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, {"raw": raw[:500]}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="ignore")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:500]}
    except Exception as e:
        return 0, {"error": {"code": "NET", "message": str(e)[:300]}}


def err_text(status, js):
    """Flatten Muapi error shapes: {"error":{"code","message"}} / {"detail": str|[{loc,msg}]} / {"raw"}."""
    if not isinstance(js, dict):
        return f"http {status}: {str(js)[:200]}"
    e = js.get("error")
    if isinstance(e, dict) and e.get("message"):
        return f"http {status} {e.get('code', '')}: {e['message']}"[:300]
    d = js.get("detail")
    if isinstance(d, list):
        return f"http {status} validation: " + "; ".join(
            f"{'.'.join(str(x) for x in (i.get('loc') or []))}: {i.get('msg')}" for i in d if isinstance(i, dict))[:300]
    if d:
        return f"http {status}: {str(d)[:250]}"
    return f"http {status}: {str(js.get('message') or js.get('raw') or js)[:250]}"


def estimate_local(model, duration, audio):
    rates = PRICE_PER_S.get(model)
    if not rates:
        return None
    r = rates[0] if audio else rates[1]
    return round(r * duration, 4) if r is not None else None


def estimate_remote(model, body):
    status, js = http("POST", f"/models/{model}/estimate-cost", body={k: v for k, v in body.items()
                                                                        if k in ("duration", "generate_audio")})
    if status == 200 and isinstance(js, dict) and isinstance(js.get("cost"), (int, float)):
        return float(js["cost"]), None
    return None, err_text(status, js)


# ---------- ledger ----------
def ledger_read():
    try:
        with open(LEDGER) as f:
            v = json.load(f)
        return v if isinstance(v, list) else []
    except Exception:
        return []


def ledger_write(rows):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    tmp = LEDGER + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rows, f, indent=1)
    os.replace(tmp, LEDGER)


def ledger_today_total(rows):
    today = time.strftime("%Y-%m-%d", time.gmtime())
    return round(sum(float(r.get("priceUsd") or 0) for r in rows if str(r.get("at", "")).startswith(today)), 4)


def ledger_append(row):
    rows = ledger_read()
    rows.append(row)
    ledger_write(rows)


def ledger_update(request_id, **fields):
    rows = ledger_read()
    for r in reversed(rows):
        if r.get("requestId") == request_id:
            r.update(fields)
            break
    ledger_write(rows)


# ---------- prompt ----------
def build_prompt(line, prompt_file):
    if prompt_file:
        with open(prompt_file) as f:
            tpl = f.read().strip()
    else:
        tpl = PROMPT_TEMPLATE
    return tpl.replace("<line>", line) if "<line>" in tpl else tpl


# ---------- verify ----------
def norm_words(s):
    return re.sub(r"[^a-z0-9' ]+", " ", s.lower().replace("’", "'")).split()


def word_match(line, transcript):
    want = norm_words(line)
    if not want:
        return 0.0
    have = {}
    for w in norm_words(transcript):
        have[w] = have.get(w, 0) + 1
    hit = 0
    for w in want:
        if have.get(w, 0) > 0:
            have[w] -= 1
            hit += 1
    return round(hit / len(want), 3)


def media_seconds(path):
    try:
        out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                       "-of", "csv=p=0", path], timeout=60).decode().strip()
        return round(float(out), 2)
    except Exception:
        return 0.0


def transcribe(path, line):
    pylib = "/home/user/pylib"
    if os.path.isdir(pylib) and pylib not in sys.path:
        sys.path.insert(0, pylib)
    wav = path + ".verify.wav"
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000", wav],
                       check=True, timeout=120)
        from faster_whisper import WhisperModel
        m = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        segs, _ = m.transcribe(wav, vad_filter=True, initial_prompt=line)
        return " ".join(s.text.strip() for s in segs).strip(), None
    except Exception as e:
        return "", f"transcribe: {str(e)[:200]}"
    finally:
        try:
            os.remove(wav)
        except Exception:
            pass


def extract_frames(path):
    base = os.path.splitext(path)[0]
    frames = []
    for i, t in enumerate(FRAME_TIMES, 1):
        fp = f"{base}.f{i}.jpg"
        try:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1",
                            "-q:v", "3", fp], check=True, timeout=60)
            if os.path.exists(fp):
                frames.append(fp)
        except Exception:
            pass
    return frames


def verify(path, line):
    transcript, terr = transcribe(path, line)
    match = word_match(line, transcript) if transcript else 0.0
    return {"transcript": transcript, "match": match, "frames": extract_frames(path),
            "verifyError": terr}


# ---------- commands ----------
def cmd_line():
    if len(sys.argv) < 6:
        emit({"error": "usage: hostgen.py muapi line <portrait_url> \"<line>\" <out.mp4> [--dry-run ...]"})
        return
    portrait, line, out = sys.argv[3], sys.argv[4], sys.argv[5]
    model = opt("--model", DEFAULT_MODEL)
    duration = int(opt("--duration", "5"))
    poll_s = max(2, int(opt("--poll", "10")))
    max_usd = float(opt("--max-usd", "0.40"))
    max_day = float(opt("--max-usd-day", "2.00"))
    audio = "--no-audio" not in sys.argv
    dry = "--dry-run" in sys.argv
    try:
        prompt = build_prompt(line, opt("--prompt-file"))
    except Exception as e:
        emit({"error": f"prompt-file: {str(e)[:200]}"})
        return
    if not (3 <= duration <= 15):
        emit({"error": "duration must be 3..15 (Kling 3.0 schema)"})
        return
    body = {"prompt": prompt, "image_url": portrait, "duration": duration, "generate_audio": audio}
    url = f"{BASE}/{model}"
    key = load_key()
    est = estimate_local(model, duration, audio)

    if dry:
        emit({"dryRun": True, "request": {"method": "POST", "url": url,
                                           "headers": {"x-api-key": mask(key), "Content-Type": "application/json"},
                                           "body": body},
              "poll": f"GET {BASE}/predictions/<request_id>/result every {poll_s}s (status completed|failed|cancelled)",
              "estimatePriceUsd": est, "estimateSource": "local table (Oct 25, 2026 estimate-cost quotes)" if est is not None
              else "unknown model: real run asks /models/<slug>/estimate-cost first",
              "maxUsd": max_usd, "maxUsdDay": max_day, "ledger": LEDGER, "todayUsd": ledger_today_total(ledger_read()),
              "wouldRefuse": (est is not None and est > max_usd), "keyPresent": bool(key)})
        return

    if not key:
        emit({"error": "no muapi key at ~/secrets/muapi.json"})
        return

    # Authoritative quote (free, keyless) before spending anything.
    price, perr = estimate_remote(model, body)
    if price is None:
        if est is None:
            emit({"error": f"cannot price job: {perr}", "model": model})
            return
        price = est
    rows = ledger_read()
    today = ledger_today_total(rows)
    if price > max_usd:
        emit({"error": f"refused: job price ${price:.2f} > --max-usd {max_usd:.2f}", "priceUsd": price, "model": model})
        return
    if today + price > max_day:
        emit({"error": f"refused: today ${today:.2f} + job ${price:.2f} > --max-usd-day {max_day:.2f}",
              "priceUsd": price, "todayUsd": today, "model": model})
        return

    t0 = time.time()
    status, js = http("POST", f"/{model}", key=key, body=body, timeout=120)
    rid = js.get("request_id") or js.get("id") if isinstance(js, dict) else None
    if not (200 <= status < 300) or not rid:
        emit({"ok": False, "error": "submit: " + err_text(status, js), "model": model, "priceUsd": 0.0})
        log("hostgen", {"event": "submit_failed", "model": model, "status": status})
        return
    charged = None
    if isinstance(js.get("cost"), dict) and isinstance(js["cost"].get("amount_usd"), (int, float)):
        charged = float(js["cost"]["amount_usd"])
    ledger_append({"at": now_iso(), "model": model, "priceUsd": charged if charged is not None else price,
                   "requestId": rid, "ok": None, "line": line[:120]})
    log("hostgen", {"event": "submitted", "model": model, "requestId": rid, "priceUsd": charged or price})

    # Poll.
    result = None
    final = None
    while time.time() - t0 < MAX_WAIT_S:
        time.sleep(poll_s)
        st, rj = http("GET", f"/predictions/{rid}/result", key=key)
        if st == 200 and isinstance(rj, dict):
            result = rj
            s = str(rj.get("status", "")).lower()
            if s in ("completed", "failed", "cancelled"):
                final = s
                break
        elif st in (401, 403, 404):
            emit({"ok": False, "error": "poll: " + err_text(st, rj), "requestId": rid, "model": model})
            ledger_update(rid, ok=False, error=err_text(st, rj)[:200])
            return
    if final is None:
        emit({"ok": False, "error": f"timeout after {int(time.time() - t0)}s, last status {str((result or {}).get('status'))}",
              "requestId": rid, "model": model, "priceUsd": charged or price})
        ledger_update(rid, ok=False, error="timeout")
        return
    if isinstance(result.get("cost"), dict):
        c = result["cost"]
        if isinstance(c.get("amount_usd"), (int, float)):
            charged = float(c["amount_usd"])
        if c.get("refunded"):
            charged = 0.0
    if final != "completed":
        msg = result.get("error") or result.get("message") or result.get("detail") or final
        ledger_update(rid, ok=False, priceUsd=charged if charged is not None else price, error=str(msg)[:200])
        emit({"ok": False, "error": f"job {final}: {str(msg)[:250]}", "requestId": rid, "model": model,
              "priceUsd": charged if charged is not None else price})
        return
    outputs = result.get("outputs") or []
    output = result.get("output") if isinstance(result.get("output"), dict) else {}
    media = (outputs[0] if outputs else None) or result.get("url") or output.get("url")
    if not media:
        ledger_update(rid, ok=False, error="completed without outputs")
        emit({"ok": False, "error": "completed but no output url", "requestId": rid, "model": model,
              "priceUsd": charged if charged is not None else price, "result": {k: result.get(k) for k in ("id", "status")}})
        return

    # Download.
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    try:
        req = urllib.request.Request(media, headers={"User-Agent": "clip-autopilot-hostgen/1.0"})
        with urllib.request.urlopen(req, timeout=300) as r, open(out + ".part", "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        os.replace(out + ".part", out)
    except Exception as e:
        ledger_update(rid, ok=False, error="download")
        emit({"ok": False, "error": f"download: {str(e)[:200]}", "mediaUrl": media, "requestId": rid, "model": model,
              "priceUsd": charged if charged is not None else price})
        return

    # Verify like the Higgsfield path: whisper small.en with the line as initial_prompt, word match, 3 frames.
    v = verify(out, line)
    ok = v["match"] >= MATCH_MIN and not v["verifyError"]
    why = None
    if v["verifyError"]:
        why = v["verifyError"]
    elif v["match"] < MATCH_MIN:
        why = f"transcript matched {v['match']:.0%} of the line (< {MATCH_MIN:.0%}); file kept at {out}"
    price_final = charged if charged is not None else price
    ledger_update(rid, ok=ok, priceUsd=price_final, match=v["match"])
    res = {"ok": ok, "out": out, "seconds": media_seconds(out), "model": model, "requestId": rid,
           "priceUsd": price_final, "transcript": v["transcript"], "match": v["match"], "frames": v["frames"],
           "mediaUrl": media, "elapsed": int(time.time() - t0)}
    if why:
        res["why"] = why
    log("hostgen", {"event": "done", "ok": ok, "requestId": rid, "priceUsd": price_final, "match": v["match"]})
    emit(res)


def cmd_balance():
    key = load_key()
    if not key:
        emit({"error": "no muapi key at ~/secrets/muapi.json"})
        return
    status, js = http("GET", "/account/balance", key=key)
    if status == 200:
        emit({"ok": True, "balance": js, "ledgerTodayUsd": ledger_today_total(ledger_read())})
    else:
        emit({"error": "balance: " + err_text(status, js)})


def main():
    if len(sys.argv) < 3 or sys.argv[1] != "muapi":
        emit({"error": "usage: hostgen.py muapi line <portrait_url> \"<line>\" <out.mp4> [...] | hostgen.py muapi balance"})
        return
    try:
        if sys.argv[2] == "line":
            cmd_line()
        elif sys.argv[2] == "balance":
            cmd_balance()
        else:
            emit({"error": f"unknown subcommand {sys.argv[2]}"})
    except Exception as e:
        emit({"ok": False, "error": f"crash: {type(e).__name__}: {str(e)[:200]}"})


if __name__ == "__main__":
    main()
