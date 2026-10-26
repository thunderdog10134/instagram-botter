#!/usr/bin/env python3
"""Background moment scanner for Clip Autopilot (Josh, Oct 25 10:30 PM ET: "make enough factories to sustain the amount
of content we need ... delegate those factories so that they're efficient").

The expensive, judgement-free part of CLIP FACTORY (list a channel's replays, fetch a 20-minute slice, rank its hype
moments) runs here as a plain loop with no LLM in it, around the clock, at low CPU priority. The factories (one per
niche, hourly) then start from a queue of pre-ranked moments whose slice is already on disk and spend their time on
the parts that need judgement: looking at frames, framing, captions, comps, assembly, the board.

  scanner.py run [--hours 6] [--niches cards,tcg] [--keep 10] [--min 0.40] [--slice 1200]
        loop: for each niche with fewer than --keep "new" entries, pick channels (channels.py pick, same weighted
        random as FACTORY), list replays (streams.py), skip used/scanned/excluded/sign-in-refused ones, cut one
        20-minute slice (middle of the replay; three slices from different thirds for replays over 90 min), rank it
        (moments.py --rank --top 5 --words-top 3), write state/momentq/<id>.json. A slice whose best reaction is
        under --min is deleted (its entry stays as status "empty" so it is never fetched again). Stops after --hours
        or when every niche holds --keep new entries (it is relaunched by every factory run). One instance at a time
        (state/scanner.pid). Everything heavy runs under nice 15 so a factory's own cut keeps the CPU.
  scanner.py status                      -> {running, pid, startedAt, lastAt, counts per niche, lastError}
  scanner.py list --niche cards|tcg [--status new]   -> entries, best first (JSON)
  scanner.py claim <id> <runId>          -> status "claimed" (refused if not new)
  scanner.py done <id> [<itemId>]        -> status "done", slice deleted
  scanner.py drop <id> "<why>"           -> status "dropped", slice deleted
  scanner.py release <id>                -> back to "new" (a factory that could not finish)

Rules kept from FACTORY: never bypass a block (a refused fetch is recorded as "refused" and the channel is left
alone), never a gambling-sponsored replay (streams.py marks them "excluded"), YouTube is never fetched here (blocked
from the sandbox; FACTORY reads ref/yt-cache.json itself), nothing is posted or written to the board from here.
Entry: {id, niche, platform, channel, handle, replayId, replayTitle, replayCreated, replaySeconds, sourceUrl,
        sliceStart, sliceLen, slicePath, best, moments[], status, scannedAt, claimedBy, claimedAt, why}
"""
import json, os, re, signal, subprocess, sys, time

HOME = os.path.expanduser("~/autopilot")
BIN = os.path.join(HOME, "bin")
STATE = os.path.join(HOME, "state")
QDIR = os.path.join(STATE, "momentq")
WORK = os.path.join(HOME, "work", "scan")
PIDF = os.path.join(STATE, "scanner.pid")
STATF = os.path.join(STATE, "scanner.json")
SCANNED = os.path.join(STATE, "scanned.json")
USED = os.path.join(STATE, "used-replays.json")
LOGF = os.path.join(STATE, "scanner.log")
ENV = dict(os.environ, PYTHONPATH="/home/user/pylib")
NICE = ["nice", "-n", "15"]


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def log(msg):
    line = f"{now()} {msg}"
    print(line, flush=True)
    try:
        with open(LOGF, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def jload(p, default):
    try:
        return json.load(open(p))
    except Exception:
        return default


def jsave(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    json.dump(obj, open(tmp, "w"), indent=1)
    os.replace(tmp, p)


def opt(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else default
    return default


def run(cmd, timeout):
    """Run a command; return (code, stdout, stderr). Never raises."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=ENV)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as e:
        return 1, "", str(e)


def entry_path(eid):
    return os.path.join(QDIR, eid + ".json")


def entries(niche=None, status=None):
    out = []
    if not os.path.isdir(QDIR):
        return out
    for fn in sorted(os.listdir(QDIR)):
        if not fn.endswith(".json"):
            continue
        e = jload(os.path.join(QDIR, fn), None)
        if not e:
            continue
        if niche and e.get("niche") != niche:
            continue
        if status and e.get("status") != status:
            continue
        out.append(e)
    out.sort(key=lambda e: (-(e.get("best") or 0), e.get("scannedAt") or ""))
    return out


def used_set():
    """used-replays.json holds replay ids (kick uuid / twitch vNNN) and, for long replays, '<id>+<start>' or
    '<id>@<start>' per slice. Returns ({whole ids}, {id: [starts]})."""
    whole, parts = set(), {}
    for u in jload(USED, []):
        if not isinstance(u, str):
            continue
        m = re.match(r"^([A-Za-z0-9-]+)[+@:](\d+)$", u)
        if m:
            parts.setdefault(m.group(1), []).append(int(m.group(2)))
        else:
            whole.add(u)
    return whole, parts


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def status_cmd():
    st = jload(STATF, {})
    pid = jload(PIDF, None) if os.path.exists(PIDF) else None
    try:
        pid = int(open(PIDF).read().strip()) if os.path.exists(PIDF) else None
    except Exception:
        pid = None
    running = bool(pid and alive(pid))
    counts = {}
    for e in entries():
        n = e.get("niche", "?")
        counts.setdefault(n, {})
        counts[n][e.get("status", "?")] = counts[n].get(e.get("status", "?"), 0) + 1
    print(json.dumps({"running": running, "pid": pid if running else None, "startedAt": st.get("startedAt"),
                      "lastAt": st.get("lastAt"), "lastError": st.get("lastError"), "scanned": st.get("scanned", 0),
                      "counts": counts, "queueDir": QDIR}))


def list_cmd():
    niche = opt("--niche")
    status = opt("--status", "new")
    if status == "any":
        status = None
    out = []
    for e in entries(niche, status):
        out.append({k: e.get(k) for k in ("id", "niche", "platform", "channel", "handle", "replayId", "replayTitle",
                                           "replayCreated", "sourceUrl", "sliceStart", "sliceLen", "slicePath", "best",
                                           "status", "scannedAt", "claimedBy")} |
                   {"moments": [{k: m.get(k) for k in ("key", "peak", "start", "end", "reaction", "components", "hypeWords", "said")}
                                for m in e.get("moments", [])]})
    print(json.dumps({"niche": niche, "status": status or "any", "n": len(out), "entries": out}, separators=(",", ":")))


def set_status(eid, new, **extra):
    p = entry_path(eid)
    e = jload(p, None)
    if not e:
        print(json.dumps({"ok": False, "error": "no such entry", "id": eid}))
        return 1
    if new == "claimed" and e.get("status") != "new":
        print(json.dumps({"ok": False, "error": f"not new (status {e.get('status')})", "id": eid}))
        return 1
    e["status"] = new
    e.update(extra)
    if new in ("done", "dropped", "empty"):
        sp = e.get("slicePath")
        if sp and os.path.exists(sp):
            try:
                os.remove(sp)
            except Exception:
                pass
        for extra_f in ("moments.json",):
            pass
    jsave(p, e)
    print(json.dumps({"ok": True, "id": eid, "status": new}))
    return 0


def pick_channels(niche, n, exclude):
    cmd = ["python3", os.path.join(BIN, "channels.py"), "pick", str(n), "--niche", niche]
    if exclude:
        cmd += ["--exclude", ",".join(sorted(exclude))]
    code, out, err = run(cmd, 120)
    if code != 0:
        log(f"pick {niche} failed: {err.strip()[:200]}")
        return []
    try:
        return [c for c in json.loads(out).get("picked", []) if c.get("platform") in ("kick", "twitch")]
    except Exception:
        return []


def list_replays(platform, handle):
    code, out, err = run(["python3", os.path.join(BIN, "streams.py"), platform, "list", handle, "20"], 120)
    if code != 0:
        return None, (err or out).strip()[:200]
    try:
        d = json.loads(out)
    except Exception:
        return None, out.strip()[:200]
    if isinstance(d, dict) and d.get("error"):
        return None, str(d["error"])[:200]
    return (d if isinstance(d, list) else d.get("replays") or d.get("data") or []), None


def replay_fields(platform, handle, r):
    if platform == "kick":
        rid = r.get("uuid") or ""
        url = f"https://kick.com/{handle}/videos/{rid}"
        return rid, url
    url = r.get("url") or ""
    m = re.search(r"/videos/(\d+)", url)
    rid = ("v" + m.group(1)) if m else ("v" + str(r.get("id") or ""))
    if not url and m is None and r.get("id"):
        url = f"https://www.twitch.tv/videos/{r['id']}"
    return rid, url


def slice_starts(seconds, slen):
    if seconds <= 0:
        return [0]
    if seconds > 5400:
        return [int(seconds / 6 - slen / 2), int(seconds / 2 - slen / 2), int(5 * seconds / 6 - slen / 2)]
    return [max(0, int(seconds / 2 - slen / 2))]


def cut(platform, handle, rid, url, start, slen, out):
    if platform == "kick":
        cmd = ["python3", os.path.join(BIN, "streams.py"), "kick", "cut", handle, rid, str(start), str(slen), out]
    else:
        cmd = ["python3", os.path.join(BIN, "streams.py"), "twitch", "cut", url, str(start), str(slen), out]
    code, so, se = run(NICE + cmd, 900)
    err = None
    try:
        d = json.loads(so.strip().splitlines()[-1]) if so.strip() else {}
        if isinstance(d, dict) and d.get("error"):
            err = str(d["error"])[:200]
    except Exception:
        pass
    if code != 0 and not err:
        err = (se or so).strip()[-200:] or f"exit {code}"
    if not err and (not os.path.exists(out) or os.path.getsize(out) < 1_000_000):
        err = "empty slice"
    return err


def rank(slice_path, out_json):
    cmd = ["python3", os.path.join(BIN, "moments.py"), slice_path, out_json, "--rank", "--top", "5", "--words-top", "3",
           "--hype-words", os.path.join(BIN, "hype_breaks.txt")]
    code, so, se = run(NICE + cmd, 900)
    if code != 0 or not os.path.exists(out_json):
        return None, (se or so).strip()[-200:] or f"exit {code}"
    return jload(out_json, None), None


def refused(msg):
    m = (msg or "").lower()
    return any(k in m for k in ("sign in", "sign-in", "login", "subscriber", "403", "401", "forbidden", "bot", "cookies", "unavailable", "404"))


def run_cmd():
    hours = float(opt("--hours", "6"))
    niches = [n for n in opt("--niches", "cards,tcg").split(",") if n]
    keep = int(opt("--keep", "10"))
    minr = float(opt("--min", "0.40"))
    slen = int(opt("--slice", "1200"))
    # one instance
    if os.path.exists(PIDF):
        try:
            old = int(open(PIDF).read().strip())
            if alive(old):
                print(json.dumps({"ok": False, "error": f"already running (pid {old})"}))
                return 0
        except Exception:
            pass
    os.makedirs(STATE, exist_ok=True); os.makedirs(QDIR, exist_ok=True); os.makedirs(WORK, exist_ok=True)
    open(PIDF, "w").write(str(os.getpid()))
    st = jload(STATF, {})
    st.update({"startedAt": now(), "pid": os.getpid(), "hours": hours, "niches": niches, "keep": keep, "min": minr})
    jsave(STATF, st)
    stop = {"flag": False}

    def _stop(*a):
        stop["flag"] = True
    signal.signal(signal.SIGTERM, _stop)
    deadline = time.time() + hours * 3600
    log(f"scanner start niches={niches} keep={keep} min={minr} hours={hours}")
    scanned = jload(SCANNED, {})
    idle_rounds = 0
    while not stop["flag"] and time.time() < deadline:
        did = False
        for niche in niches:
            if stop["flag"] or time.time() >= deadline:
                break
            fresh = len(entries(niche, "new"))
            if fresh >= keep:
                continue
            whole, parts = used_set()
            recent = {k.split(":")[1] for k, v in scanned.items() if v.get("at", "") > time.strftime("%Y-%m-%dT%H", time.gmtime(time.time() - 4 * 3600))}
            picks = pick_channels(niche, 3, recent)
            if not picks:
                picks = pick_channels(niche, 3, set())
            for c in picks:
                if stop["flag"] or time.time() >= deadline:
                    break
                platform, handle = c["platform"], c["handle"]
                reps, err = list_replays(platform, handle)
                if reps is None:
                    scanned[f"{platform}:{handle}:list"] = {"at": now(), "error": err}
                    jsave(SCANNED, scanned)
                    log(f"{niche} {platform}:{handle} list failed: {err}")
                    continue
                job = None
                for r in reps:
                    if r.get("excluded"):
                        continue
                    secs = int(r.get("seconds") or 0)
                    if secs < 1500:
                        continue
                    rid, url = replay_fields(platform, handle, r)
                    if not rid or rid in whole:
                        continue
                    for start in slice_starts(secs, slen):
                        key = f"{platform}:{handle}:{rid}@{start}"
                        if key in scanned:
                            continue
                        if any(abs(start - s) < slen for s in parts.get(rid, [])):
                            continue
                        job = (r, rid, url, start, secs)
                        break
                    if job:
                        break
                if not job:
                    scanned[f"{platform}:{handle}:list"] = {"at": now(), "note": "nothing unscanned"}
                    jsave(SCANNED, scanned)
                    continue
                r, rid, url, start, secs = job
                eid = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{niche}-{platform}-{handle}-{rid}-{start}")
                d = os.path.join(WORK, eid); os.makedirs(d, exist_ok=True)
                sp = os.path.join(d, "slice.mp4")
                key = f"{platform}:{handle}:{rid}@{start}"
                log(f"{niche} cut {platform}:{handle} {rid} @{start} ({secs}s replay)")
                t0 = time.time()
                err = cut(platform, handle, rid, url, start, slen, sp)
                if err:
                    scanned[key] = {"at": now(), "error": err, "refused": refused(err)}
                    jsave(SCANNED, scanned)
                    st.update({"lastAt": now(), "lastError": f"{key}: {err}"}); jsave(STATF, st)
                    log(f"{niche} cut failed {key}: {err}")
                    try:
                        if os.path.exists(sp):
                            os.remove(sp)
                    except Exception:
                        pass
                    continue
                mj = os.path.join(d, "moments.json")
                res, err = rank(sp, mj)
                if not res:
                    scanned[key] = {"at": now(), "error": "rank: " + (err or "?")}
                    jsave(SCANNED, scanned)
                    st.update({"lastAt": now(), "lastError": f"{key}: rank {err}"}); jsave(STATF, st)
                    log(f"{niche} rank failed {key}: {err}")
                    continue
                moments = res.get("moments", [])
                best = max([m.get("reaction") or 0 for m in moments] or [0])
                e = {"id": eid, "niche": niche, "platform": platform, "channel": c.get("name") or handle, "handle": handle,
                     "instagram": c.get("instagram"), "channelScore": c.get("score"), "maxRes": c.get("maxRes"),
                     "replayId": rid, "replayTitle": r.get("title"), "replayCreated": r.get("created"), "replaySeconds": secs,
                     "sourceUrl": url, "sliceStart": start, "sliceLen": slen, "slicePath": sp, "momentsPath": mj,
                     "best": round(best, 3), "moments": moments, "rankSeconds": res.get("seconds"), "scannedAt": now(),
                     "status": "new" if best >= minr else "empty", "claimedBy": None, "claimedAt": None, "why": None}
                if e["status"] == "empty":
                    try:
                        os.remove(sp)
                    except Exception:
                        pass
                jsave(entry_path(eid), e)
                scanned[key] = {"at": now(), "best": e["best"], "status": e["status"]}
                jsave(SCANNED, scanned)
                st["scanned"] = int(st.get("scanned", 0)) + 1
                st.update({"lastAt": now(), "lastError": None}); jsave(STATF, st)
                log(f"{niche} {key} best {e['best']} -> {e['status']} ({int(time.time() - t0)} s)")
                did = True
                if len(entries(niche, "new")) >= keep:
                    break
        if not did:
            idle_rounds += 1
            if all(len(entries(n, "new")) >= keep for n in niches):
                log("every niche full; scanner stops")
                break
            if idle_rounds >= 6:
                log("nothing left to scan this round; scanner stops")
                break
            time.sleep(60)
        else:
            idle_rounds = 0
    try:
        os.remove(PIDF)
    except Exception:
        pass
    st.update({"endedAt": now()}); jsave(STATF, st)
    log("scanner end")
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 2
    cmd = sys.argv[1]
    if cmd == "run":
        return run_cmd()
    if cmd == "status":
        return status_cmd()
    if cmd == "list":
        return list_cmd()
    if cmd == "claim" and len(sys.argv) >= 4:
        return set_status(sys.argv[2], "claimed", claimedBy=sys.argv[3], claimedAt=now())
    if cmd == "done" and len(sys.argv) >= 3:
        return set_status(sys.argv[2], "done", itemId=(sys.argv[3] if len(sys.argv) > 3 else None), doneAt=now())
    if cmd == "drop" and len(sys.argv) >= 3:
        return set_status(sys.argv[2], "dropped", why=(sys.argv[3] if len(sys.argv) > 3 else ""), doneAt=now())
    if cmd == "release" and len(sys.argv) >= 3:
        return set_status(sys.argv[2], "new", claimedBy=None, claimedAt=None)
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main() or 0)
