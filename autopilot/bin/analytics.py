#!/usr/bin/env python3
"""DuckDB analytics over clip results (MIT). Data: JSON files in ~/autopilot/data/clips/*.json (board clipq dumps and monthly archives,
one clip per file or arrays). Usage:
  analytics.py --hours <handle>        median views7d by posting hour (ET) for one page
  analytics.py --pages                 per page: posts, median views7d, median completion, last 14 days vs previous 14
  analytics.py --hooks <niche>         views7d by hook pattern (first word class / question / number / emoji)
  analytics.py --forecast              posts per day needed vs warm accounts (needs accounts.json + campaigns.json in data/)
Prints JSON; empty data -> empty result, exit 0."""
import glob, json, os, sys
DATA = os.path.expanduser("~/autopilot/data")

def con():
    import duckdb
    c = duckdb.connect()
    files = glob.glob(os.path.join(DATA, "clips", "*.json"))
    if files:
        c.execute(f"CREATE VIEW clips AS SELECT * FROM read_json_auto({json.dumps(files)}, union_by_name=true, ignore_errors=true)")
    else:
        c.execute("CREATE TABLE clips (accountHandle VARCHAR, postedAt VARCHAR, views7d DOUBLE, completion DOUBLE, hook VARCHAR, slug VARCHAR, niche VARCHAR)")
    return c

def rows(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

def main():
    a = sys.argv[1:]
    c = con()
    if not a or a[0] == "--pages":
        q = """SELECT accountHandle, count(*) posts, median(views7d) med_views7d, median(completion) med_completion,
               median(views7d) FILTER (WHERE TRY_CAST(postedAt AS TIMESTAMP) >= now() - INTERVAL 14 DAY) last14,
               median(views7d) FILTER (WHERE TRY_CAST(postedAt AS TIMESTAMP) <  now() - INTERVAL 14 DAY AND TRY_CAST(postedAt AS TIMESTAMP) >= now() - INTERVAL 28 DAY) prev14
               FROM clips WHERE accountHandle IS NOT NULL GROUP BY 1 ORDER BY med_views7d DESC NULLS LAST"""
        print(json.dumps(rows(c.execute(q)), default=str, indent=1))
    elif a[0] == "--hours":
        q = """SELECT hour(timezone('America/New_York', TRY_CAST(postedAt AS TIMESTAMPTZ))) et_hour, count(*) posts, median(views7d) med_views7d
               FROM clips WHERE accountHandle = ? AND views7d IS NOT NULL GROUP BY 1 ORDER BY med_views7d DESC"""
        print(json.dumps(rows(c.execute(q, [a[1]])), default=str, indent=1))
    elif a[0] == "--hooks":
        q = """SELECT CASE WHEN hook LIKE '%?%' THEN 'question' WHEN regexp_matches(hook, '[0-9]') THEN 'number'
                           WHEN lower(hook) LIKE 'pov%' THEN 'pov' WHEN lower(hook) LIKE '%watch%' THEN 'watch-the-end' ELSE 'statement' END pattern,
               count(*) posts, median(views7d) med_views7d FROM clips WHERE (niche = ? OR ? = 'all') AND views7d IS NOT NULL GROUP BY 1 ORDER BY med_views7d DESC"""
        print(json.dumps(rows(c.execute(q, [a[1], a[1]])), default=str, indent=1))
    elif a[0] == "--forecast":
        acc = json.load(open(os.path.join(DATA, "accounts.json"))) if os.path.exists(os.path.join(DATA, "accounts.json")) else []
        camps = json.load(open(os.path.join(DATA, "campaigns.json"))) if os.path.exists(os.path.join(DATA, "campaigns.json")) else []
        warm = [x for x in acc if x.get("status") in ("warm", "assigned")]
        cap = sum(int(x.get("dailyMax") or 4) for x in warm)
        want = sum(int(x.get("dailyMax") or 3) for x in camps if x.get("status") == "active")
        print(json.dumps({"warmAccounts": len(warm), "postsPerDayCapacity": cap, "postsPerDayWanted": want, "shortBy": max(0, want - cap)}))
    else:
        print(json.dumps({"error": "usage"}))

if __name__ == "__main__":
    main()
