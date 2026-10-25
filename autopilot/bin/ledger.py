#!/usr/bin/env python3
"""ledger.py - global footage ledger so the same stream window is never posted by two of our pages. One JSON line out, exit 0.
  ledger.py check  <sourceUrl> <offsetS> [--len 20] [--account h]       -> {"free": bool, "conflict": window|null}
  ledger.py claim  <sourceUrl> <offsetS> <account> <itemId> [--len 20]  -> {"ok": bool, "conflict": ...} appends status "queued"
  ledger.py set <itemId> <queued|live|retired|bad> | ledger.py list [--account h] [--since ISO] | ledger.py import <json file>
Conflict: same normalised sourceUrl (no query, no trailing slash, lower-case host) and |offset - other.offset| < 90 s, across ALL
accounts; retired/bad windows never conflict. import never refuses (dedupe by itemId). State: ~/autopilot/state/ledger.json (atomic).
"""
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_state, write_state, log, now_iso  # noqa: E402

STATE_NAME = "ledger.json"
WINDOW_S = 90
STATUSES = ("queued", "live", "retired", "bad")
INACTIVE = ("retired", "bad")
IMPORT_STATUS = {"live": "live", "ready": "queued", "posting": "queued", "hold": "queued",
                 "queued": "queued", "bad": "bad", "retired": "retired"}


def emit(obj):
    print(json.dumps(obj, separators=(",", ":")))
    sys.exit(0)


def norm_url(u):
    """Lower-case host, drop query string and fragment, strip trailing slash."""
    u = (u or "").strip()
    try:
        p = urllib.parse.urlsplit(u)
    except Exception:
        return u.rstrip("/")
    if not p.scheme or not p.netloc:
        return u.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    path = p.path.rstrip("/")
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), path, "", ""))


def norm_account(a):
    return (a or "").strip().lstrip("@").lower()


def to_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def load():
    st = read_state(STATE_NAME, {"windows": []})
    if not isinstance(st, dict) or not isinstance(st.get("windows"), list):
        st = {"windows": []}
    return st


def save(st):
    write_state(STATE_NAME, st)  # common.out(): temp file + os.replace


def find_conflict(windows, url, offset):
    """First active window on the same normalised url whose offset is within WINDOW_S seconds."""
    nurl = norm_url(url)
    off = to_float(offset)
    for w in windows:
        if w.get("status") in INACTIVE:
            continue
        if norm_url(w.get("sourceUrl")) != nurl:
            continue
        if abs(off - to_float(w.get("offsetS"))) < WINDOW_S:
            return w
    return None


def parse_opts(args):
    """Split positional args from --key value options."""
    pos, opts = [], {}
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            key = a[2:]
            if "=" in key:
                k, v = key.split("=", 1)
                opts[k] = v
            elif i + 1 < len(args):
                opts[key] = args[i + 1]
                i += 1
            else:
                opts[key] = ""
        else:
            pos.append(a)
        i += 1
    return pos, opts


def cmd_check(pos, opts):
    if len(pos) < 2:
        emit({"free": False, "error": "usage: check <sourceUrl> <offsetS> [--len 20] [--account h]"})
    st = load()
    c = find_conflict(st["windows"], pos[0], pos[1])
    emit({"free": c is None, "conflict": c})


def cmd_claim(pos, opts):
    if len(pos) < 4:
        emit({"ok": False, "error": "usage: claim <sourceUrl> <offsetS> <account> <itemId> [--len 20]"})
    url, offset, account, item_id = pos[0], to_float(pos[1]), norm_account(pos[2]), str(pos[3])
    length = to_float(opts.get("len", 20), 20.0)
    st = load()
    for w in st["windows"]:
        if str(w.get("itemId")) == item_id and norm_account(w.get("account")) == account:
            emit({"ok": True, "idempotent": True, "window": w})  # same account re-claiming: no duplicate
    c = find_conflict(st["windows"], url, offset)
    if c is not None:
        log("ledger", {"event": "claim_refused", "account": account, "itemId": item_id, "conflict": c})
        emit({"ok": False, "conflict": c})
    row = {"sourceUrl": norm_url(url), "offsetS": offset, "lenS": length, "account": account,
           "itemId": item_id, "at": now_iso(), "status": "queued"}
    st["windows"].append(row)
    save(st)
    log("ledger", {"event": "claim", **row})
    emit({"ok": True, "window": row})


def cmd_set(pos, opts):
    if len(pos) < 2 or pos[1] not in STATUSES:
        emit({"ok": False, "error": "usage: set <itemId> <queued|live|retired|bad>"})
    item_id, status = str(pos[0]), pos[1]
    account = norm_account(opts.get("account")) if opts.get("account") else None
    st = load()
    n = 0
    for w in st["windows"]:
        if str(w.get("itemId")) != item_id:
            continue
        if account and norm_account(w.get("account")) != account:
            continue
        if w.get("status") != status:
            w["status"] = status
            w["updatedAt"] = now_iso()
        n += 1
    if n:
        save(st)
        log("ledger", {"event": "set", "itemId": item_id, "status": status, "updated": n})
    emit({"ok": n > 0, "updated": n, "itemId": item_id, "status": status})


def cmd_list(pos, opts):
    st = load()
    account = norm_account(opts.get("account")) if opts.get("account") else None
    since = opts.get("since")
    rows = [w for w in st["windows"]
            if (not account or norm_account(w.get("account")) == account)
            and (not since or str(w.get("updatedAt") or w.get("at") or "") >= since)]
    emit({"count": len(rows), "windows": rows})


def cmd_import(pos, opts):
    if not pos:
        emit({"ok": False, "error": "usage: import <json file>"})
    try:
        with open(pos[0]) as f:
            data = json.load(f)
    except Exception as e:
        emit({"ok": False, "error": f"read {pos[0]}: {str(e)[:200]}"})
    if isinstance(data, dict):
        data = data.get("rows") or data.get("items") or data.get("windows") or []
    st = load()
    present = {str(w.get("itemId")) for w in st["windows"]}
    added = skipped = invalid = 0
    for r in data if isinstance(data, list) else []:
        if not isinstance(r, dict):
            invalid += 1
            continue
        item_id = r.get("id") or r.get("itemId")
        url = r.get("sourceUrl") or r.get("url")
        account = norm_account(r.get("handle") or r.get("accountHandle") or r.get("account"))
        if not item_id or not url:
            invalid += 1
            continue
        key = str(item_id)
        if key in present:
            skipped += 1
            continue
        status = IMPORT_STATUS.get(str(r.get("status") or "").lower(), "queued")
        row = {"sourceUrl": norm_url(url), "offsetS": to_float(r.get("sourceOffsetS", r.get("offsetS"))),
               "lenS": to_float(r.get("lenS", r.get("len", 20)), 20.0), "account": account,
               "itemId": str(item_id), "at": r.get("at") or now_iso(), "status": status, "imported": True}
        st["windows"].append(row)
        present.add(key)
        added += 1
    if added:
        save(st)
    log("ledger", {"event": "import", "file": pos[0], "added": added, "skipped": skipped, "invalid": invalid})
    emit({"ok": True, "added": added, "skipped": skipped, "invalid": invalid, "total": len(st["windows"])})


COMMANDS = {"check": cmd_check, "claim": cmd_claim, "set": cmd_set, "list": cmd_list, "import": cmd_import}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in COMMANDS:
        emit({"ok": False, "error": "usage: ledger.py check|claim|set|list|import ...", "commands": sorted(COMMANDS)})
    pos, opts = parse_opts(sys.argv[2:])
    try:
        COMMANDS[cmd](pos, opts)
    except SystemExit:
        raise
    except Exception as e:
        emit({"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}"})


if __name__ == "__main__":
    main()
