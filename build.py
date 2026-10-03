#!/usr/bin/env python3
"""Render template.html + data + content into index.html."""
import json, re, pathlib
R = pathlib.Path(__file__).parent
KEEP = ("id","genericName","brand","brands","form","strengthLabel","category","status","statusLabel","expectedReturn","sourceUrl")
meds = json.loads((R/"data/medicines.json").read_text())
payload = {"generatedAt": meds["generatedAt"],
           "medicines": [{k:m[k] for k in KEEP if k in m} for m in meds["medicines"]]}
content = {k: json.loads((R/f"content/{k}.json").read_text()) for k in ("dosing","administration","costs","easyread","pharmacy","clinicians","allies","resources","privacy","accessibility","disclaimer")}
medinfo = json.loads((R/"content/medicines.json").read_text())
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
html = _tpl.replace("{{REVIEWED}}", _dates["{{REVIEWED}}"]).replace("__TURNSTILE_SITEKEY__", CFG.get("turnstileSiteKey", "")) \
    .replace("__MEDS__", json.dumps(payload, separators=(",",":"))) \
    .replace("__CONTENT__", json.dumps(content, separators=(",",":"))) \
    .replace("__MEDINFO__", json.dumps(medinfo, separators=(",",":"))) \
    .replace("__PREMIUMS__", json.dumps(json.loads((R/"data/premiums.json").read_text()), separators=(",",":")))
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
    return ('<!doctype html>\n<html lang="en-AU"__ROUTING__>\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'<meta name="description" content="{d}">\n'
            '<meta name="theme-color" content="#0B5D7A" media="(prefers-color-scheme: light)">\n<meta name="theme-color" content="#0F171D" media="(prefers-color-scheme: dark)">\n'
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
# The script stays inline on every page: measured on a throttled phone, one request
# paints the first page about a second sooner than a separate cached script file.
script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
import base64
SCRIPT_HASH = "'sha256-" + base64.b64encode(hashlib.sha256(script.encode()).digest()).decode() + "'"
_th = re.search(r'<script id="th">(.*?)</script>', html, re.S).group(1)
SCRIPT_HASH += " 'sha256-" + base64.b64encode(hashlib.sha256(_th.encode()).digest()).decode() + "'"
# rewrite #/ links in the static markup only; the script must stay byte-identical to its CSP hash
_pre, _post = html.split("<script>" + script + "</script>")
def _paths(x):
    x = x.replace('href="#/med/', 'href="/medicines/').replace('href="#/"', 'href="/"')
    return re.sub(r'href="#(/[a-z0-9-]+)"', r'href="\1"', x)
page = _paths(_pre) + "<script>" + script + "</script>" + _paths(_post)
page = re.sub(r'(<title>)[^<]*(</title>)', r'\1__TITLE__\2', page, count=1)

def sentence(t, n=158):
    t = re.sub(r"\s*\[\d+\]", "", re.sub(r"<[^>]+>", "", t)).strip()
    if len(t) <= n: return t
    cut = t[:n].rsplit(" ", 1)[0].rstrip(",;:—- ")
    return cut + "…"

VIEWDESC = {
 "/": BASE_DESC,
 "/supply": "Which gender-affirming hormone medicines are in short supply in Australia right now, checked daily against TGA records, and what to do about it.",
 "/medicines": "Every medicine used in gender-affirming hormone therapy in Australia, with a page for each: how it is used, cost, monitoring and current supply.",
 "/sightings": "Reports from the public of gender-affirming medicines seen in stock at South Australian pharmacies.",
 "/pharmacy-reports": "Stock reports for gender-affirming medicines posted by registered South Australian pharmacists.",
 "/feedback": "Report a mistake, something missing or an accessibility problem on GAMSA.",
 "/search": "Search every page, guide and medicine on GAMSA.",
 "/alerts": "Gender-affirming medicines under a current TGA shortage notice, with an RSS feed for prescribers and pharmacists.",
 "/trans": "Gender-affirming medicines in plain language for trans and gender diverse South Australians: supply, costs, doses, how to use each one, and your pharmacy.",
 "/clinicians": "For prescribers, nurses and pharmacists: testosterone injection training package, pharmacist stock register, monitoring schedule, PBS Authority wording, shortage alerts.",
 "/allies": "GAMSA for family, friends and allies of trans and gender diverse people: what the medicines are, what goes wrong, and how to help at the pharmacy.",
 "/easy": "Easy Read guides to gender-affirming hormone medicines: getting your medicine, shortages, costs, doses and using it safely, in short sentences with pictures.",
}
CVIEW = {"/doses": "dosing", "/using": "administration", "/costs": "costs", "/pharmacy": "pharmacy", "/clinician-guide": "clinicians", "/ally-guide": "allies", "/resources": "resources", "/privacy": "privacy", "/accessibility": "accessibility", "/disclaimer": "disclaimer"}
TITLES = {"/": "Gender-Affirming Medicines South Australia", "/supply": "Supply & shortages",
          "/medicines": "Medicines A–Z", "/sightings": "Patient sightings", "/easy": "Easy Read guides",
          "/doses": "Doses and formulations", "/using": "How to use your medicine",
          "/pharmacy": "Working with your pharmacy", "/costs": "Costs and the PBS", "/feedback": "Send feedback", "/pharmacy-reports": "Pharmacy stock reports",
          "/trans": "Trans and gender diverse people", "/clinicians": "Clinicians and pharmacists", "/allies": "Family, friends and allies",
          "/clinician-guide": "For clinicians and pharmacists", "/ally-guide": "For family, friends and allies", "/resources": "Resources", "/alerts": "Shortage alerts", "/privacy": "Privacy", "/accessibility": "Accessibility", "/disclaimer": "Disclaimer", "/search": "Search"}
VIEWID = {"/": "v-home", "/supply": "v-supply", "/medicines": "v-medicines", "/sightings": "v-sightings",
          "/easy": "v-easy", "/doses": "v-doses", "/using": "v-using", "/pharmacy": "v-pharmacy",
          "/costs": "v-costs", "/feedback": "v-feedback", "/pharmacy-reports": "v-pharmacy-reports",
          "/trans": "v-trans", "/clinicians": "v-clinicians", "/allies": "v-allies", "/clinician-guide": "v-clinician-guide", "/ally-guide": "v-ally-guide", "/resources": "v-resources", "/alerts": "v-alerts", "/privacy": "v-privacy", "/accessibility": "v-accessibility", "/disclaimer": "v-disclaimer", "/search": "v-search"}

def ld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False).replace("</", "<\\/") + "</script>\n"

def write(path, title, desc, view, schema, noindex=False):
    full = title if path == "/" else title + " — GAMSA"
    extra = ld(schema) + ('<meta name="robots" content="noindex">\n' if noindex else "")
    top = head(full, desc, path, extra).replace("__ROUTING__", ' data-routing="path"')
    body = page.replace("__TITLE__", H.escape(full), 1) \
               .replace(f'<div class="view" id="{view}"', f'<div class="view on" id="{view}"', 1)
    # Cloudflare Pages serves /costs from costs.html (and /costs/ needs a redirect if it were a folder)
    out = D/"index.html" if path == "/" else D/(path.strip("/") + ".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(shell(top, body))

urls = []
for path, title in TITLES.items():
    desc = VIEWDESC.get(path) or sentence(content[CVIEW[path]]["intro"])
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
    if path not in ("/sightings", "/feedback", "/search"): urls.append(path)

for m in medinfo["medicines"]:
    path = "/medicines/" + m["id"]
    short = m["name"].split(" (")[0]
    title = short + (": doses, cost and supply" if len(short) < 34 else "")
    desc = sentence(m.get("summary", ""))
    page_ld = {"@type": "MedicalWebPage", "name": m["name"],
              "url": SITE + path, "description": desc, "inLanguage": "en-AU",
              "about": {"@type": "Drug", "name": m["name"], "nonProprietaryName": m["generic"]},
              "author": AUTHOR, "reviewedBy": AUTHOR, "lastReviewed": REVIEWED_ISO, "publisher": ORG}
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
    write(path, title, desc, "v-med", schema)
    urls.append(path)

for g in content["easyread"]["guides"]:
    path = "/easy/" + g["id"]
    desc = g["title"] + " — " + g["subtitle"] + ". An Easy Read guide in short sentences with pictures."
    write(path, g["title"] + " (Easy Read)", desc, "v-easy-guide",
          {"@context": "https://schema.org", "@type": "MedicalWebPage", "name": g["title"] + " (Easy Read)",
           "url": SITE + path, "description": desc, "inLanguage": "en-AU", "author": AUTHOR, "publisher": ORG})
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
        items.append("<item><title>" + H.escape(f"{st}: {name}") + "</title><link>" + link + "</link><guid isPermaLink=\"false\">" + H.escape(f"gamsa-{r.get('id', name)}-{r.get('status')}") + "</guid><pubDate>" + email.utils.format_datetime(dt) + "</pubDate><description>" + H.escape((r.get("note") or st) + " Expected return: " + str(r.get("expectedReturn", "—")) + ". TGA status as checked " + str(meds.get("generatedAt", "")) + ".") + "</description></item>")
    (D/"feed.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>GAMSA shortage alerts</title><link>' + SITE + '/supply</link><description>Gender-affirming medicines in Australia under a current TGA shortage notice. Rebuilt daily.</description><language>en-au</language>' + "".join(items) + "</channel></rss>\n")
_rss()
(D/"robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n")
if (R/"static").exists():
    shutil.copytree(R/"static", D, dirs_exist_ok=True)

csp = "; ".join([
    "default-src 'self'",
    "script-src 'self' " + SCRIPT_HASH + " https://static.cloudflareinsights.com https://challenges.cloudflare.com",
    "frame-src https://challenges.cloudflare.com",
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self'",
    "img-src 'self' data:",
    "connect-src 'self' https://cloudflareinsights.com",
    "frame-ancestors 'none'", "base-uri 'self'", "form-action 'self'", "object-src 'none'",
    "upgrade-insecure-requests",
])
(D/"_headers").write_text("\n".join([
    "/*",
    "  Content-Security-Policy: " + csp,
    "  Strict-Transport-Security: max-age=31536000; includeSubDomains",
    "  X-Content-Type-Options: nosniff",
    "  X-Frame-Options: DENY",
    "  Referrer-Policy: strict-origin-when-cross-origin",
    "  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()",
    "  Cross-Origin-Opener-Policy: same-origin",
    "",
]))
n = sum(1 for _ in D.rglob("*.html")) - 1
print(f"Built dist/: {n} pages, sitemap with {len(urls)} URLs; preview.html for local viewing")
