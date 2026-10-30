#!/usr/bin/env python3
"""Render template.html + data + content into index.html."""
import json, re, pathlib
R = pathlib.Path(__file__).parent
KEEP = ("id","genericName","brand","brands","form","strengthLabel","category","status","statusLabel","expectedReturn","sourceUrl")
meds = json.loads((R/"data/medicines.json").read_text())
payload = {"generatedAt": meds["generatedAt"],
           "medicines": [{k:m[k] for k in KEEP if k in m} for m in meds["medicines"]]}
content = {k: json.loads((R/f"content/{k}.json").read_text()) for k in ("dosing","administration","costs","easyread","pharmacy","clinicians","allies","resources","privacy","accessibility","disclaimer","addons","monitoring")}
medinfo = json.loads((R/"content/medicines.json").read_text())

# B-14 (24 Oct 2026): ONE list of dated changes, content/changes.json: [{"date","version","pages":[...],"text"}].
# It feeds the "Updated <date>: ..." note at the top of each page and the What's changed page (/changes).
# Entries other helpers drop in ../claude/changes-entries-*.json (same shape) are merged in and written back to
# content/changes.json, so the file shipped in the release holds everything. Same date + same words = one entry.
def _changes():
    f = R/"content/changes.json"
    cur = json.loads(f.read_text()) if f.exists() else []
    norm = lambda e: (e.get("date", ""), re.sub(r"\s+", " ", e.get("text", "")).strip().lower())
    out, seen = [], {}
    extra = sorted((R.parent/"claude").glob("changes-entries-*.json")) if (R.parent/"claude").is_dir() else []
    for src in [cur] + [json.loads(x.read_text()) for x in extra]:
        for e in (src if isinstance(src, list) else []):
            if not (isinstance(e, dict) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(e.get("date", ""))) and e.get("text")): continue
            k = norm(e)
            if k in seen:
                for p in e.get("pages", []):
                    if p not in seen[k]["pages"]: seen[k]["pages"].append(p)
                continue
            e = {"date": e["date"], "version": e.get("version", ""), "pages": list(e.get("pages", [])), "text": e["text"].strip()}
            seen[k] = e; out.append(e)
    out.sort(key=lambda e: e["date"], reverse=True)   # stable: same-day entries keep their order
    if out != cur:
        f.write_text("[\n" + ",\n".join(" " + json.dumps(e, ensure_ascii=False) for e in out) + "\n]\n")
    return out
content["changes"] = _changes()
# B-09 (24 Oct 2026): the About page, content/about.json {"title","intro":[...],"updated","sections":[{"h","paras","bullets"}]}.
# Optional: with no file (or a file that does not parse yet) the build skips /about and /about keeps redirecting to /disclaimer.
try: content["about"] = json.loads((R/"content/about.json").read_text())
except (FileNotFoundError, ValueError): pass
# B-20 (24 Oct 2026): "Sources and copyright" on the Disclaimer page, added here unless the page already has that section.
# No licence is named yet (Ted to choose). The footer line "© 2026 GAMSA" links to this section ({{COPYRIGHT_SEC}}).
_disc = content["disclaimer"]["sections"]
if not any(s.get("h") == "Sources and copyright" for s in _disc):
    _disc.append({"h": "Sources and copyright", "body": [
        "The words, pictures and figures on this site are © 2026 GAMSA, unless a page says otherwise.",
        "The Product Information (PI) and Consumer Medicine Information (CMI) for each medicine belong to the company that supplies that medicine in Australia (the sponsor). This site does not copy them: it puts what they say into plain words, and each medicine page links to the full documents.",
        "Prices, PBS listings and supply status come from the Pharmaceutical Benefits Scheme (PBS) and the Therapeutic Goods Administration (TGA), which are Australian Government (Commonwealth of Australia) sources. Each page names its sources, with the date they were checked, and links to them.",
        "To ask about using something from this site, [send feedback](#/feedback)."]})
COPYRIGHT_SEC = "sec-disclaimer-" + str(next(i for i, s in enumerate(_disc) if s.get("h") == "Sources and copyright"))
# /clinicians (and /allies) downloads: file type and size from the files themselves, e.g. "PDF, 182 KB" (24 Oct 2026)
def _files():
    out = {}
    for f in sorted((R/"static").glob("*/*")):
        if f.parent.name in ("clinicians", "allies") and f.suffix.lower() in (".pdf", ".zip"):
            n = f.stat().st_size
            size = f"{n/1e6:.1f} MB" if n >= 1e6 else f"{max(1, round(n/1e3))} KB"
            out[f"/{f.parent.name}/{f.name}"] = {"type": f.suffix[1:].upper(), "size": size}
    return out
FILES = _files()
CFG = json.loads((R/"site-config.json").read_text()) if (R/"site-config.json").exists() else {}
_tpl = (R/"template.html").read_text()
try:   # smaller pages when the minifiers are installed (pip install rjsmin rcssmin); fine without
    import rjsmin, rcssmin, re as _re
    _tpl = _re.sub(r"<style>(.*?)</style>", lambda m: "<style>" + rcssmin.cssmin(m.group(1)) + "</style>", _tpl, count=1, flags=_re.S)
    _tpl = _re.sub(r"<script>(.*?)</script>", lambda m: "<script>" + rjsmin.jsmin(m.group(1)) + "</script>", _tpl, count=1, flags=_re.S)
except ImportError:
    pass
_prem = json.loads((R/"data/premiums.json").read_text())
_dates = {"{{PBS_CHECKED}}": content["costs"].get("pbsFigures", {}).get("checkedAt", "recently"),
          "{{PREMIUMS_CHECKED}}": _prem.get("checkedAt", "recently"),
          "{{SUPPLY_CHECKED}}": meds["generatedAt"],
          "{{REVIEWED}}": medinfo.get("reviewed", "October 2026")}
_AUTO_REFS = [  # sources the scrapers fetch: their "Accessed" date is stamped with that check's date
    (re.compile(r"pbs\.gov\.au/(medicine/item/|browse/brand-premium)"), _dates["{{PREMIUMS_CHECKED}}"]),
    (re.compile(r"pbs\.gov\.au/healthpro/explanatory-notes/front/fee"), _dates["{{PBS_CHECKED}}"]),
    (re.compile(r"apps\.tga\.gov\.au/(shortages|prod/msi)|tga\.gov\.au/safety/shortages-and-supply-disruptions/medicine-shortages$"), _dates["{{SUPPLY_CHECKED}}"]),
]
_MONTHS = {"Jan":"January","Feb":"February","Mar":"March","Apr":"April","Jun":"June","Jul":"July","Aug":"August","Sep":"September","Oct":"October","Nov":"November","Dec":"December"}
def _longdate(d):
    p = d.split(); return " ".join(_MONTHS.get(x, x) for x in p)
def _stamp_refs(obj):
    if isinstance(obj, dict):
        url, text = obj.get("url", ""), obj.get("text", "")
        if url and isinstance(text, str) and "Accessed" in text:
            for rx, d in _AUTO_REFS:
                if rx.search(url):
                    obj["text"] = re.sub(r"Accessed [^.]*\.?$", "Accessed " + _longdate(d) + ".", text.strip()); break
        for v in obj.values(): _stamp_refs(v)
    elif isinstance(obj, list):
        for v in obj: _stamp_refs(v)
    return obj
def _tok(obj):
    s = json.dumps(obj, ensure_ascii=False)
    for k, v in _dates.items(): s = s.replace(k, v)
    return _stamp_refs(json.loads(s))
content = _tok(content); medinfo = _tok(medinfo)
import figures   # figure definitions in content/*.json -> HTML + inline SVG (page view + Easy Read view); see figures.py
def _premium_example(costs, prem):
    """B-11 (24 Oct 2026): figure F10 "What a brand premium adds" is drawn from the monthly PBS brand-premium data
    (data/premiums.json) and the PBS co-payment (content/costs.json pbsFigures), not fixed text. Example: one script
    (one pack) of spironolactone 25 mg if it carries a premium, else the first single-pack premium on the list; the
    no-premium bar is a benchmark brand without its own premium on that strength (as template.html premiumList() does).
    With no usable row the figure keeps its written example."""
    sec = next((x for x in costs.get("sections", []) if (x.get("figure") or {}).get("id") == "brand-premium"), None)
    rows = (prem or {}).get("rows", [])
    strength = lambda pr: re.sub(r",\s*\d+\s*$", "", pr or "")
    own = {}
    for r in rows: own.setdefault(strength(r.get("product")), set()).add(r.get("brand"))
    ok = [r for r in rows if r.get("packs") == "1" and r.get("premium")
          and [b for b in r.get("benchmark", []) if b not in own.get(strength(r.get("product")), ())]]
    if not sec or not ok:
        print("NOTE: brand-premium figure keeps its written example (no usable row in data/premiums.json)"); return
    r = next((x for x in ok if x["product"].startswith("spironolactone 25 mg")), ok[0])
    bench = [b for b in r["benchmark"] if b not in own[strength(r["product"])]][0]
    cp, pr = costs["pbsFigures"]["conc_copay"], "%.2f" % float(r["premium"])
    to = max(15, 5 * -(-(float(cp) + float(pr)) // 5))
    f = sec["figure"]
    f["sub"] = f"Example only: one script of {strength(r['product'])}, with a concession card (PBS list checked {prem.get('checkedAt', 'monthly')})"
    f["axis"]["to"] = int(to)
    f["long"] = (f"Two bars on one dollar scale from $0 to ${int(to)}. {bench}, a brand with no premium, costs the ${cp} co-payment. "
                 f"{r['brand']} costs the same co-payment plus a ${pr} brand premium, {{t2}} in all; the premium part is hatched.")
    f["rows"] = [
        {"label": bench + ":", "segs": [{"k": "bar", "v": "$" + cp}], "text": f"**${cp}**, the co-payment. No premium: it is a benchmark brand."},
        {"label": r["brand"] + ":", "segs": [{"k": "bar", "v": "$" + cp}, {"k": "acc", "v": "$" + pr}],
         "text": f"${cp} co-payment + **${pr}** brand premium = **{{total}}**."}]
_premium_example(content["costs"], _prem)
_FIGS = figures.render_content(content)
html = _tpl.replace("{{REVIEWED}}", _dates["{{REVIEWED}}"]).replace("__TURNSTILE_SITEKEY__", CFG.get("turnstileSiteKey", "")) \
    .replace("{{COPYRIGHT_SEC}}", COPYRIGHT_SEC).replace("__FILES__", json.dumps(FILES, separators=(",",":"))) \
    .replace("__MEDS__", json.dumps(payload, separators=(",",":"))) \
    .replace("__CONTENT__", json.dumps(content, separators=(",",":"))) \
    .replace("__MEDINFO__", json.dumps(medinfo, separators=(",",":"))) \
    .replace("__PREMIUMS__", json.dumps(json.loads((R/"data/premiums.json").read_text()), separators=(",",":")))
def _dl_sizes(x):
    """Static markup: <a href="/clinicians/x.pdf">Card (PDF, 1 page)</a> -> "Card (PDF, 1 page, 182 KB)".
    template.html fileLabel() does the same for the links the script draws."""
    def f(m):
        meta, t = FILES.get(m.group(2)), m.group(3)
        if not meta or meta["size"] in t: return m.group(0)
        p = re.search(r"\s*\(([^()]*)\)\s*$", t)
        if p and p.group(1).upper().startswith(meta["type"]):
            t = t[:p.start()] + f' <span class="dl-meta">({p.group(1)}, {meta["size"]})</span>'
        else:
            t += f' <span class="dl-meta">({meta["type"]}, {meta["size"]})</span>'
        return m.group(1) + t + "</a>"
    return re.sub(r'(<a [^>]*href="(/(?:clinicians|allies)/[^"#]+)"[^>]*>)([^<]*)</a>', f, x)
_m = re.search(r"<script>(.*?)</script>", html, re.S)
html = _dl_sizes(html[:_m.start()]) + _m.group(0) + _dl_sizes(html[_m.end():])
if "about" not in content: html = re.sub(r'\s*<li class="ft-about">.*?</li>', "", html)   # no about.json: no footer link
# artifact.html: fragment form, for publishing inside claude.ai (skeleton added there)
(R/"index.html").write_text(html)  # fragment: for previewing as a claude.ai artifact

# ---------------------------------------------------------------------------
# preview.html: one self-contained file using #/ routes, for viewing locally.
# dist/: the hosted site. One real HTML page per route (so search engines can
# index each page), sharing one cached script, plus sitemap, robots and headers.
# ---------------------------------------------------------------------------
import re, hashlib, html as H, shutil, datetime

SITE = "https://gamsa.au"
BASE_DESC = ("Independent, referenced information on gender-affirming medicines in South Australia: "
             "supply and shortages, PBS costs, doses and how to use each form.")
REVIEWED_ISO = datetime.datetime.strptime(medinfo.get("reviewed", "3 October 2026"), "%d %B %Y").date().isoformat()
AUTHOR = {"@type": "Person", "name": "Theodore South", "jobTitle": "Registered pharmacist",
          "hasCredential": "BPharm (Hons)"}
ORG = {"@type": "Organization", "name": "Gender-Affirming Medicines South Australia",
       "alternateName": "GAMSA", "url": SITE + "/", "logo": SITE + "/og-image.png"}

def head(title, desc, path, extra=""):
    url = SITE + path
    t, d = H.escape(title, quote=True), H.escape(desc, quote=True)
    _og = (R/"static/og"/((path.strip("/").replace("/", "-") or "home") + ".jpg"))
    og = f"{SITE}/og/{_og.name}" if _og.exists() else f"{SITE}/og-image.png"
    return ('<!doctype html>\n<html lang="en-AU" class="rb-b3"__ROUTING__>\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'<meta name="description" content="{d}">\n'
            '<meta name="theme-color" content="#0B5D7A" media="(prefers-color-scheme: light)">\n<meta name="theme-color" content="#0A2E3C" media="(prefers-color-scheme: dark)">\n'
            f'<link rel="canonical" href="{url}">\n'
            '<meta property="og:type" content="website">\n'
            '<meta property="og:site_name" content="GAMSA — Gender-Affirming Medicines South Australia">\n'
            f'<meta property="og:title" content="{t}">\n<meta property="og:description" content="{d}">\n'
            f'<meta property="og:url" content="{url}">\n<meta property="og:image" content="{og}">\n'
            '<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="630">\n'
            '<meta property="og:locale" content="en_AU">\n<meta name="twitter:card" content="summary_large_image">\n'
            + extra)

def shell(top, body_html):
    i = body_html.index("</style>") + len("</style>")
    return top + body_html[:i] + "\n</head>\n<body>\n" + body_html[i:] + "\n</body>\n</html>\n"

# 1. single-file preview (hash routes, inline script) -----------------------
_prev = re.sub(r'@font-face\{[^}]*\}', '', re.sub(r'<link rel="preload"[^>]*woff2[^>]*>\n?', '', html))  # file:// cannot load /fonts/; system fonts are fine locally
(R/"preview.html").write_text(shell(head("Gender-Affirming Medicines South Australia", BASE_DESC, "/").replace("__ROUTING__", ""), _prev))

# 2. hosted site ------------------------------------------------------------
D = R/"dist"
if D.exists(): shutil.rmtree(D)
D.mkdir(parents=True)
# B-15 (24 Oct 2026): the site script (code, guides, every medicine) is one file, /js/app.<hash>.js, shared by every page and
# cached for a year (_headers below); a new build gives it a new name, so nobody gets an old copy. Each page keeps only its
# own HTML and stylesheet, plus its own words in a <noscript> block (search engines and readers without JavaScript).
# Measured before the change (claude/perf-plan-2026-10-24.md): every page carried the whole 199 KB (gzip) script inline,
# so each new page cost about 238 KB; now a page is about 40-60 KB and the script downloads once.
script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
import base64
APP = "js/app." + hashlib.sha256(script.encode()).hexdigest()[:12] + ".js"
_th = re.search(r'<script id="th">(.*?)</script>', html, re.S).group(1)
SCRIPT_HASH = "'sha256-" + base64.b64encode(hashlib.sha256(_th.encode()).digest()).decode() + "'"   # the only inline script left
# rewrite #/ links in the static markup only (the script fixes the links it draws itself)
_pre, _post = html.split("<script>" + script + "</script>")
def _paths(x):
    x = x.replace('href="#/med/', 'href="/medicines/').replace('href="#/"', 'href="/"')
    return re.sub(r'href="#(/[a-z0-9-]+)(#[a-z0-9-]+)?"', r'href="\1\2"', x)
page = _paths(_pre) + f'<script src="/{APP}"></script>' + _paths(_post)
(D/"js").mkdir(); (D/APP).write_text(script)
page = re.sub(r'(<title>)[^<]*(</title>)', r'\1__TITLE__\2', page, count=1)
PRELOAD = f'<link rel="preload" href="/{APP}" as="script">\n'   # starts the script download before the stylesheet is read

def sentence(t, n=158):
    t = re.sub(r"\s*\[\d+\]", "", re.sub(r"<[^>]+>", "", t)).strip()
    if len(t) <= n: return t
    cut = t[:n].rsplit(" ", 1)[0].rstrip(",;:—- ")
    return cut + "…"

# B-28 (23 Oct 2026): every title and meta description says what the site is and where. Titles keep the page or
# medicine name first and stay within 60 characters where they can; template.html fullTitle() is the same rule for
# in-app navigation, so the title does not change once the script runs.
def full_title(name):
    if "South Australia" in name: return "GAMSA \u00b7 " + name
    for t in (name + " \u00b7 Gender-affirming medicines, South Australia \u00b7 GAMSA",
              name + " \u00b7 Gender-affirming medicines SA \u00b7 GAMSA",
              name + " \u00b7 GAMSA, South Australia"):
        if len(t) <= 60: return t
    return name + " \u00b7 GAMSA"

WHERE = "GAMSA (Gender-Affirming Medicines South Australia): "
def where_desc(d, n=158):
    if "gender-affirming" in d.lower() and "south australia" in d.lower(): return d
    return WHERE + sentence(d, n - len(WHERE))

VIEWDESC = {
 "/": BASE_DESC,
 "/supply": "Which gender-affirming hormone medicines are in short supply in Australia right now, checked daily against TGA records, and what to do about it.",
 "/medicines": "Every medicine used in gender-affirming hormone therapy in Australia, with a page for each: how it is used, cost, monitoring and current supply.",
 "/sightings": "Reports from the public of gender-affirming medicines seen in stock at South Australian pharmacies.",
 "/pharmacy-reports": "Stock reports for gender-affirming medicines posted by registered pharmacists.",
 "/feedback": "Report a mistake, something missing or an accessibility problem on GAMSA.",
 "/search": "Search every page, medicine and Easy Read guide on GAMSA. The search runs in your browser.",
 "/alerts": "Gender-affirming medicines under a current TGA shortage notice, with an RSS feed for prescribers and pharmacists.",
 "/trans": "Gender-affirming medicines in plain language for trans and gender diverse South Australians: supply, costs, doses, how to use each one, and your pharmacy.",
 "/clinicians": "For prescribers, nurses and pharmacists: an injection training package, pharmacist stock register, monitoring schedule and PBS Authority wording card.",
 "/allies": "GAMSA for family, friends and allies of trans and gender diverse people: what the medicines are, what goes wrong, and how to help at the pharmacy.",
 "/easy": "Easy Read guides to gender-affirming hormone medicines: getting your medicine, shortages, costs, doses and using it safely, in short sentences with pictures.",
 "/changes": "Dated changes to the information on GAMSA, newest first: doses, costs, supply, safety points and downloads for gender-affirming medicines in South Australia.",
}
CVIEW = {"/doses": "dosing", "/using": "administration", "/costs": "costs", "/pharmacy": "pharmacy", "/clinician-guide": "clinicians", "/ally-guide": "allies", "/resources": "resources", "/add-on-therapies": "addons", "/monitoring": "monitoring", "/privacy": "privacy", "/accessibility": "accessibility", "/disclaimer": "disclaimer", "/about": "about"}
TITLES = {"/": "Gender-Affirming Medicines South Australia", "/supply": "Supply & shortages",
          "/medicines": "Medicines A–Z", "/sightings": "Patient sightings", "/easy": "Easy Read guides",
          "/doses": "Medicines, doses and formulations", "/monitoring": "Monitoring and related care", "/add-on-therapies": "Add-on therapies", "/using": "How to use your medicine",
          "/pharmacy": "Working with your pharmacy", "/costs": "Costs and the PBS", "/feedback": "Send feedback", "/pharmacy-reports": "Pharmacy stock reports",
          "/trans": "Trans and gender diverse people", "/clinicians": "Clinicians and pharmacists", "/allies": "Family, friends and allies",
          "/clinician-guide": "For clinicians and pharmacists", "/ally-guide": "For family, friends and allies", "/resources": "Resources", "/alerts": "Shortage alerts", "/changes": "What’s changed", "/privacy": "Privacy", "/accessibility": "Accessibility", "/disclaimer": "Disclaimer", "/search": "Search"}
if "about" in content: TITLES["/about"] = content["about"].get("title") or "About GAMSA"   # B-09: only with content/about.json
VIEWID = {"/": "v-home", "/supply": "v-supply", "/medicines": "v-medicines", "/sightings": "v-sightings",
          "/easy": "v-easy", "/doses": "v-doses", "/monitoring": "v-monitoring", "/add-on-therapies": "v-add-on-therapies", "/using": "v-using", "/pharmacy": "v-pharmacy",
          "/costs": "v-costs", "/feedback": "v-feedback", "/pharmacy-reports": "v-pharmacy-reports",
          "/trans": "v-trans", "/clinicians": "v-clinicians", "/allies": "v-allies", "/clinician-guide": "v-clinician-guide", "/ally-guide": "v-ally-guide", "/resources": "v-resources", "/alerts": "v-alerts", "/changes": "v-changes", "/about": "v-about", "/privacy": "v-privacy", "/accessibility": "v-accessibility", "/disclaimer": "v-disclaimer", "/search": "v-search"}

def ld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False).replace("</", "<\\/") + "</script>\n"

# B-15: each page's own words as plain HTML in a <noscript> block inside its view, for search engines and readers without
# JavaScript (with JavaScript on, browsers ignore it and the script draws the full page as before).
_hp = lambda h: ("/medicines/" + h[6:] if h.startswith("#/med/") else h[1:]) if h.startswith("#/") else h   # "#/med/x" -> "/medicines/x"
def _md(t):
    s = H.escape(re.sub(r"\s*\[\d+(?:[,\s]*\d+)*\]", "", str(t)))
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    def a(m):
        u = m.group(2)
        u = _hp(u)
        return f'<a href="{u}">{m.group(1)}</a>'
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", a, s)
def _nj_secs(secs):
    o = ""
    for s in secs:
        o += f"<h2>{H.escape(s.get('h', ''))}</h2>"
        o += "".join(f"<p>{_md(b)}</p>" for b in (s.get("body") or s.get("paras") or []) if isinstance(b, str))
        li = s.get("list") or s.get("bullets") or []
        if li: o += "<ul>" + "".join(f"<li>{_md(x)}</li>" for x in li if isinstance(x, str)) + "</ul>"
        tb = s.get("table")
        if tb: o += ("<table><tr>" + "".join(f"<th>{_md(h)}</th>" for h in tb["head"]) + "</tr>" +
                     "".join("<tr>" + "".join(f"<td>{_md(c)}</td>" for c in r) + "</tr>" for r in tb["rows"]) + "</table>")
        if (s.get("fig") or {}).get("cap"): o += f"<p>{_md(s['fig']['cap'])}</p>"
        if s.get("note"): o += f"<p>{_md(s['note'])}</p>"
    return o
def _nj_refs(refs):
    if not refs: return ""
    return "<h2>References</h2><ol>" + "".join(f"<li>{_md(r.get('text', ''))}" + (f' <a href="{H.escape(r["url"])}">{H.escape(r["url"])}</a>' if r.get("url") else "") + "</li>" for r in refs) + "</ol>"
def _nj_content(c):
    intro = c.get("intro", "")
    return (f"<h1>{H.escape(c.get('title', ''))}</h1>" + "".join(f"<p>{_md(p)}</p>" for p in (intro if isinstance(intro, list) else [intro])) +
            _nj_secs(c.get("sections", [])) + _nj_refs(c.get("references", [])) +
            (f"<p>Last reviewed {datetime.date.fromisoformat(c['updated']).strftime('%-d %B %Y')}.</p>" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(c.get("updated", ""))) else ""))
def _nj_med(m):
    return (f"<h1>{H.escape(m['name'])}</h1><p>{_md(m.get('summary', ''))}</p>" + _nj_secs(m.get("sections", [])) +
            ("<h2>Links and resources</h2><ul>" + "".join(f'<li><a href="{H.escape(l["url"])}">{H.escape(l["label"])}</a></li>' for l in m["links"]) + "</ul>" if m.get("links") else "") +
            _nj_refs(m.get("references", [])))
def _nj_easy(g):
    o = f"<h1>{H.escape(g['title'])}</h1><p>{H.escape(g.get('subtitle', ''))}</p>"
    for sec in g.get("sections", []):
        o += f"<h2>{H.escape(sec.get('h', ''))}</h2>"
        for b in sec.get("blocks", []):
            ul = False
            for l in b.get("lines", []):
                x = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", H.escape(l[2:] if l.startswith("- ") else l))
                if l.startswith("- ") and not ul: o += "<ul>"; ul = True
                if not l.startswith("- ") and ul: o += "</ul>"; ul = False
                o += f"<li>{x}</li>" if l.startswith("- ") else f"<p>{x}</p>"
            if ul: o += "</ul>"
    return o
def _nj_hubs():
    src, out = (R/"template.html").read_text(), {}
    u = lambda s: json.loads('"' + s + '"')
    for k, kick, tit, lede, items in re.findall(r'(trans|clinicians|allies): \{kicker:"([^"]*)", title:"([^"]*)", lede:"([^"]*)",\s*items:\[(.*?)\]\}', src, re.S):
        li = "".join(f'<li><a href="{_hp(h)}">{H.escape(u(t))}</a>: {H.escape(u(d))}</li>'
                     for t, h, d in re.findall(r'\{t:"([^"]*)", h:"([^"]*)", d:"([^"]*)"', items))
        out["/" + k] = f"<h1>{H.escape(u(tit))}</h1><p>{H.escape(u(lede))}</p><ul>{li}</ul>"
    return out
def _nj_changes(L):
    days, o = {}, "<h1>What’s changed</h1><p>Dated changes to the information on this site, newest first.</p>"
    for e in L: days.setdefault(e["date"], []).append(e)
    for d, es in days.items():
        o += f"<h2>{datetime.date.fromisoformat(d).strftime('%-d %B %Y')}</h2><ul>" + "".join(
            "<li>" + H.escape(e["text"]) + ("" if not e["pages"] else " (" + ", ".join(f'<a href="{H.escape(p)}">{H.escape(p)}</a>' for p in e["pages"]) + ")") + "</li>" for e in es) + "</ul>"
    return o
NOJS = {p: _nj_content(content[k]) for p, k in CVIEW.items() if k in content}
NOJS.update(_nj_hubs())
NOJS["/changes"] = _nj_changes(content["changes"])
NOJS["/easy"] = (f"<h1>{H.escape(content['easyread'].get('title', 'Easy Read guides'))}</h1><ul>" +
                 "".join(f'<li><a href="/easy/{g["id"]}">{H.escape(g["title"])}</a>: {H.escape(g.get("subtitle", ""))}</li>' for g in content["easyread"]["guides"]) + "</ul>")
NOJS["/medicines"] = ("<h1>Medicines A–Z</h1><ul>" + "".join(f'<li><a href="/medicines/{m["id"]}">{H.escape(m["name"])}</a>: {_md(sentence(m.get("summary", "")))}</li>'
                      for m in sorted(medinfo["medicines"], key=lambda m: m["name"].lower())) + "</ul>")
NOJS["/alerts"] = ("<h1>Shortage alerts</h1><p>Medicines under a current TGA shortage notice, checked " + H.escape(str(meds.get("generatedAt", ""))) +
                   '. Feed: <a href="/feed.xml">gamsa.au/feed.xml</a>.</p><ul>' + "".join(f'<li>{H.escape(r.get("brand", ""))} {H.escape(r.get("strengthLabel", ""))}: {H.escape(r.get("statusLabel") or str(r.get("status")))}</li>'
                   for r in meds["medicines"] if r.get("status") not in (None, "in_supply", "unverified")) + "</ul>")

def write(path, title, desc, view, schema, noindex=False, nojs=None):
    full = full_title(title)   # home too: the same title the app sets after in-app navigation (B-28, 23 Oct 2026)
    extra = ld(schema) + ('<meta name="robots" content="noindex">\n' if noindex else "")
    top = head(full, desc, path, PRELOAD + extra).replace("__ROUTING__", ' data-routing="path"')
    nj = NOJS.get(path) if nojs is None else nojs
    body = page.replace("__TITLE__", H.escape(full), 1) \
               .replace(f'<div class="view" id="{view}">', f'<div class="view on" id="{view}">' + (f"<noscript>{_dl_sizes(nj)}</noscript>" if nj else ""), 1)
    # Cloudflare Pages serves /costs from costs.html (and /costs/ needs a redirect if it were a folder)
    out = D/"index.html" if path == "/" else D/(path.strip("/") + ".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(shell(top, body))

urls = []
for path, title in TITLES.items():
    _in = content[CVIEW[path]]["intro"] if path in CVIEW else ""
    desc = where_desc(VIEWDESC.get(path) or sentence(" ".join(_in) if isinstance(_in, list) else _in))
    if path == "/":
        schema = {"@context": "https://schema.org", "@graph": [ORG,
                  {"@type": "WebSite", "name": ORG["name"], "url": SITE + "/", "inLanguage": "en-AU",
                   "publisher": {"@id": SITE + "/#org"}}]}
        schema["@graph"][0]["@id"] = SITE + "/#org"
    else:
        schema = {"@context": "https://schema.org", "@type": "MedicalWebPage", "name": title,
                  "url": SITE + path, "description": desc, "inLanguage": "en-AU",
                  "author": AUTHOR, "publisher": ORG}
    write(path, title, desc, VIEWID[path], schema, noindex=(path == "/search"))
    if path != "/search": urls.append(path)   # /sightings and /feedback indexed too (v18.1.1, Ted 15 Oct); /search stays noindex

for m in medinfo["medicines"]:
    path = "/medicines/" + m["id"]
    short = m["name"].split(" (")[0]
    title = short   # B-28: the site and place now follow the name (full_title), in place of ": doses, cost and supply"
    desc = where_desc(sentence(m.get("summary", "")))
    page_ld = {"@type": "MedicalWebPage", "name": m["name"],
              "url": SITE + path, "description": desc, "inLanguage": "en-AU",
              "about": {"@type": "Substance", "name": m["name"], "activeIngredient": m["generic"]},   # B-16: not "Drug" (a Product type: Google then wants offers/reviews)
              "author": AUTHOR, "reviewedBy": AUTHOR, "publisher": ORG,
              "lastReviewed": datetime.datetime.strptime(m["reviewed"], "%d %B %Y").date().isoformat() if m.get("reviewed") else REVIEWED_ISO}   # per-page review date when the page has one
    nm = short[0].lower() + short[1:] if short.split()[0].lower() in m["generic"].lower() else short
    pl = short.split()[-1].endswith("s") and not short.endswith("ss")
    qa = [(f"What {'are' if pl else 'is'} {nm}?", "What it is"),
          (f"How {'are' if pl else 'is'} {nm} used?", "How it is used"),
          (f"How much {'do' if pl else 'does'} {nm} cost on the PBS?", "Cost and PBS"),
          (f"How should {nm} be stored?", "Storage and disposal")]
    faq = []
    for q, h in qa:
        sec = next((x for x in m["sections"] if x.get("h") == h), None)
        txt = " ".join(b for b in (sec or {}).get("body", []) if isinstance(b, str))[:900]
        txt = re.sub(r"\s*\[\d+(?:[,\s]*\d+)*\]", "", re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", txt)).strip()
        if txt: faq.append({"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": txt}})
    schema = {"@context": "https://schema.org", "@graph": [page_ld] + ([{"@type": "FAQPage", "mainEntity": faq}] if faq else [])}
    write(path, title, desc, "v-med", schema, nojs=_nj_med(m))
    urls.append(path)

for g in content["easyread"]["guides"]:
    path = "/easy/" + g["id"]
    desc = where_desc(g["title"] + " — " + g["subtitle"] + ". An Easy Read guide in short sentences with pictures.")
    write(path, g["title"] + " (Easy Read)", desc, "v-easy-guide",
          {"@context": "https://schema.org", "@type": "MedicalWebPage", "name": g["title"] + " (Easy Read)",
           "url": SITE + path, "description": desc, "inLanguage": "en-AU", "author": AUTHOR, "publisher": ORG}, nojs=_nj_easy(g))
    urls.append(path)

# unknown paths: the home page, marked noindex
write("/", TITLES["/"], BASE_DESC, "v-home", {"@context": "https://schema.org", "@type": "WebPage"}, noindex=True)
shutil.move(D/"index.html", D/"404.html")
write("/", TITLES["/"], BASE_DESC, "v-home",
      {"@context": "https://schema.org", "@graph": [dict(ORG, **{"@id": SITE + "/#org"}),
       {"@type": "WebSite", "name": ORG["name"], "url": SITE + "/", "inLanguage": "en-AU",
        "publisher": {"@id": SITE + "/#org"}}]})

today = datetime.date.today().isoformat()
(D/"sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    "".join(f"  <url><loc>{SITE}{u}</loc><lastmod>{today}</lastmod></url>\n" for u in urls) + "</urlset>\n")
def _rss():
    import email.utils, datetime
    items = []
    for r in meds["medicines"]:
        if r.get("status") in (None, "in_supply", "unverified"): continue
        name = r.get("brand", "") + (" (" + r["strengthLabel"] + ")" if r.get("strengthLabel") else "")
        st = r.get("statusLabel") or str(r.get("status")).replace("_", " ").title()
        d = r.get("lastVerified") or meds.get("generatedAt", "")
        try: dt = datetime.datetime.fromisoformat(str(d)[:10]).replace(tzinfo=datetime.timezone.utc)
        except Exception: dt = datetime.datetime.now(datetime.timezone.utc)
        link = SITE + "/supply"
        items.append("<item><title>" + H.escape(f"{st}: {name}") + "</title><link>" + link + "</link><guid isPermaLink=\"false\">" + H.escape(f"gamsa-{r.get('id', name)}-{r.get('status')}") + "</guid><pubDate>" + email.utils.format_datetime(dt) + "</pubDate><description>" + H.escape((r.get("note") or st) + (" Not returning" if "not returning" in str(r.get("expectedReturn", "")).lower() else " Expected return: " + str(r.get("expectedReturn", "—"))) + ". TGA status as checked " + str(meds.get("generatedAt", "")) + ".") + "</description></item>")
    (D/"feed.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>GAMSA shortage alerts</title><link>' + SITE + '/supply</link><description>Gender-affirming medicines in Australia under a current TGA shortage notice. Rebuilt daily.</description><language>en-au</language>' + "".join(items) + "</channel></rss>\n")
_rss()
(D/"robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n")
if (R/"static").exists():
    shutil.copytree(R/"static", D, dirs_exist_ok=True)
if "/about" in TITLES and (D/"_redirects").exists():   # B-09: the About page takes over /about (static/_redirects sends it to /disclaimer otherwise)
    (D/"_redirects").write_text("".join(l for l in (D/"_redirects").read_text().splitlines(True) if l.split()[:1] != ["/about"]))

# v19 security (24 Oct 2026). Browsers report anything this policy blocks to /api/csp-report (functions/api/csp-report.js);
# Ted reads the totals on /admin -> "Blocked-content reports". 'unsafe-inline' stays in style-src because the pages and
# their script use many style="" attributes. The Report-Only trial checks whether the <style> blocks could be locked to
# this build's own hashes (style="" attributes still allowed): if /admin shows no "style-src-elem" lines for a few weeks,
# that rule can be moved into the enforced policy.
CSP_BASE = [
    "default-src 'self'",
    "script-src 'self' " + SCRIPT_HASH + " https://static.cloudflareinsights.com https://challenges.cloudflare.com",
    "frame-src https://challenges.cloudflare.com",
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self'",
    "img-src 'self' data:",
    "connect-src 'self' https://cloudflareinsights.com",
    "frame-ancestors 'none'", "base-uri 'self'", "form-action 'self'", "object-src 'none'",
    "upgrade-insecure-requests",
]
CSP_REPORT = ["report-uri /api/csp-report"]   # report-uri: sent at once by Chrome, Safari and Firefox (report-to was not delivered in tests)
_STYLE_HASHES = sorted({"'sha256-" + base64.b64encode(hashlib.sha256(_s.encode()).digest()).decode() + "'"
                        for _f in D.rglob("*.html") for _s in re.findall(r"<style[^>]*>(.*?)</style>", _f.read_text(), re.S)})
csp = "; ".join(CSP_BASE + CSP_REPORT)
csp_trial = "; ".join([d for d in CSP_BASE if d != "upgrade-insecure-requests"] +   # not allowed in a Report-Only policy
                      ["style-src-elem 'self' " + " ".join(_STYLE_HASHES), "style-src-attr 'unsafe-inline'"] + CSP_REPORT)
(D/"_headers").write_text("\n".join([
    "/*",
    "  Content-Security-Policy: " + csp,
    "  Content-Security-Policy-Report-Only: " + csp_trial,
    "  Strict-Transport-Security: max-age=31536000; includeSubDomains",
    "  X-Content-Type-Options: nosniff",
    "  X-Frame-Options: DENY",
    "  Referrer-Policy: strict-origin-when-cross-origin",
    "  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "  Cross-Origin-Opener-Policy: same-origin",
    # B-15 (24 Oct 2026): the site script has its content hash in its name, so it can be cached for a year and never revalidated;
    # the fonts keep their names, so they get a year without "immutable" (a reload still checks them)
    "/js/*",
    "  Cache-Control: public, max-age=31536000, immutable",
    "/fonts/*",
    "  Cache-Control: public, max-age=31536000",
    "",
]))
n = sum(1 for _ in D.rglob("*.html")) - 1
print(f"Built dist/: {n} pages, sitemap with {len(urls)} URLs, {len(_FIGS)} figures; preview.html for local viewing")
