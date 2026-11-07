"""B-34 (v19.5, 7 Nov 2026): blood-test monitoring from ONE file, content/monitoring-levels.json.

apply(monitoring, medinfo, levels) is called by build.py (and by tools/site_check.py before its reference check):
- /monitoring: every section with "levels": "<group id>" gets a table (Test | When | Aim | Talk to your prescriber if),
  a "clin" list (shown under "For clinicians") and reference numbers. "{{SRC:ID}}" in any /monitoring text becomes "[n]".
- each medicine page named in a group's "pages" gets m["bloodTests"] (the short "Blood tests" box drawn by template.html
  at the top of "What is monitored"); content/medicines.json itself is never written.
Reference numbers are never typed: a source reuses a page reference with the same URL (and all of its "match" words, if
given), otherwise its own text is added at the end of that page's reference list.
"""
import json, re

HEAD = ["Test", "When", "Aim", "Talk to your prescriber if"]


def _ref(page, src):
    refs = page.setdefault("references", [])
    for r in refs:
        if r.get("url") == src["url"] and all(w in r.get("text", "") for w in src.get("match", [])):
            return r["n"]
    n = max([r["n"] for r in refs] or [0]) + 1
    refs.append({"n": n, "text": src["text"], "url": src["url"]})
    return n


def _cites(page, L, ids):
    out, seen = "", set()
    for i in ids:
        n = _ref(page, L["sources"][i])
        if n not in seen: seen.add(n); out += f"[{n}]"
    return " " + out if out else ""


def _aim(page, L, row):
    if row["aim"].strip() in ("", "—"): return "—"
    t = row["aim"].rstrip(".") + _cites(page, L, [s["id"] for s in row.get("sources", [])]) + "."
    for o in row.get("other", []):
        t += f" Other guidance ({L['sources'][o['src']]['name']}): {o['text']}" + _cites(page, L, [o["src"]]) + "."
    return t


def _clin(page, L, row):
    locs = "; ".join(f"{L['sources'][s['id']]['name']} {s['loc']}" + _cites(page, L, [s["id"]]) for s in row.get("sources", []))
    return {"t": row["test"], "x": row["clinician"].rstrip(".") + "." + (f" ({locs})" if locs else "")}


def _rows_for(group, forms):
    for r in group["rows"]:
        if "all" in forms or not r.get("forms") or set(r["forms"]) & set(forms):
            yield r


def sheet_card(sh):
    """Download card for one sheet's printable (dlCards shape; pages and size are added at build time)."""
    return {"t": "Blood test guide: " + sh["t"], "u": sh["file"],
            "d": "Tests, timing and aims, to print and take to your appointment."}


def reading_points(monitoring, levels, sh):
    """v19.5 R3 (Ted, 7 Nov 2026): the points of the general "Reading your results" section (content/monitoring.json) that
    apply to one sheet, in the same words and with the same reference marks; "units" keeps its first sentence only."""
    keys = sh.get("reading") or []
    if not keys: return None
    gen = next((s for s in monitoring["sections"] if s.get("h") == "Reading your results"), None)
    if gen is None: raise SystemExit("FAIL: content/monitoring.json has no 'Reading your results' section (monitoring-levels.json sheets name its points)")
    body, lst = list(gen.get("body", [])), list(gen.get("list", []))
    pool = body + lst
    out = {"points": [], "listh": gen.get("listh", ""), "wrong": []}
    for k in keys:
        start = levels["reading"].get(k)
        hit = [t for t in pool if start and t.startswith(start)]
        if len(hit) != 1: raise SystemExit(f"FAIL: monitoring-levels.json sheet {sh['id']} reading point '{k}' matches {len(hit)} lines of 'Reading your results'")
        t = hit[0]
        if k == "units": t = t.split(". ", 1)[0].rstrip(".") + "."
        out["points" if hit[0] in body else "wrong"].append(t.rstrip(".") + ".")
    return out


def apply(monitoring, medinfo, levels):
    """v19.5 R2: a /monitoring section with "levels": <sheet id> shows that sheet's rows (its group, its forms) and the
    sheet's download card; "levels": <group id> (no sheet of that id) still shows the whole group."""
    L, G = levels, {g["id"]: g for g in levels["groups"]}
    SH = {s["id"]: s for s in levels.get("sheets", [])}
    secidx = {}
    for i, s in enumerate(monitoring["sections"]):
        key = s.get("levels")
        if not key: continue
        sh = SH.get(key)
        gid, forms = (sh["group"], sh["forms"]) if sh else (key, ["all"])
        if gid not in G: raise SystemExit(f"FAIL: content/monitoring.json section {i} names levels '{key}', not a sheet or group in monitoring-levels.json")
        g = G[gid]; secidx[key] = i
        rows = list(_rows_for(g, forms))
        for r in rows:
            if not r.get("sources"): raise SystemExit(f"FAIL: monitoring-levels.json row {r['id']} has no source")
        s["table"] = {"head": HEAD, "stack": True,
                      "rows": [[r["test"], r["when"], _aim(monitoring, L, r), r["talkIf"]] for r in rows]}
        s["clin"] = [_clin(monitoring, L, r) for r in rows if r.get("clinician")]
        if sh and sh.get("file"): s["downloads"] = [sheet_card(sh)]
        if sh and sh.get("reading"): s["read"] = reading_points(monitoring, L, sh)
    # {{SRC:ID}} in the page's own words -> [n]
    rx = re.compile(r"\{\{SRC:([A-Z0-9-]+)\}\}")
    def sub(o):
        if isinstance(o, str): return rx.sub(lambda m: f"[{_ref(monitoring, L['sources'][m.group(1)])}]", o)
        if isinstance(o, list): return [sub(x) for x in o]
        if isinstance(o, dict): return {k: (sub(v) if k != "references" else v) for k, v in o.items()}
        return o
    monitoring.update(sub({k: v for k, v in monitoring.items() if k != "references"}))
    # medicine pages: the box shows every row of the medicine's sheet (the same tests as /monitoring) and its printable
    by = {m["id"]: m for m in medinfo["medicines"]}
    for sh in SH.values():
        g = G[sh["group"]]
        for mid in sh.get("pages", []):
            m = by.get(mid)
            if not m and not by: continue   # site_check: /monitoring only
            if not m: raise SystemExit(f"FAIL: monitoring-levels.json sheet {sh['id']} names medicine page '{mid}', not in content/medicines.json")
            if mid in [x for o in SH.values() if o is not sh for x in o.get("pages", [])]: raise SystemExit(f"FAIL: medicine page '{mid}' is in two sheets")
            m["bloodTests"] = {"title": sh["h"],
                               "href": "#/monitoring#sec-monitoring-" + str(secidx[sh["id"]]) if sh["id"] in secidx else "#/monitoring",
                               "dl": [sheet_card(sh)] if sh.get("file") else [],
                               "rows": [{"t": r["test"], "w": r["when"],
                                         "a": "" if r["aim"].strip() in ("", "\u2014") else r["aim"].rstrip(".") + _cites(m, L, [s["id"] for s in r.get("sources", [])][:2]) + "."}
                                        for r in _rows_for(g, sh["forms"])]}
    return monitoring, medinfo


def printable_rows(levels):
    """Rows for the blood-test record printable: (test, when, aim) from each printable row's 'short' line ("Test: when; aim")."""
    out = []
    for g in levels["groups"]:
        for r in g["rows"]:
            if r.get("printable") and r.get("short"):
                name, rest = r["short"].split(":", 1)
                when, aim = [x.strip() for x in rest.split(";", 1)]
                out.append((name.strip(), when[0].upper() + when[1:], aim[0].upper() + aim[1:]))
    return out


if __name__ == "__main__":
    import pathlib
    R = pathlib.Path(__file__).parent
    mon = json.loads((R / "content/monitoring.json").read_text()); med = json.loads((R / "content/medicines.json").read_text())
    apply(mon, med, json.loads((R / "content/monitoring-levels.json").read_text()))
    print(json.dumps([s.get("table") for s in mon["sections"] if s.get("levels")][:1], indent=1, ensure_ascii=False)[:1500])
