import os, pathlib as _pl
CHROME=os.environ.get("CHROME") or None
_ax=_pl.Path("node_modules/axe-core/axe.min.js")
AXE=_ax.read_text() if _ax.exists() else ""
from playwright.sync_api import sync_playwright
import pathlib,json,sys
axe=AXE
B="http://127.0.0.1:8767"
D=pathlib.Path("dist")
routes=["/"]+["/"+p.stem for p in D.glob("*.html") if p.stem not in ("index","404")]
routes+=["/medicines/"+p.stem for p in (D/"medicines").glob("*.html")]
routes+=["/easy/"+p.stem for p in (D/"easy").glob("*.html")]
res={"axe":{}, "jserr":{}, "h1":[], "noopener":[], "overflow":[], "title":[], "console":{}}
with sync_playwright() as p:
    b=p.chromium.launch(**({"executable_path":CHROME} if CHROME else {}))
    for theme in ("light","dark"):
        ctx=b.new_context(viewport={"width":1280,"height":900},bypass_csp=True); ctx.route("**/*", lambda route: route.abort() if "127.0.0.1" not in route.request.url else route.continue_())
        pg=ctx.new_page()
        if theme=="dark": pg.add_init_script("try{localStorage.setItem('gamsa.theme','dark')}catch(e){}")
        errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)[:100]))
        cons=[]; pg.on("console", lambda m: cons.append(m.text[:100]) if m.type=="error" and "ERR_" not in m.text and "Failed to load" not in m.text else None)
        for r in routes:
            errs.clear(); cons.clear()
            pg.goto(B+r); pg.wait_for_timeout(150)
            pg.add_script_tag(content=axe)
            v=pg.evaluate("axe.run(document,{runOnly:['wcag2a','wcag2aa','wcag21aa','best-practice']})")["violations"]
            if v: res["axe"][theme+r]=[(x["id"],len(x["nodes"]),x["nodes"][0]["html"][:70]) for x in v]
            if errs: res["jserr"][theme+r]=list(errs)
            if cons: res["console"][theme+r]=list(cons)
            if theme=="light":
                n=pg.evaluate("document.querySelectorAll('.view.on h1').length")
                if n!=1: res["h1"].append((r,n))
                t=pg.title()
                if not t or "undefined" in t or "GAMSA" not in t: res["title"].append((r,t))
                bad=pg.evaluate("Array.from(document.querySelectorAll('.view.on a[target=_blank]')).filter(a=>!/noopener/.test(a.rel)).length")
                if bad: res["noopener"].append((r,bad))
        ctx.close()
    ctx=b.new_context(viewport={"width":360,"height":780},bypass_csp=True); ctx.route("**/*", lambda route: route.abort() if "127.0.0.1" not in route.request.url else route.continue_()); m=ctx.new_page()
    for r in routes:
        m.goto(B+r); m.wait_for_timeout(120)
        if m.evaluate("document.documentElement.scrollWidth>window.innerWidth+1"): res["overflow"].append(r)
    b.close()
print(len(routes),"routes")
for k,v in res.items(): print(k, v if v else "ok")
