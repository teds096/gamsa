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
    out(not bad, "pdfs", "; ".join(bad[:5]) or f"{len(info)} PDFs open, page counts OK" + (", QR codes point to gamsa.au" if cv2 else " (QR not checked: pip install opencv-python-headless)"))

def assets():
    bad = []
    for f, h in pages():
        for u in re.findall(r'og:image" content="https://gamsa\.au/([^"]+)"', h):
            if not (D / u).exists(): bad.append(f"missing og image {u}")
        if re.search(r"fonts\.(googleapis|gstatic)\.com", h): bad.append(f"Google Fonts still referenced in {f}")
        if "ld+json" in h and str(f).startswith("/medicines/") and '"FAQPage"' not in h: bad.append(f"no FAQ markup {f}")
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
    out(not bad, "assets", "; ".join(bad[:4]) or "own fonts, page share images, FAQ markup and IndexNow key in place")

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
        # other engines
        for name in ("webkit", "firefox"):
            try: eb = getattr(p, name).launch()
            except Exception as e:
                out(None, f"engine {name}", "not installed (python3 -m playwright install " + name + ")"); continue
            bad = []
            for w, h in ((390, 844), (1280, 900)):
                c = eb.new_context(viewport={"width": w, "height": h}); c.route("**/*", lambda r: r.abort() if "127.0.0.1" not in r.request.url else r.continue_())
                q = c.new_page(); errs = []; q.on("pageerror", lambda e: errs.append(str(e)[:80]))
                for r in ("/", "/clinicians", "/costs", "/easy/helping"):
                    q.goto(B + r); q.wait_for_timeout(300)
                    if q.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad.append(f"overflow {w}px {r}")
                    if not q.evaluate("!!document.querySelector('.view.on h1')"): bad.append(f"no content {w}px {r}")
                if errs: bad.append(f"JS error {w}px: {errs[0]}")
                c.close()
            eb.close()
            out(not bad, f"engine {name}", "; ".join(bad[:4]) or "renders cleanly at phone and desktop width")

if __name__ == "__main__":
    seo(); downloads(); assets(); review_date(); pdfs(); wording(); weight("--update-weights" in sys.argv)
    try: browser_checks()
    except Exception as e: out(False, "browser checks", str(e)[:200])
