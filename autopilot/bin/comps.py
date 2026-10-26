#!/usr/bin/env python3
"""Sold-comp lookup from PUBLIC price pages (no login, no scraping behind a wall, never works around a block).
Usage: comps.py --card "Shohei Ohtani" --set "2025 Topps Chrome" [--parallel "auto /10"] [--sport baseball] [--out comps.json]
       comps.py --query "free text"            (one query string instead of the three fields)
Source: pricecharting.com public search ("sportscardspro" is the same company; eBay sold search, 130point and
sportscardspro.com answer 403 / a bot check from the sandbox, Oct 25 2026, so they are not used).
Prints JSON. Only when the match is solid does it return a price:
  {ok:true, compUrl, compPrice (ungraded, USD), compTitle, compSet, parallelMatched, matchScore, source, checkedAt}
  {ok:false, why:"no match"|"blocked:<http code>"|"parallel not matched", candidates:[...]}
The caller (FACTORY / DEAL) writes compUrl + compPrice on the item ONLY when ok is true; a numbered parallel (/10, 1/1,
refractor colour) that PriceCharting does not list separately is NOT priced from the base card (parallelMatched false).
"""
import json, re, sys, time, html, urllib.request, urllib.parse
UA = "Mozilla/5.0 (X11; Linux x86_64) pullshot-comps/1.0"
BRANDS = ("topps", "bowman", "panini", "prizm", "select", "donruss", "optic", "mosaic", "upper deck", "fleer", "leaf", "pokemon", "pokémon", "sage", "score", "chronicles", "national treasures", "flawless", "immaculate", "contenders", "heritage", "chrome", "stadium club", "gilded", "finest", "allen", "big league", "magic", "yu-gi-oh", "one piece", "lorcana")
NOISE = ("funko", "coin", "figure", "plush", "jersey", "bobblehead", "ticket", "poster")
def opt(n, d=None):
    return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d
def toks(s):
    return [t for t in re.findall(r"[a-z0-9/]+", (s or "").lower()) if t not in ("the", "of", "and", "a")]
def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return 0, str(e)[:200]
def parse_rows(page):
    out = []
    for pid, r in re.findall(r'<tr[^>]*id="product-(\d+)"[^>]*>(.*?)</tr>', page, re.S):
        t = re.search(r'<td class="title">\s*<a href="([^"]+)"[^>]*>\s*(.*?)</a>', r, re.S)
        c = re.search(r'<td class="console[^"]*">\s*<a[^>]*>\s*(.*?)\s*</a>', r, re.S)
        pr = dict(re.findall(r'<td class="price numeric (\w+)">\s*<span class="js-price">([^<]*)', r, re.S))
        if not t:
            continue
        out.append({"url": html.unescape(t.group(1)), "title": html.unescape(re.sub(r"\s+", " ", t.group(2))).strip(),
                    "set": html.unescape(c.group(1)).strip() if c else "", "ungraded": (pr.get("used_price") or "").strip()})
    return out
def price_num(s):
    m = re.search(r"\$([\d,]+(?:\.\d+)?)", s or "")
    return float(m.group(1).replace(",", "")) if m else None
def main():
    card, cset, par = opt("--card", ""), opt("--set", ""), opt("--parallel", "")
    q = opt("--query") or " ".join(x for x in (cset, card, par) if x)
    url = "https://www.pricecharting.com/search-products?" + urllib.parse.urlencode({"q": q, "type": "prices"})
    res = {"query": q, "source": "pricecharting", "checkedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    status, page = fetch(url)
    if status != 200:
        res.update(ok=False, why=f"blocked:{status}" if status in (403, 429, 503) else f"http:{status}"); return emit(res)
    rows = parse_rows(page)
    ct, st, pt = toks(card), toks(cset), toks(par)
    cands = []
    for r in rows:
        tl, sl = r["title"].lower(), r["set"].lower()
        if any(n in sl or n in tl for n in NOISE) or not any(b in sl for b in BRANDS):
            continue
        card_hit = sum(1 for t in ct if t in tl) / max(1, len(ct))
        set_hit = sum(1 for t in st if t in sl) / max(1, len(st))
        par_hit = (sum(1 for t in pt if t in tl or t in sl) / len(pt)) if pt else 1.0
        score = round(0.5 * card_hit + 0.3 * set_hit + 0.2 * par_hit, 3)
        cands.append({**r, "score": score, "cardHit": card_hit, "setHit": set_hit, "parallelMatched": par_hit >= 0.99})
    cands.sort(key=lambda x: (-x["score"], -(price_num(x["ungraded"]) or 0)))
    res["candidates"] = [{k: c[k] for k in ("title", "set", "ungraded", "score", "parallelMatched", "url")} for c in cands[:5]]
    best = next((c for c in cands if c["cardHit"] >= 0.99 and c["setHit"] >= 0.6 and price_num(c["ungraded"])), None)
    if not best:
        res.update(ok=False, why="no match"); return emit(res)
    if pt and not best["parallelMatched"]:
        res.update(ok=False, why="parallel not matched", baseCompUrl=best["url"], baseCompPrice=price_num(best["ungraded"]),
                   note="the base card has a public price but the numbered parallel does not; no price is shown for the item")
        return emit(res)
    res.update(ok=True, compUrl=best["url"], compPrice=price_num(best["ungraded"]), compTitle=best["title"], compSet=best["set"],
               parallelMatched=best["parallelMatched"], matchScore=best["score"])
    return emit(res)
def emit(res):
    o = opt("--out")
    if o:
        json.dump(res, open(o, "w"), indent=1)
    print(json.dumps(res, indent=1))
if __name__ == "__main__":
    main()
