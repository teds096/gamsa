#!/usr/bin/env python3
"""Weekly totals from Cloudflare Web Analytics into data/analytics.json (hub item B-23, v19).

Run once a week by .github/workflows/analytics.yml. Reads two environment variables (GitHub secrets):
  CLOUDFLARE_ANALYTICS_TOKEN  read-only Cloudflare API token: Account > Account Analytics > Read
  CLOUDFLARE_ACCOUNT_ID       the Cloudflare account ID
If either is missing it prints "... not set, skipping" and exits 0 (nothing is written).
Optional: CLOUDFLARE_ANALYTICS_SITE_TAG (not secret) counts one Web Analytics site by its site tag
instead of filtering on the hostnames gamsa.au and www.gamsa.au.

What it writes (totals only): per week (Monday to Sunday, Adelaide time) page views, visits, and the top
pages, outside referrer hosts and countries. No IP addresses, user agents or per-visit rows are asked for.
Any entry with fewer than MIN_VIEWS page views, and any odd-looking path or host, is folded into "(other)",
so a single visit never shows. Cloudflare samples Web Analytics, so these are the same estimates the
dashboard shows. data/analytics.json is a data file: never in a release zip, never read by build.py.

Options: --weeks N   recent complete weeks to re-fetch each run (default 2; missing weeks are back-filled
                     up to BACKFILL weeks)
         --dry-run   print the JSON instead of writing it
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Australia/Adelaide")
    TZ_NAME = "Adelaide time"
except Exception:  # no tz database: fall back to UTC weeks
    TZ = dt.timezone.utc
    TZ_NAME = "UTC"

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "analytics.json"
API = "https://api.cloudflare.com/client/v4/graphql"
HOSTS = ["gamsa.au", "www.gamsa.au"]
MIN_VIEWS = 3      # list entries below this are folded into "(other)"
TOP = 10           # entries kept per list
BACKFILL = 12      # weeks fetched when the file is new or has gaps (Web Analytics keeps about six months)
KEEP = 104         # weeks kept in the file
SAFE_PATH = re.compile(r"^/[A-Za-z0-9/_.\-]{0,80}$")
SAFE_HOST = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,79}$")
SAFE_COUNTRY = re.compile(r"^[A-Za-z][A-Za-z .'()\-]{0,59}$")

QUERY = """query ($account: string!) { viewer { accounts(filter: {accountTag: $account}) {
  total: rumPageloadEventsAdaptiveGroups(filter: %(f)s, limit: 1) { count sum { visits } }
  pages: rumPageloadEventsAdaptiveGroups(filter: %(f)s, limit: 50, orderBy: [count_DESC]) { count sum { visits } dimensions { requestPath } }
  referrers: rumPageloadEventsAdaptiveGroups(filter: %(f)s, limit: 50, orderBy: [count_DESC]) { count sum { visits } dimensions { refererHost } }
  countries: rumPageloadEventsAdaptiveGroups(filter: %(f)s, limit: 50, orderBy: [count_DESC]) { count sum { visits } dimensions { countryName } }
} } }"""


def iso(t):
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def week_bounds(monday):
    start = dt.datetime.combine(monday, dt.time(0), TZ)
    end = dt.datetime.combine(monday + dt.timedelta(days=7), dt.time(0), TZ)
    return start, end


def gql_filter(start, end, site_tag, bots):
    parts = ['{datetime_geq: "%s", datetime_lt: "%s"}' % (iso(start), iso(end))]
    if site_tag:
        parts.append('{siteTag: %s}' % json.dumps(site_tag))
    else:
        parts.append('{requestHost_in: %s}' % json.dumps(HOSTS))
    if not bots:
        parts.append('{bot: 0}')
    return "{AND: [%s]}" % ", ".join(parts)


def post(token, body):
    req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": "Bearer " + token, "Content-Type": "application/json", "User-Agent": "gamsa-analytics"})
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")[:300]
            if e.code >= 500 and attempt < 3:
                time.sleep(5 * attempt)
                continue
            raise RuntimeError("HTTP %s from the Cloudflare API: %s" % (e.code, text))
        except urllib.error.URLError as e:
            if attempt < 3:
                time.sleep(5 * attempt)
                continue
            raise RuntimeError("could not reach the Cloudflare API: %s" % e.reason)


def errors_of(resp):
    return [str(e.get("message", e)) for e in (resp.get("errors") or [])]


def fetch_week(token, account, monday, site_tag, state):
    """Return the raw account node for one week. state['bots'] becomes True if the bot filter is refused."""
    start, end = week_bounds(monday)
    while True:
        q = QUERY % {"f": gql_filter(start, end, site_tag, state["bots"])}
        resp = post(token, {"query": q, "variables": {"account": account}})
        errs = errors_of(resp)
        if errs and not state["bots"] and any("bot" in e.lower() for e in errs):
            print("NOTE the bot filter was refused; counting all page loads from now on")
            state["bots"] = True
            continue
        if errs:
            hint = ""
            if any(w in " ".join(errs).lower() for w in ("auth", "permission", "not authorized", "access")):
                hint = " (check the token has Account > Account Analytics > Read for this account)"
            raise RuntimeError("; ".join(errs)[:500] + hint)
        accounts = ((resp.get("data") or {}).get("viewer") or {}).get("accounts") or []
        if not accounts:
            raise RuntimeError("no account in the answer (check CLOUDFLARE_ACCOUNT_ID and the token's account)")
        return accounts[0], start, end


def num(row, visits=False):
    if visits:
        return int(((row or {}).get("sum") or {}).get("visits") or 0)
    return int((row or {}).get("count") or 0)


def top_list(rows, dim, key, ok, total_views, total_visits, rename=None):
    out = []
    for row in rows or []:
        name = ((row.get("dimensions") or {}).get(dim) or "").strip()
        if rename:
            name = rename(name)
        if len(out) < TOP and name and ok(name) and num(row) >= MIN_VIEWS:
            out.append({key: name, "views": num(row), "visits": num(row, True)})
    ov = total_views - sum(x["views"] for x in out)
    ovis = total_visits - sum(x["visits"] for x in out)
    if ov > 0 or ovis > 0:
        out.append({key: "(other)", "views": max(ov, 0), "visits": max(ovis, 0)})
    return out


def referrer_name(h):
    h = h.lower()
    if not h:
        return "(none or direct)"
    if h in HOSTS:
        return "(inside gamsa.au)"
    return h


def summarise(node, monday, start, end, bots_excluded=True):
    total = (node.get("total") or [{}])
    views, visits = num(total[0] if total else {}), num(total[0] if total else {}, True)
    ok_ref = lambda n: n.startswith("(") or bool(SAFE_HOST.match(n))
    return {
        "week": monday.isoformat(),
        "from": iso(start),
        "to": iso(end),
        "pageViews": views,
        "visits": visits,
        "botsExcluded": bots_excluded,
        "topPages": top_list(node.get("pages"), "requestPath", "path", lambda p: bool(SAFE_PATH.match(p)), views, visits),
        "topReferrers": top_list(node.get("referrers"), "refererHost", "host", ok_ref, views, visits, referrer_name),
        "topCountries": top_list(node.get("countries"), "countryName", "country", lambda c: bool(SAFE_COUNTRY.match(c)), views, visits),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--weeks", type=int, default=2)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    token = os.environ.get("CLOUDFLARE_ANALYTICS_TOKEN", "").strip()
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    missing = [n for n, v in (("CLOUDFLARE_ANALYTICS_TOKEN", token), ("CLOUDFLARE_ACCOUNT_ID", account)) if not v]
    if missing:
        print("Secret(s) %s not set, skipping. Nothing was written." % ", ".join(missing))
        return 0
    site_tag = os.environ.get("CLOUDFLARE_ANALYTICS_SITE_TAG", "").strip()

    try:
        old = json.loads(OUT.read_text()) if OUT.exists() else {}
    except ValueError:
        print("NOTE data/analytics.json was not valid JSON; starting a new file")
        old = {}
    weeks = {w["week"]: w for w in old.get("weeks", []) if isinstance(w, dict) and w.get("week")}

    today = dt.datetime.now(TZ).date()
    last = today - dt.timedelta(days=today.weekday() + 7)          # Monday of the last complete week
    wanted = [last - dt.timedelta(weeks=i) for i in range(BACKFILL)]
    todo = [m for i, m in enumerate(wanted) if i < max(args.weeks, 1) or m.isoformat() not in weeks]

    state = {"bots": False}
    fetched = 0
    for i, monday in enumerate(todo):                               # newest first
        try:
            node, start, end = fetch_week(token, account, monday, site_tag, state)
        except RuntimeError as e:
            if i == 0:
                print("FAIL week of %s: %s" % (monday, e))
                return 1
            print("NOTE stopped back-filling at the week of %s: %s" % (monday, e))
            break
        weeks[monday.isoformat()] = summarise(node, monday, start, end, not state["bots"])
        fetched += 1
        w = weeks[monday.isoformat()]
        print("PASS week of %s: %d page views, %d visits" % (monday, w["pageViews"], w["visits"]))

    data = {
        "about": "Weekly totals from Cloudflare Web Analytics for gamsa.au, newest week first. Estimates "
                 "(Cloudflare samples). Totals only: no IP addresses or visitor-level data; entries under "
                 "%d page views are folded into (other). Written by tools/analytics.py." % MIN_VIEWS,
        "site": site_tag and "site tag set by CLOUDFLARE_ANALYTICS_SITE_TAG" or " and ".join(HOSTS),
        "weekStarts": "Monday 00:00 " + TZ_NAME,
        "updated": iso(dt.datetime.now(dt.timezone.utc)),
        "weeks": sorted(weeks.values(), key=lambda w: w["week"], reverse=True)[:KEEP],
    }
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if args.dry_run:
        print(text)
    else:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text)
        print("Wrote %s (%d weeks fetched, %d kept)" % (OUT.relative_to(ROOT), fetched, len(data["weeks"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
