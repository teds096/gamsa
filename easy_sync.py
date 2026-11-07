#!/usr/bin/env python3
"""B-36 (v19.5, 7 Nov 2026): keeps the Easy Read guides in step with the pages they summarise.

Each guide in content/easyread.json lists what it summarises and a fingerprint of those parts from the day it was last
checked against them:
  "sources": ["content/costs.json",                                    whole file
              "content/administration.json#Taking tablets and capsules", one section (by its heading "h")
              "content/medicines.json#testosterone-gel",                 one medicine (by "id")
              "template.html#renderMeds"],                               one function in the page script
  "synced": {"date": "2026-11-07", "fp": {"content/costs.json": "1a2b3c4d5e6f", ...}}
build.py prints a WARN, and tools/site_check.py and tools/quick_check.py FAIL, naming the guide, when a source has
changed (or gone) since the guide was synced. Fingerprints ignore JSON layout and whitespace.

  python3 easy_sync.py                 list guides that are out of step (exit 1 if any)
  python3 easy_sync.py --sync ID ...   after updating or checking those guides, record today's fingerprints
  python3 easy_sync.py --sync --all    the same for every guide
"""
import datetime, hashlib, json, pathlib, re, sys

R = pathlib.Path(__file__).resolve().parent
EASY = R / "content/easyread.json"


def _js_function(text, name):
    i = text.find("function " + name + "(")
    if i < 0: return None
    j = text.find("{", i); depth = 0
    for k in range(j, len(text)):
        depth += {"{": 1, "}": -1}.get(text[k], 0)
        if depth == 0: return text[i:k + 1]
    return text[i:]


def _piece(src, cache):
    path, _, part = src.partition("#")
    f = R / path
    if not f.exists(): return None
    if path not in cache: cache[path] = f.read_text()
    raw = cache[path]
    if not path.endswith(".json"):
        got = _js_function(raw, part) if part else raw
        return None if got is None else re.sub(r"\s+", " ", got).strip()
    c = json.loads(raw)
    if part:
        hits = [s for key in ("sections", "medicines") for s in (c.get(key) or []) if isinstance(s, dict) and part in (s.get("h"), s.get("id"))]
        if hits: c = hits[0]
        elif isinstance(c, dict) and part in c: c = c[part]
        else: return None
    return json.dumps(c, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def fingerprint(src, cache=None):
    p = _piece(src, {} if cache is None else cache)
    return None if p is None else hashlib.sha256(p.encode()).hexdigest()[:12]


def stale(guides=None):
    """One message per out-of-step guide, e.g. 'costs (Paying for your medicine): content/costs.json changed since 2026-11-07'."""
    if guides is None: guides = json.loads(EASY.read_text())["guides"]
    cache, out = {}, []
    for g in guides:
        srcs, syn = g.get("sources") or [], (g.get("synced") or {})
        fp, when = syn.get("fp") or {}, syn.get("date", "never")
        if not srcs: out.append(f"{g['id']} ({g['title']}): no sources listed"); continue
        bad = []
        for s in srcs:
            now = fingerprint(s, cache)
            if now is None: bad.append(s + " is missing")
            elif fp.get(s) != now: bad.append(s + (" changed since " + when if s in fp else " never synced"))
        if bad: out.append(f"{g['id']} ({g['title']}): " + "; ".join(bad))
    return out


def sync(ids):
    d = json.loads(EASY.read_text()); cache, today, done = {}, datetime.date.today().isoformat(), []
    for g in d["guides"]:
        if ids != ["--all"] and g["id"] not in ids: continue
        fp = {s: fingerprint(s, cache) for s in g.get("sources") or []}
        miss = [s for s, v in fp.items() if v is None]
        if miss: sys.exit(f"{g['id']}: source not found: {', '.join(miss)}")
        g["synced"] = {"date": today, "fp": fp}; done.append(g["id"])
    unknown = [i for i in ids if i != "--all" and i not in done]
    if unknown: sys.exit("unknown guide id: " + ", ".join(unknown))
    EASY.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
    print("synced", today + ":", ", ".join(done))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--sync"]:
        if len(a) < 2: sys.exit("give guide ids or --all")
        sync(a[1:])
    else:
        msgs = stale()
        for m in msgs: print("OUT OF STEP", m)
        print(f"{len(msgs)} Easy Read guide(s) out of step" if msgs else "Easy Read guides in step")
        sys.exit(1 if msgs else 0)
