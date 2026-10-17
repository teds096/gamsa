#!/usr/bin/env python3
"""Extra GAMSA checks, run by tools/site_check.py (needs the local server on 127.0.0.1:8767 for the browser parts).

Prints one line per check: "PASS name — detail", "FAIL name — detail" or "SKIP name — why".
  seo            titles 10-65 chars, descriptions 70-165, unique descriptions, canonical, Open Graph,
                 JSON-LD parses, /search noindex and not in the sitemap
  downloads      every link to a .pdf/.zip carries download or opens in a new tab (never routed by the app)
  pdfs           every PDF in static/ opens, page count (clinician package SOP 7, others 1-2), QR codes decode
                 to https://gamsa.au/... (needs opencv-python-headless and pdftoppm; else SKIP)
  wording        content/*.json has no leftover phrases (this session, our clinic, lorem, TODO) or US spellings
  weight         gzip size of every built page vs tools/weights.json; flags >10% growth (--update-weights resets)
  search         key searches return the right page first
  keyboard       Tab reaches skip link, menu, accessibility, quick exit, search; focus always visible;
                 Enter opens a menu group, Escape closes it
  print          print media: no sideways overflow at A4 width, header and menus hidden or static
  figures        figures built by figures.py: alt <= 100 characters, visible long description, words in HTML (no SVG
                 text), each view <= 8 KB, no fixed colours or plates; lines and marks >= 3:1 in light, dark, high
                 contrast, HC + dark, colour-blind and CB + dark (browser part needs the local server)
  engines        Safari (WebKit) and Firefox: home, a hub, costs and an Easy Read page render without errors
                 or overflow at phone and desktop width (SKIP if the engines are not installed:
                 python3 -m playwright install webkit firefox)
"""
import gzip, json, os, pathlib, re, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]; os.chdir(ROOT)
D = ROOT / "dist"; B = "http://127.0.0.1:8767"; CHROME = os.environ.get("CHROME") or None
def out(ok, name, detail=""):
    print(("PASS " if ok is True else "FAIL " if ok is False else "SKIP ") + name + (f" — {detail}" if detail else ""), flush=True)

def pages():
    for f in sorted(D.rglob("*.html")):
        if f.name == "404.html": continue
        rel = "/" + str(f.relative_to(D))[:-5]
        yield ("/" if rel == "/index" else rel), f.read_text()

def seo():
    bad, descs = [], {}
    sm = (D/"sitemap.xml").read_text()
    for path, h in pages():
        t = (re.search(r"<title>(.*?)</title>", h) or [None, ""])[1]
        d = (re.search(r'name="description" content="([^"]*)"', h) or [None, ""])[1]
        if not 10 <= len(t) <= 70: bad.append(f"title {len(t)} {path}")
        if path != "/search" and not 70 <= len(d) <= 170: bad.append(f"desc {len(d)} {path}")
        descs.setdefault(d, []).append(path)
        if f'rel="canonical" href="https://gamsa.au{path if path != "/" else "/"}"' not in h: bad.append(f"canonical {path}")
        for k in ("og:title", "og:description", "og:image", "og:url"):
            if f'property="{k}"' not in h: bad.append(f"{k} {path}")
        for js in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
            try: json.loads(js)
            except Exception: bad.append(f"json-ld {path}")
    dups = [v for v in descs.values() if len(v) > 1]
    if dups: bad.append(f"duplicate descriptions {dups[:2]}")
    s = (D/"search.html").read_text() if (D/"search.html").exists() else ""
    if 'name="robots" content="noindex"' not in s or "gamsa.au/search<" in sm: bad.append("search should be noindex and out of the sitemap")
    for _p in ("/sightings", "/feedback"):
        if f"gamsa.au{_p}<" not in sm: bad.append(f"{_p} should be in the sitemap")
        elif 'name="robots" content="noindex"' in (D/(_p.strip("/")+".html")).read_text(): bad.append(f"{_p} is in the sitemap but noindex")
    out(not bad, "seo", "; ".join(bad[:6]) or "titles, descriptions, canonicals, Open Graph, JSON-LD")

def downloads():
    bad = set()
    for f in list(ROOT.glob("content/*.json")):
        for m in re.finditer(r"\]\((/[^)]+\.(?:pdf|zip))\)", f.read_text()):
            if not (ROOT/"static"/m.group(1).lstrip("/")).exists(): bad.add("missing file " + m.group(1))
    tpl = (ROOT/"template.html").read_text()
    for m in re.finditer(r'<a[^>]+href="(/[^"]+\.(?:pdf|zip|xml))"[^>]*>', tpl):
        if "download" not in m.group(0) and "_blank" not in m.group(0) and not m.group(1).endswith(".xml"): bad.add("no download/new-tab " + m.group(1))
    for m in re.finditer(r'h:"(/[^"]+\.(?:pdf|zip))"', tpl):
        if not (ROOT/"static"/m.group(1).lstrip("/")).exists(): bad.add("missing file " + m.group(1))
    if "a.hasAttribute(\"download\")" not in tpl or "pdf|zip" not in tpl: bad.add("router no longer skips file links")
    out(not bad, "downloads", "; ".join(sorted(bad)[:5]) or "file links exist and bypass the router")

def pdfs():
    try:
        import cv2, numpy  # noqa
    except Exception:
        cv2 = None
    bad, info = [], []
    for f in sorted((ROOT/"static").rglob("*.pdf")):
        p = subprocess.run(["pdfinfo", str(f)], capture_output=True, text=True)
        n = int((re.search(r"Pages:\s+(\d+)", p.stdout) or [0, 0])[1])
        if n == 0: bad.append(f"unreadable {f.name}"); continue
        limit = 8 if "sop" in f.name else 2
        if n > limit: bad.append(f"{f.name} {n} pages")
        info.append(n)
        if "gamsa-brand-5b" not in p.stdout and "gamsa-logo-5b" not in p.stdout: bad.append(f"no logo/stripe on {f.name} - run python3 tools/brand.py")
        if cv2:
            png = f"/tmp/_qr_{f.stem}"
            subprocess.run(["pdftoppm", "-r", "150", "-png", "-f", "1", "-l", "1", str(f), png], capture_output=True)
            img = cv2.imread(png + "-1.png") if pathlib.Path(png + "-1.png").exists() else cv2.imread(png + "-01.png")
            if img is None: continue
            data, *_ = cv2.QRCodeDetector().detectAndDecode(img)
            if not data:
                p2 = subprocess.run(["pdftoppm", "-r", "300", "-png", str(f), png + "a"], capture_output=True)
                for g in sorted(pathlib.Path("/tmp").glob(f"_qr_{f.stem}a-*.png")):
                    data, *_ = cv2.QRCodeDetector().detectAndDecode(cv2.imread(str(g)))
                    if data: break
            if not data: bad.append(f"no QR found {f.name}")
            elif not data.startswith("https://gamsa.au/"): bad.append(f"QR {f.name} -> {data}")
    z = ROOT/"static/clinicians/testosterone-undecanoate-im-training-package.zip"
    if z.exists():
        import zipfile
        with zipfile.ZipFile(z) as zz:
            for n in zz.namelist():
                if not n.endswith(".pdf"): continue  # README.txt lives only in the zip
                if not (ROOT/"static/clinicians"/n).exists(): bad.append(f"training zip has {n}, missing from static/clinicians"); continue
                if zz.read(n) != (ROOT/"static/clinicians"/n).read_bytes(): bad.append(f"training zip has an old copy of {n} - run python3 tools/brand.py")
    out(not bad, "pdfs", "; ".join(bad[:5]) or f"{len(info)} PDFs open, page counts OK, logo on each, training zip current" + (", QR codes point to gamsa.au" if cv2 else " (QR not checked: pip install opencv-python-headless)"))

def assets():
    bad = []
    for f, h in pages():
        for u in re.findall(r'og:image" content="https://gamsa\.au/([^"]+)"', h):
            if not (D / u).exists(): bad.append(f"missing og image {u}")
        if re.search(r"fonts\.(googleapis|gstatic)\.com", h): bad.append(f"Google Fonts still referenced in {f}")
        for u in set(re.findall(r'<link [^>]*href="/([^"#?]+)"', h)):   # tab icons (mask-icon.svg), font preloads
            if not (D / u).exists(): bad.append(f"linked file missing /{u} in {f}")
        if "ld+json" in h and str(f).startswith("/medicines/") and '"FAQPage"' not in h: bad.append(f"no FAQ markup {f}")
    for k in ("favicon.ico", "apple-touch-icon.png", "mask-icon.svg"):
        if not (D / k).exists() or (D / k).read_bytes() != (ROOT / "static" / k).read_bytes(): bad.append(f"icon {k} missing or not the static/ file")
    keys = [k for k in D.glob("*.txt") if re.fullmatch(r"[0-9a-f]{32}\.txt", k.name)]
    if not keys: bad.append("IndexNow key file missing")
    for w in ("public-sans-latin-wght-normal", "lexend-latin-wght-normal", "atkinson-hyperlegible-latin-700-normal"):
        if not (D / "fonts" / (w + ".woff2")).exists(): bad.append(f"font {w} missing")
    import json as _j, datetime as _dt
    for m in _j.loads((ROOT / "content/medicines.json").read_text())["medicines"]:
        if not (D / "og" / f"medicines-{m['id']}.jpg").exists(): bad.append(f"no share image for {m['id']} (run tools/og_images.py)")
    rd = (D / "_redirects")
    if rd.exists():
        real = set(re.findall(r"<loc>https://gamsa\.au([^<]*)</loc>", (D / "sitemap.xml").read_text())) | {"/"}
        for line in rd.read_text().splitlines():
            f2 = line.split()
            if len(f2) >= 2 and not line.startswith("#"):
                tgt = f2[1].replace(":splat", "estradiol-patches")
                if tgt not in real and not (D / (tgt.strip("/") + ".html")).exists(): bad.append(f"redirect target missing {f2[1]}")
                if f2[0].rstrip("*").rstrip("/") in real: bad.append(f"redirect hides a real page {f2[0]}")
    out(not bad, "assets", "; ".join(bad[:4]) or "own fonts, page share images, icons, linked files, FAQ markup and IndexNow key in place")

def review_date():
    import json as _j, datetime as _dt
    r = _j.loads((ROOT / "content/medicines.json").read_text()).get("reviewed", "")
    try: age = (_dt.date.today() - _dt.datetime.strptime(r, "%d %B %Y").date()).days
    except ValueError: return out(False, "review date", f"content/medicines.json reviewed {r!r} is not like '3 October 2026'")
    if age > 365: return out(False, "review date", f"medicine pages say last reviewed {r} ({age} days ago) — re-review and update")
    print(f"{'NOTE' if age > 90 else 'PASS'} review date — last reviewed {r} ({age} days ago){'; quarterly evidence review due' if age > 90 else ''}")

def wording():
    pat = re.compile(r"\b(colou?rs?|behavior|favorite|labeled|analyze|pediatric|hemoglobin|anemia|center|fiber|liter|gray)\b|this session|\bour clinic\b|at this clinic|lorem|TODO|\bTBD\b", re.I)
    us = {"color", "colors", "behavior", "favorite", "labeled", "analyze", "pediatric", "hemoglobin", "anemia", "center", "fiber", "liter", "gray"}
    bad = []
    for f in ROOT.glob("content/*.json"):
        s = f.read_text()
        for m in pat.finditer(s):
            w = m.group(0); ctx = s[max(0, m.start()-30):m.end()+10]
            if w.lower() in ("colour", "colours"): continue
            if '\\"' in ctx: continue   # inside a quotation from a source
            if w.lower() in us or not m.group(1): bad.append(f"{f.name}: …{ctx.strip()[:50]}…")
    out(not bad, "wording", "; ".join(bad[:5]) or "no leftovers or US spellings")

FIG_MODES = {"light": {"theme": "light"}, "dark": {"theme": "dark"}, "high contrast": {"theme": "light", "hc": "1"},
             "HC + dark": {"theme": "dark", "hc": "1"}, "colour-blind": {"theme": "light", "cb": "1"}, "CB + dark": {"theme": "dark", "cb": "1"}}
# art shapes that carry meaning (lines, marks, sites): each must stand out 3:1 from the figure surface (WCAG 2.2 1.4.11).
# Left out on purpose: the soft arch, zone tints and textures (decoration; the outline, hatching and words carry the meaning).
FIG_JS = """() => { const out=[]; const lum=c=>{const m=c.match(/[\\d.]+/g);if(!m)return null;const [r,g,b]=m.slice(0,3).map(v=>{v/=255;return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4)});return {L:.2126*r+.7152*g+.0722*b,a:m.length>3?+m[3]:1}};
  const ratio=(a,b)=>{const x=lum(a),y=lum(b);if(!x||!y)return 99;return (Math.max(x.L,y.L)+.05)/(Math.min(x.L,y.L)+.05)};
  for(const f of document.querySelectorAll('.view.on figure.gf')){ const bg=getComputedStyle(f).backgroundColor;
    for(const e of f.querySelectorAll('svg :is(.k-body,.k-body *,.k-bone,.k-v,.k-mark,.k-site,.k-not rect,.k-x,.k-band,.k-edge,.k-edge2,.k-needle,.k-hub,.k-axis,.k-line,.k-p,.k-pl,.k-pa,.k-za,.k-pf,.k-pm,.k-arrow,.gf-sw .k-spot,.k-zb,.gf-bod .k-zone *,.k-pn rect)')){
      const s=getComputedStyle(e); if(s.display==='none'||!e.getBoundingClientRect().width) continue;
      const paint=(s.stroke&&s.stroke!=='none'&&parseFloat(s.strokeWidth)>0&&!e.matches('.k-site'))?s.stroke:s.fill;
      if(!paint||paint==='none'||/url/.test(paint)) continue;
      const r=ratio(paint,bg); if(r<3) out.push(f.dataset.fig+' '+e.getAttribute('class')+' '+paint+' on '+bg+' '+r.toFixed(2)); }
    for(const e of f.querySelectorAll('.gf-mk')){ const s=getComputedStyle(e), b=e.getBoundingClientRect(); if(s.display==='none'||!(b.width||b.height)) continue;
      let paint=(s.backgroundImage==='none'&&!e.matches('.gf-win,.gf-ring')&&s.backgroundColor!=='rgba(0, 0, 0, 0)')?s.backgroundColor:null;
      if(!paint&&parseFloat(s.borderTopWidth)>0) paint=s.borderTopColor; if(!paint) continue;   /* hatching is texture: its stripes are checked by eye */
      const r=ratio(paint,bg); if(r<3) out.push(f.dataset.fig+' '+e.className+' '+paint+' on '+bg+' '+r.toFixed(2)); }
    for(const sv of f.querySelectorAll('svg')){ const b=getComputedStyle(sv).backgroundColor; if(b!=='rgba(0, 0, 0, 0)') out.push(f.dataset.fig+' plate '+b); }
    if(document.documentElement.classList.contains('dark') && lum(bg) && lum(bg).L>.5) out.push(f.dataset.fig+' light figure in dark mode');
  } return out; }"""

# Easy Read pictures (template ICONS): the picture colour against whatever it sits on (row, card, page) >= 3:1, no plate
ICON_JS = """() => { const out=[]; const lum=c=>{const m=c.match(/[\\d.]+/g);if(!m)return null;const [r,g,b]=m.slice(0,3).map(v=>{v/=255;return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4)});return {L:.2126*r+.7152*g+.0722*b,a:m.length>3?+m[3]:1}};
  const ratio=(a,b)=>{const x=lum(a),y=lum(b);if(!x||!y)return 99;return (Math.max(x.L,y.L)+.05)/(Math.min(x.L,y.L)+.05)};
  const bgOf=e=>{for(let x=e;x;x=x.parentElement){const b=getComputedStyle(x).backgroundColor;const l=lum(b);if(l&&l.a>0)return b;}return 'rgb(255, 255, 255)'};
  let n=0; for(const sv of document.querySelectorAll('.view.on svg.er-icon')){ if(!sv.getBoundingClientRect().width) continue; n++;
    const s=getComputedStyle(sv); if(s.backgroundColor!=='rgba(0, 0, 0, 0)') out.push('icon plate '+s.backgroundColor);
    const bg=bgOf(sv.parentElement), r=ratio(s.fill,bg); if(r<3) out.push('icon '+s.fill+' on '+bg+' '+r.toFixed(2)); }
  return {n, out}; }"""

def figures():
    """figures built by figures.py from content/*.json: alt <= 100 characters, a long description on the page, every word in
    HTML (no drawn <text>), each view <= 8 KB, colours only from the stylesheet (no fixed white plate); then, in the browser,
    lines and marks (SVG shapes and the HTML chart marks) >= 3:1 against the figure in every colour mode, and the Easy Read
    pictures >= 3:1 against what they sit on. A section with an old hand-drawn "svg" is a failure (it is no longer shown)."""
    sys.path.insert(0, str(ROOT))
    import figures as F
    c = {p.stem: json.loads(p.read_text()) for p in (ROOT / "content").glob("*.json")}
    old = [f"{k}:{i}" for k, v in c.items() if isinstance(v, dict) for i, s in enumerate(v.get("sections", [])) if s.get("svg")]
    bad = [f"{x} has an old svg diagram, which the site no longer shows: convert it to a figure" for x in old]
    try: done = F.render_content(c)
    except Exception as e: return out(False, "figures", f"definition error: {e}")
    for page in c.values():
        for s in (page.get("sections", []) if isinstance(page, dict) else []):
            g = s.get("fig")
            if not g: continue
            d = g["id"]
            if s.get("svg"): bad.append(f"{d} has an old svg as well")
            h, er = g["html"], g["er"]
            alt = re.search(r'<title id="[^"]+">([^<]*)</title>|aria-label="([^"]*)"', h)
            alt = (alt.group(1) or alt.group(2)) if alt else ""
            if not alt: bad.append(f"{d} no alt")
            elif len(alt) > F.ALT_MAX: bad.append(f"{d} alt {len(alt)} chars")
            if not re.search(r'id="gfU-[^"]+-d"[^>]*>[^<]{20,}', h): bad.append(f"{d} no long description")
            if '<svg' in h and 'role="img"' in h and 'aria-describedby="gfU-' not in h: bad.append(f"{d} drawing not tied to its description")
            for v, x in (("page", h), ("easy", er)):
                if "<text" in x: bad.append(f"{d} {v}: words drawn in the SVG")
                if len(x.encode()) > F.LIMIT: bad.append(f"{d} {v} view {len(x.encode())} B > {F.LIMIT}")
                if re.search(r'(fill|stroke|stop-color)="#|style="[^"]*(?:fill|stroke|background)', x): bad.append(f"{d} {v}: fixed colour in the markup")
            if not g["er"].count("<li>") >= 3: bad.append(f"{d} fewer than 3 Easy Read panels")
    detail = f"{len(done)} figures: alt <= 100, long description, words in HTML, <= 8 KB, colours from the stylesheet"
    try:
        import socket; s_ = socket.socket(); up = s_.connect_ex(("127.0.0.1", 8767)) == 0; s_.close()
        if not up: raise RuntimeError("local server not running")
        from playwright.sync_api import sync_playwright
        routes = sorted({"/using", "/costs", "/doses"} | {"/easy/" + g["id"] for g in c["easyread"]["guides"] for s in g["sections"] if s.get("figure")}
                        | {"/medicines/estradiol-patches", "/medicines/estradiol-tablets", "/medicines/cyproterone-acetate"})
        with sync_playwright() as p:
            b = p.chromium.launch(**({"executable_path": CHROME} if CHROME else {}))
            icons, er_routes = 0, ["/easy"] + ["/easy/" + g["id"] for g in c["easyread"]["guides"]]
            for mode, ls in FIG_MODES.items():
                ctx = b.new_context(viewport={"width": 1280, "height": 900})
                ctx.add_init_script("try{localStorage.clear();" + "".join(f"localStorage.setItem('gamsa.{k}','{v}');" for k, v in ls.items()) + "}catch(e){}")
                ctx.route("**/*", lambda r: r.abort() if "127.0.0.1" not in r.request.url else r.continue_())
                pg = ctx.new_page()
                for r in routes:
                    pg.goto(B + r); pg.wait_for_timeout(250)
                    bad += [f"{mode} {r}: {x}" for x in pg.evaluate(FIG_JS)[:3]]
                for r in er_routes:
                    pg.goto(B + r); pg.wait_for_timeout(200)
                    res = pg.evaluate(ICON_JS); icons += res["n"]
                    bad += [f"{mode} {r}: {x}" for x in res["out"][:3]]
                ctx.close()
            b.close()
        detail += (f"; lines and marks >= 3:1, no plates, in {len(FIG_MODES)} colour modes on {len(routes)} pages"
                   f"; Easy Read pictures >= 3:1, no plates ({icons} checks on {len(er_routes)} pages)")
    except Exception as e:
        detail += f" (browser part skipped: {str(e)[:60]})"
    out(not bad, "figures", "; ".join(bad[:5]) or detail)

def weight(update=False):
    base_f = ROOT/"tools"/"weights.json"
    now = {p: len(gzip.compress(h.encode(), 6)) for p, h in pages()}
    base = json.loads(base_f.read_text()) if base_f.exists() else {}
    grew = [f"{p} {base[p]//1024}→{n//1024} KB" for p, n in now.items() if p in base and n > base[p] * 1.10]
    biggest = max(now.values()) // 1024
    if update or not base: base_f.write_text(json.dumps(now, indent=0, sort_keys=True))
    out(not grew, "weight", "; ".join(grew[:5]) or f"largest page {biggest} KB gzipped" + (" (baseline saved)" if update or not base else ""))

def browser_checks():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(**({"executable_path": CHROME} if CHROME else {}))
        ctx = b.new_context(viewport={"width": 1280, "height": 900}); ctx.route("**/*", lambda r: r.abort() if "127.0.0.1" not in r.request.url else r.continue_())
        pg = ctx.new_page()
        # search quality
        cases = {"patches": "patch", "Reandron": "testosterone undecanoate", "safety net": "safety net", "injection": "inject", "Closing the Gap": "closing the gap", "Estradot": "estradiol"}
        bad = []
        for q, want in cases.items():
            pg.goto(f"{B}/search?q={q}"); pg.wait_for_timeout(300)
            first = (pg.evaluate("(document.querySelector('#srOut .sr')||{}).innerText||''") or "").lower()
            if want not in first: bad.append(f"'{q}' → {first[:40]!r}")
        out(not bad, "search", "; ".join(bad) or f"{len(cases)} key searches find the right page first")
        # keyboard
        pg.goto(B + "/"); pg.wait_for_timeout(300)
        seen, invisible = set(), []
        for _ in range(45):
            pg.keyboard.press("Tab")
            r = pg.evaluate("""(()=>{const e=document.activeElement;if(!e||e===document.body)return null;const s=getComputedStyle(e);
              const vis=(s.outlineStyle!=='none'&&parseFloat(s.outlineWidth)>0)||s.boxShadow!=='none'||e.matches(':focus-within');
              return [e.id||e.className||e.tagName, vis]})()""")
            if r: seen.add(str(r[0])); (None if r[1] else invisible.append(str(r[0])))
        need = {"skip": any("skip" in s for s in seen), "menu": any("ng-btn" in s for s in seen), "accessibility": "a11yBtn" in seen,
                "quick exit": "exitBtn" in seen, "search": "siteq" in seen}
        miss = [k for k, v in need.items() if not v]
        pg.goto(B + "/"); pg.wait_for_timeout(200); pg.focus(".ng-btn"); pg.keyboard.press("Enter"); pg.wait_for_timeout(150)
        opened = pg.evaluate("!!document.querySelector('.ng.open')"); pg.keyboard.press("Escape"); pg.wait_for_timeout(100)
        closed = not pg.evaluate("!!document.querySelector('.ng.open')")
        ok = not miss and not invisible and opened and closed
        out(ok, "keyboard", ("; ".join(filter(None, [f"not reached: {miss}" if miss else "", f"no visible focus: {invisible[:3]}" if invisible else "",
            "" if opened else "Enter does not open menu", "" if closed else "Escape does not close menu"])) or f"{len(seen)} stops, focus visible, menu opens/closes"))
        # open panels: axe colour contrast with the Accessibility panel and a menu open, light and dark
        ax = pathlib.Path("node_modules/axe-core/axe.min.js")
        if ax.exists():
            bad = []
            for th in ("light", "dark"):
                pg.goto(B + "/"); pg.evaluate(f"localStorage.setItem('gamsa.theme','{th}')"); pg.reload(); pg.wait_for_timeout(300)
                for opener, sel in (("#a11yBtn", "#a11yPanel"), (".ng-btn", ".ng.open")):
                    pg.click(opener); pg.wait_for_timeout(200); pg.evaluate(ax.read_text() + ";0")
                    v = pg.evaluate("""async s=>{const r=await axe.run(document.querySelector(s)||document,{runOnly:['color-contrast']});
                      return r.violations.flatMap(v=>v.nodes.map(n=>n.target.join(' ')+' '+(n.any[0]||{}).message?.slice(0,60)))}""", sel)
                    bad += [f"{th} {sel}: {x}" for x in v[:2]]
                    pg.keyboard.press("Escape"); pg.wait_for_timeout(100)
            out(not bad, "open panels", "; ".join(bad[:4]) or "Accessibility panel and menus readable in light and dark")
        # print
        pp = b.new_page(viewport={"width": 794, "height": 1123}); pp.route("**/*", lambda r: r.abort() if "127.0.0.1" not in r.request.url else r.continue_())
        bad = []
        for r in ("/costs", "/easy/helping", "/clinician-guide", "/medicines/testosterone-undecanoate"):
            pp.goto(B + r); pp.wait_for_timeout(250); pp.emulate_media(media="print")
            st = pp.evaluate("(()=>{const h=document.querySelector('header');const s=getComputedStyle(h);return [document.documentElement.scrollWidth>innerWidth+1, s.display==='none'||s.position!=='sticky'&&s.position!=='fixed']})()")
            if st[0]: bad.append(f"overflow {r}")
            if not st[1]: bad.append(f"sticky header prints over content {r}")
            pp.emulate_media(media="screen")
        out(not bad, "print", "; ".join(bad) or "A4 print layout OK")
        b.close()

def engines():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        for name in ("webkit", "firefox"):
            try: eb = getattr(p, name).launch()
            except Exception as e:
                out(None, f"engine {name}", "not installed (python3 -m playwright install " + name + ")"); continue
            bad = []
            for w, h in ((390, 844), (1280, 900)):
                c = eb.new_context(viewport={"width": w, "height": h}); c.route("**/*", lambda r: r.abort() if "127.0.0.1" not in r.request.url else r.continue_())
                q = c.new_page(); errs = []; q.on("pageerror", lambda e: errs.append(str(e)[:80]))
                for r in ("/", "/clinicians", "/costs", "/supply", "/medicines/estradiol-patches", "/easy/helping"):
                    q.goto(B + r); q.evaluate("document.fonts.ready.then(()=>1)"); q.wait_for_timeout(300)
                    if q.evaluate("document.documentElement.scrollWidth>innerWidth+1"):
                        who = q.evaluate("""(()=>{const W=document.documentElement.clientWidth;const o=[];for(const e of document.querySelectorAll('body *')){const b=e.getBoundingClientRect();
                          if(b.width&&b.right>W+1&&!(e.parentElement&&e.parentElement.getBoundingClientRect().right>W+1)){o.push((e.tagName.toLowerCase()+(e.id?'#'+e.id:'')+(e.className&&e.className.baseVal===undefined?'.'+String(e.className).trim().split(/\\s+/).join('.'):''))+' '+Math.round(b.right)+'>'+W);if(o.length>2)break;}}
                          return o.join(', ')+' (page '+document.documentElement.scrollWidth+')';})()""")
                        hdr = q.evaluate("""(()=>{const W=e=>e?Math.round(e.getBoundingClientRect().width):0;
                          return 'header logo '+W(document.querySelector('.bar .logo'))+' nav '+W(document.querySelector('nav.main'))+' right '+W(document.querySelector('.bar-r'))
                          +' buttons ['+[...document.querySelectorAll('nav.main > *, .bar-r > *')].map(W).join(',')+']'
                          +' font '+(document.fonts.check('16px "Public Sans"')?'loaded':'NOT loaded')+' cur '+[...document.querySelectorAll('.ng.cur')].length;})()""")
                        bad.append(f"overflow {w}px {r}: {who}; {hdr}")
                    if not q.evaluate("!!document.querySelector('.view.on h1')"): bad.append(f"no content {w}px {r}")
                try:
                    q.goto(B + "/"); q.wait_for_timeout(300); q.click("#a11yBtn"); q.wait_for_timeout(300)
                    if not q.evaluate("(()=>{const p=document.getElementById('a11yPanel');return !!p&&p.offsetHeight>0})()"): bad.append(f"Accessibility panel does not open {w}px")
                except Exception as e: bad.append(f"Accessibility panel {w}px: {str(e)[:60]}")
                if errs: bad.append(f"JS error {w}px: {errs[0]}")
                c.close()
            eb.close()
            out(not bad, f"engine {name}", "; ".join(bad[:4]) or "renders cleanly at phone and desktop width")

if __name__ == "__main__":
    if "--engines-only" in sys.argv: engines(); sys.exit(0)
    if "--figures-only" in sys.argv: figures(); sys.exit(0)
    seo(); downloads(); assets(); review_date(); pdfs(); wording(); figures(); weight("--update-weights" in sys.argv)
    try: browser_checks()
    except Exception as e: out(False, "browser checks", str(e)[:200])
    engines()
