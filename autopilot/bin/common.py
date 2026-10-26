"""Clip Autopilot shared library. Lives in ~/autopilot/bin on the Higgsfield sandbox.

Rules: tokens never printed; every script exits 0 and reports errors in its JSON output.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HOME = os.path.expanduser("~")
AP = os.path.join(HOME, "autopilot")
SECRETS = os.path.join(HOME, "secrets")
STATE = os.path.join(AP, "state")
OUT = os.path.join(AP, "out")
LOGS = os.path.join(AP, "logs")

# Pinned API version (checked Oct 24, 2026: v25.0 released Feb 2026; change only here).
API_VERSION = "v25.0"
GRAPH = f"https://graph.instagram.com/{API_VERSION}"
GRAPH_FB = f"https://graph.facebook.com/{API_VERSION}"

# Insights metrics (Reels). Confirm against Meta's docs when a call returns error 100 on a metric.
REELS_METRICS = ["views", "reach", "likes", "comments", "shares", "saved",
                 "ig_reels_avg_watch_time", "ig_reels_video_view_total_time"]
STORY_METRICS = ["views", "reach", "replies"]
IMAGE_METRICS = ["views", "reach", "likes", "comments", "shares", "saved"]

RATE_LIMIT_CODES = {4, 17, 32, 613, 80002}
TOKEN_CODES = {190, 102, 463, 467}


class NoSecret(Exception):
    pass


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ensure_dirs():
    for d in (AP, STATE, OUT, LOGS, os.path.join(AP, "queue")):
        os.makedirs(d, exist_ok=True)


def load_secret(name):
    path = os.path.join(SECRETS, name + ".json")
    if not os.path.exists(path):
        raise NoSecret(f"no secret file for {name}")
    with open(path) as f:
        return json.load(f)


def save_secret(name, obj):
    os.makedirs(SECRETS, exist_ok=True)
    path = os.path.join(SECRETS, name + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def ig_accounts():
    """All Instagram secrets: list of dicts {username, ig_user_id, access_token, expires_at, kind}."""
    out = []
    if not os.path.isdir(SECRETS):
        return out
    for fn in sorted(os.listdir(SECRETS)):
        if fn.startswith("ig-") and fn.endswith(".json"):
            try:
                with open(os.path.join(SECRETS, fn)) as f:
                    out.append(json.load(f))
            except Exception:
                pass
    return out


def ig_secret(username):
    return load_secret("ig-" + username.lstrip("@").lower())


def _request(method, url, params=None, data=None, timeout=60):
    params = dict(params or {})
    if method == "GET":
        if params:
            url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method="GET")
    else:
        body = urllib.parse.urlencode({**params, **(data or {})}).encode()
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode() or "{}"
            return r.status, json.loads(raw) if raw.strip().startswith(("{", "[")) else {"raw": raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="ignore")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:500]}
    except Exception as e:  # network
        return 0, {"error": {"message": str(e)[:300], "code": -1}}


def api(method, url, params=None, data=None, token=None, retries=5):
    """Call the Graph API with backoff. Returns dict. On failure: {'error': {...}, 'kind': 'token'|'rate'|'net'|'api'}."""
    params = dict(params or {})
    if token:
        params["access_token"] = token
    delay = 4
    last = None
    for attempt in range(retries):
        status, js = _request(method, url, params=params, data=data)
        err = js.get("error") if isinstance(js, dict) else None
        if status and 200 <= status < 300 and not err:
            return js
        code = (err or {}).get("code")
        last = {"error": {"status": status, "code": code, "subcode": (err or {}).get("error_subcode"),
                          "message": str((err or {}).get("message", js))[:300]}}
        if code in TOKEN_CODES:
            last["kind"] = "token"
            return last
        if code in RATE_LIMIT_CODES or status == 429 or status >= 500 or status == 0:
            last["kind"] = "rate" if status else "net"
            time.sleep(delay)
            delay = min(delay * 2, 60)
            continue
        last["kind"] = "api"
        return last
    return last


def is_err(js):
    return isinstance(js, dict) and "error" in js


def log(task, event):
    ensure_dirs()
    path = os.path.join(LOGS, f"{task}-{time.strftime('%Y-%m-%d')}.jsonl")
    with open(path, "a") as f:
        f.write(json.dumps({"at": now_iso(), **event}) + "\n")


def job(path):
    with open(path) as f:
        return json.load(f)


def out(path, obj):
    ensure_dirs()
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)
    return path


def emit(obj, name=None):
    """Write the output file (if name) and print it."""
    if name:
        out(os.path.join(OUT, name), obj)
    print(json.dumps(obj, indent=1))


def ffprobe_url(url):
    cmd = ["ffprobe", "-v", "error", "-show_entries",
           "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate",
           "-of", "json", url]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        js = json.loads(p.stdout or "{}")
    except Exception as e:
        return {"error": str(e)[:200]}
    v = next((s for s in js.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in js.get("streams", []) if s.get("codec_type") == "audio"), {})
    fps = 0.0
    try:
        n, d = (v.get("r_frame_rate") or "0/1").split("/")
        fps = float(n) / float(d or 1)
    except Exception:
        pass
    fmt = js.get("format", {})
    size = int(fmt.get("size") or 0)
    if not size:
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=30) as r:
                size = int(r.headers.get("Content-Length") or 0)
        except Exception:
            pass
    return {"duration": float(fmt.get("duration") or 0), "width": v.get("width"), "height": v.get("height"),
            "vcodec": v.get("codec_name"), "acodec": a.get("codec_name"), "fps": round(fps, 2), "size": size}


def reel_spec_ok(p):
    """Our house spec for Reels. Returns (ok, reason)."""
    if p.get("error"):
        return False, "probe:" + p["error"]
    if p.get("vcodec") != "h264":
        return False, f"vcodec {p.get('vcodec')}"
    if p.get("acodec") not in ("aac", None):
        return False, f"acodec {p.get('acodec')}"
    if p.get("acodec") is None:
        return False, "no audio"
    if abs((p.get("width") or 0) - 1080) > 2 or abs((p.get("height") or 0) - 1920) > 2:
        return False, f"size {p.get('width')}x{p.get('height')}"
    if not (3 <= p.get("duration", 0) <= 90):
        return False, f"duration {p.get('duration')}"
    if p.get("size", 0) > 100 * 1024 * 1024:
        return False, "over 100 MB"
    if not (23 <= p.get("fps", 0) <= 60):
        return False, f"fps {p.get('fps')}"
    return True, ""


def file_hash(url, nbytes=2 * 1024 * 1024):
    req = urllib.request.Request(url, headers={"Range": f"bytes=0-{nbytes - 1}"})
    h = hashlib.md5()
    with urllib.request.urlopen(req, timeout=60) as r:
        h.update(r.read(nbytes))
    return h.hexdigest()


def read_state(name, default):
    path = os.path.join(STATE, name)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return default


def write_state(name, obj):
    out(os.path.join(STATE, name), obj)


def arg(i, default=None):
    return sys.argv[i] if len(sys.argv) > i else default
