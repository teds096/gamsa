#!/usr/bin/env python3
"""GAMSA one-step local site check. Run from the repo root:  python3 tools/site_check.py

Builds the site, then runs every local check and prints a PASS/FAIL summary:
  1. data drift guard (scraper/check.py) and build
  2. static checks: sitemap files exist, feed.xml valid, CSP hashes, no template tokens,
     every markdown link in content renders, references consistent, dist file sizes
  3. behaviour tests on the single-file preview (tools/test.py) and real paths (tools/pathtest.py)
  4. axe (WCAG 2.0/2.1 A+AA + best practice) on every route, light and dark; JS errors;
     one h1; titles; noopener; overflow at 360px (tools/audit.py)
  5. phones and iPads, portrait and landscape: overflow, 24px tap targets, menu, a11y panel (tools/devices.py)
  6. tools/extra_checks.py: SEO, download links, PDFs (pages, QR codes), wording, page weight,
     search quality, keyboard-only use, print layout, Safari (WebKit) and Firefox engines
  7. optional: pass the release zip path to check its contents match the repo
Flags: --update-weights resets the page-weight baseline after an intended size change.
Needs: python3, playwright (chromium), axe-core in node_modules (npm i axe-core). Set CHROME=/path
to use a specific Chromium. Live-site, analytics, GitHub, database and outside-link checks are in
the gamsa-site-check skill (they need Chrome, Cloudflare and GitHub access, not this script).
"""
import subprocess, sys, json, re, glob, pathlib, time, os, signal, xml.dom.minidom as m

ROOT = pathlib.Path(__file__).resolve().parents[1]; os.chdir(ROOT)
res = []
def step(name, ok, detail=""):
    res.append((name, ok, detail)); print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)
def run(cmd, timeout=900):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout); return p.returncode, (p.stdout + p.stderr)

if not pathlib.Path("node_modules/axe-core/axe.min.js").exists(): run("npm i --no-save --silent axe-core")
c, o = run("python3 scraper/check.py"); step("data drift guard", c == 0, o.strip().splitlines()[-1] if o.strip() else "")
c, o = run("python3 build.py"); step("build", c == 0, o.strip().splitlines()[-1] if o.strip() else "")

D = pathlib.Path("dist")
sm = re.findall(r"<loc>https://gamsa.au(/[^<]*)</loc>", (D/"sitemap.xml").read_text())
miss = [u for u in sm if not (D/("index.html" if u == "/" else u.strip("/")+".html")).exists()]
step("sitemap pages exist", not miss, f"{len(sm)} URLs" + (f", missing {miss}" if miss else ""))
try: n = len(m.parse(str(D/"feed.xml")).getElementsByTagName("item")); step("feed.xml valid", True, f"{n} items")
except Exception as e: step("feed.xml valid", False, str(e))
step("CSP script hashes", (D/"_headers").read_text().count("sha256-") >= 2)
tok = [f.name for f in D.rglob("*.html") if re.search(r"\{\{|__[A-Z]+__", f.read_text())]
step("no leftover template tokens", not tok, ", ".join(tok[:5]))
pat = re.compile(r"\[(?!\d[\d,\s]*\])[^\]]+\]\((#/[a-z0-9/-]*(#[a-z0-9-]+)?|/(clinicians|allies)/[a-z0-9-]+\.(pdf|zip)|https://[^\s)]+|/medicines/[a-z0-9-]+(#[a-z0-9-]+)?)\)")
badlinks, badrefs = [], []
for f in glob.glob("content/*.json"):
    c = json.load(open(f)); txt = json.dumps(c, ensure_ascii=False)
    badlinks += [f+": "+x.group(0)[:60] for x in re.finditer(r"\[[^\]]*\]\([^)]*\)", txt) if not pat.fullmatch(x.group(0))]
    if "sections" in c:
        refs = {r["n"] for r in c.get("references", [])}; cited = set()
        for g in re.findall(r"\[(\d+(?:,\s*\d+)*)\]", json.dumps(c["sections"], ensure_ascii=False)): cited |= {int(x) for x in g.split(",")}
        if cited - refs: badrefs.append(f"{f} cites missing {sorted(cited-refs)}")
        if refs - cited: badrefs.append(f"{f} never cites {sorted(refs-cited)}")
step("content links render", not badlinks, "; ".join(badlinks[:3]))
step("references consistent", not badrefs, "; ".join(badrefs[:3]))
for f in pathlib.Path("static").rglob("*"):
    if f.is_file() and f.suffix in (".pdf", ".zip", ".png", ".ico"):
        d = D/f.relative_to("static")
        if not d.exists() or d.stat().st_size != f.stat().st_size: step("static file copied", False, str(f))

c, o = run("python3 tools/test.py", 600); step("preview behaviour tests", "0 failed" in o, (re.findall(r"\d+ passed, \d+ failed", o) or [o[-200:]])[-1])
srv = subprocess.Popen([sys.executable, "tools/pages_gz.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
try:
    c, o = run("python3 tools/pathtest.py", 600); fails = [l for l in o.splitlines() if l.startswith("FAIL")]
    step("real-path behaviour tests", c == 0 and not fails, f"{o.count('PASS')} passed" + (f"; {fails[:3]}" if fails else ""))
    c, o = run("python3 tools/audit.py", 900); bad = [l for l in o.splitlines() if l.split(" ")[0] in ("axe","jserr","h1","noopener","overflow","title","console") and not l.endswith(" ok")]
    step("accessibility + errors, every route, light and dark", c == 0 and not bad, "; ".join(x[:150] for x in bad) or o.strip().splitlines()[0])
    c, o = run("python3 tools/devices.py", 900); bad = [l for l in o.splitlines() if "'ok'" not in l]
    step("phones and iPads", c == 0 and not bad, "; ".join(x[:150] for x in bad))
    c, o = run("python3 tools/extra_checks.py" + (" --update-weights" if "--update-weights" in sys.argv else ""), 900)
    for l in o.splitlines():
        if l.startswith(("PASS ", "FAIL ")): k, rest = l[:4], l[5:]; name, _, det = rest.partition(" — "); step(name, k == "PASS", det)
        elif l.startswith(("SKIP ", "NOTE ")): print(l)
finally:
    srv.send_signal(signal.SIGTERM)
zarg = [a for a in sys.argv[1:] if a.endswith(".zip")]
if zarg:   # release zip check: python3 tools/site_check.py "path/to/GAC – GAMSA Release vX.zip"
    import zipfile, hashlib
    z = zipfile.ZipFile(zarg[0]); names = set(z.namelist())
    banned = [n for n in ("data/medicines.json", "data/premiums.json", "data/inbox-state.json", "data/status.json") if n in names]
    need = [n for n in ("template.html", "build.py", "data/manual.json", ".github/workflows/refresh.yml", "tools/site_check.py") if n not in names]
    stale = [n for n in names if not n.endswith("/") and pathlib.Path(n).is_file() and z.read(n) != pathlib.Path(n).read_bytes()]
    step("release zip", not banned and not need and not stale, "; ".join(filter(None, [f"contains {banned}" if banned else "", f"missing {need}" if need else "", f"differs from repo {stale[:5]}" if stale else ""])) or f"{len(names)} files, matches repo")
    print("NOTE workflow file in this zip — Ted must paste refresh.yml by hand if it changed since the last release")
f = [r for r in res if not r[1]]
print(f"\n{len(res)-len(f)}/{len(res)} checks passed" + ("" if not f else ": fix " + ", ".join(r[0] for r in f)))
sys.exit(1 if f else 0)
