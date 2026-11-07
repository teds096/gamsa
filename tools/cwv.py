#!/usr/bin/env python3
"""Core Web Vitals in the lab (v19.5, 7 Nov 2026): LCP and CLS for every sitemap route, light mode, CPU slowed 4x.

  python3 tools/cwv.py [--routes /supply /] [--fast] [--json out.json]

Needs the local server on 127.0.0.1:8767 (tools/pages_gz.py) and CHROME as in CLAUDE.md. CLS is the largest
session window (shifts less than 1 s apart, at most 5 s long, ignoring shifts after input), measured while the page
loads, settles, and then scrolls to the bottom. tools/extra_checks.py uses measure() for its "layout shift" check."""
import json, os, re, sys, pathlib

B = "http://127.0.0.1:8767"
ROOT = pathlib.Path(__file__).resolve().parent.parent
VIEWPORTS = {"phone": (390, 844), "desktop": (1280, 800)}
INIT = r"""(()=>{window.__cwv={lcp:0,shifts:[]};try{localStorage.clear()}catch(e){}
try{new PerformanceObserver(l=>{for(const e of l.getEntries())__cwv.lcp=e.startTime}).observe({type:'largest-contentful-paint',buffered:true})}catch(e){}
try{new PerformanceObserver(l=>{for(const e of l.getEntries())if(!e.hadRecentInput)__cwv.shifts.push([e.startTime,e.value,
 (e.sources||[]).slice(0,3).map(s=>{const n=s.node;return n&&n.nodeType===1?(n.tagName.toLowerCase()+(n.id?'#'+n.id:'')+(n.className&&typeof n.className==='string'?'.'+n.className.trim().split(/\s+/).slice(0,2).join('.'):'')):(n?n.nodeName:'?')}).join(' ')])}).observe({type:'layout-shift',buffered:true})}catch(e){}})();"""
CLS_JS = r"""(()=>{let best=0,cur=0,start=0,last=-1e9,who='';let bw='',cw='';for(const [t,v,s] of __cwv.shifts){if(t-last>1000||t-start>5000){cur=0;start=t;cw=''}cur+=v;last=t;if(v>0.01&&cw.length<200)cw+=(cw?' | ':'')+s+' '+v.toFixed(3);if(cur>best){best=cur;bw=cw}}return {cls:best,lcp:__cwv.lcp,who:bw}})()"""

def routes_from_sitemap():
    x = (ROOT / "dist/sitemap.xml").read_text()
    return sorted({re.sub(r"^https?://[^/]+", "", u) or "/" for u in re.findall(r"<loc>([^<]+)</loc>", x)})

def measure(browser, routes, viewports=VIEWPORTS, throttle=4, settle=1200, net=False):
    res = []
    for vn, (w, h) in viewports.items():
        ctx = browser.new_context(viewport={"width": w, "height": h}, color_scheme="light", device_scale_factor=1)
        ctx.add_init_script(INIT)
        ctx.route("**/*", lambda r: r.abort() if "127.0.0.1" not in r.request.url else r.continue_())
        pg = ctx.new_page()
        cdp = ctx.new_cdp_session(pg)
        if throttle: cdp.send("Emulation.setCPUThrottlingRate", {"rate": throttle})
        if net:   # roughly "slow 4G": 150 ms round trip, 1.6 Mbit/s down (the local server answers at once otherwise)
            cdp.send("Network.enable"); cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 150, "downloadThroughput": 200000, "uploadThroughput": 90000})
        for r in routes:
            try:
                pg.goto(B + r, wait_until="load"); pg.wait_for_timeout(settle)
                pg.evaluate("""async()=>{const H=()=>document.documentElement.scrollHeight;for(let y=0;y<H();y+=innerHeight*0.8){scrollTo(0,y);await new Promise(r=>setTimeout(r,120))}scrollTo(0,H());await new Promise(r=>setTimeout(r,600))}""")
                m = pg.evaluate(CLS_JS)
                res.append({"route": r, "vp": vn, "cls": round(m["cls"], 3), "lcp": round(m["lcp"] / 1000, 2), "who": m["who"]})
            except Exception as e:
                res.append({"route": r, "vp": vn, "cls": None, "lcp": None, "who": "error: " + str(e)[:80]})
        ctx.close()
    return res

if __name__ == "__main__":
    import argparse
    from playwright.sync_api import sync_playwright
    ap = argparse.ArgumentParser(); ap.add_argument("--routes", nargs="*"); ap.add_argument("--json"); ap.add_argument("--fast", action="store_true"); ap.add_argument("--net", action="store_true")
    a = ap.parse_args()
    rs = a.routes or routes_from_sitemap()
    with sync_playwright() as p:
        CH = os.environ.get("CHROME") or None
        b = p.chromium.launch(**({"executable_path": CH} if CH else {}))
        out = measure(b, rs, throttle=0 if a.fast else 4, net=a.net); b.close()
    for x in out:
        flag = "  <-- " if (x["cls"] or 0) > 0.05 or (x["lcp"] or 0) > 2.5 else ""
        print(f'{x["vp"]:7} {x["route"]:45} CLS {x["cls"]}  LCP {x["lcp"]}s{flag}{"  " + x["who"] if flag else ""}')
    if a.json: pathlib.Path(a.json).write_text(json.dumps(out, indent=1))
