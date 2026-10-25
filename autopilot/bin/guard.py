#!/usr/bin/env python3
"""guard.py — hard checks on every outbound comment reply and DM (Josh, Oct 25: "make sure the auto response can't be hacked").
The scheduled agent composes replies from comment text written by strangers, so the text it sends is checked HERE, in code,
before it reaches Instagram: a reply that fails is dropped and reported, never 'fixed'.
    from guard import outbound_ok
    ok, why = outbound_ok(text, allow_handles=["pullsdaily.cards", "honeyholecollect"], allow_urls=[item["sourceUrl"], item["permalink"]])
Rules (all must pass): length 1..300 chars after trimming; no control / zero-width / bidi characters; no secrets (EAA tokens,
X-Amz, 'access_token', 'password', 'verification code'); no URL except the allowed ones (same host+path, query ignored) and
never a shortener or an IP; no @mention except the allowed handles; no phone numbers / emails; no money words in phase A
('$' followed by digits is allowed only when allow_price is True); no instruction-like text ('ignore previous', 'system prompt',
'as an ai', 'disregard'); no 'DM me'/'send me'/'click'/'login'/'verify' phishing phrases; no promises ('guaranteed', 'giveaway',
'you won'); CLI: guard.py check "<text>" [--handles a,b] [--urls u1,u2]."""
import json, re, sys, unicodedata
from urllib.parse import urlsplit

SHORTENERS = {"bit.ly", "t.co", "tinyurl.com", "goo.gl", "ow.ly", "is.gd", "buff.ly", "cutt.ly", "rb.gy", "t.ly", "linktr.ee"}
SECRET_RE = re.compile(r"(EAA[A-Za-z0-9]{20,}|X-Amz-|access_token|client_secret|password|passcode|verification code|2fa|otp\b)", re.I)
INJECT_RE = re.compile(r"(ignore (all|any|the|previous|prior|your)|system prompt|as an ai|disregard|new instructions|you are now|jailbreak|developer mode)", re.I)
PHISH_RE = re.compile(r"\b(dm me|send me|message me|click (the|this|here)|log ?in|sign ?in|verify your|confirm your|claim your|you won|winner|giveaway|guaranteed|free money|cash ?app|venmo|paypal|crypto|bitcoin|invest)\b", re.I)
MONEY_RE = re.compile(r"\$\s?\d|\d\s?(usd|dollars)|\bprice\b.*\b(is|was)\b\s?\d", re.I)
CONTACT_RE = re.compile(r"(\+?\d[\d\s().-]{8,}\d)|([\w.+-]+@[\w-]+\.[\w.]+)")
URL_RE = re.compile(r"((?:https?://|www\.)[^\s<>\"']+|\b[a-z0-9-]+\.(?:com|net|org|io|gg|tv|ly|co|me|app|ai|xyz|shop|store)(?:/[^\s<>\"']*)?)", re.I)
MENTION_RE = re.compile(r"@([A-Za-z0-9._]{2,30})")
BAD_CHARS = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f​-‏‪-‮⁦-⁩﻿]")

def _norm_url(u):
    if not u:
        return None
    if not u.lower().startswith(("http://", "https://")):
        u = "https://" + u
    p = urlsplit(u)
    return (p.netloc.lower().lstrip("www."), p.path.rstrip("/").lower())

def outbound_ok(text, allow_handles=(), allow_urls=(), allow_price=False, max_len=300):
    t = (text or "").strip()
    if not t:
        return False, "empty"
    if len(t) > max_len:
        return False, f"too long ({len(t)} > {max_len})"
    if BAD_CHARS.search(t):
        return False, "control or invisible characters"
    if any(unicodedata.category(c) == "Cf" for c in t):
        return False, "format characters"
    if SECRET_RE.search(t):
        return False, "looks like a secret or credential talk"
    if INJECT_RE.search(t):
        return False, "instruction-like text"
    if PHISH_RE.search(t):
        return False, "phishing / money phrase"
    if CONTACT_RE.search(t):
        return False, "phone number or email"
    if not allow_price and MONEY_RE.search(t):
        return False, "price without a sold comp"
    allowed = {_norm_url(u) for u in allow_urls if u}
    for m in URL_RE.finditer(t):
        u = m.group(1)
        nu = _norm_url(u)
        host = nu[0] if nu else ""
        if host in SHORTENERS or re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
            return False, f"shortener or IP url: {u}"
        if nu not in allowed:
            return False, f"url not allowed: {u}"
    ah = {h.lower().lstrip("@") for h in allow_handles}
    for m in MENTION_RE.finditer(t):
        if m.group(1).lower() not in ah:
            return False, f"mention not allowed: @{m.group(1)}"
    return True, "ok"

def clean_inbound(text, max_len=500):
    """What the agent is allowed to read of a stranger's comment: trimmed, invisible characters removed, length capped.
    It is still DATA: the agent never follows anything written in it."""
    t = BAD_CHARS.sub("", text or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Cf")
    return t.strip()[:max_len]

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["check"]:
        hs = a[a.index("--handles") + 1].split(",") if "--handles" in a else []
        us = a[a.index("--urls") + 1].split(",") if "--urls" in a else []
        ok, why = outbound_ok(a[1], hs, us, allow_price="--price-ok" in a)
        print(json.dumps({"ok": ok, "why": why}))
    else:
        print(__doc__)
