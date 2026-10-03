import os, pathlib as _pl
CHROME=os.environ.get("CHROME") or None
_ax=_pl.Path("node_modules/axe-core/axe.min.js")
AXE=_ax.read_text() if _ax.exists() else ""
from playwright.sync_api import sync_playwright
from PIL import Image
axe=AXE
B="http://127.0.0.1:8767"
DEV=[("Android small",360,780,True),("iPhone SE",375,667,True),("iPhone 15",393,852,True),("iPad mini portrait",744,1133,True),("iPad portrait",820,1180,True),("iPad landscape",1180,820,True),("iPad Pro portrait",1024,1366,True),("iPad Pro landscape",1366,1024,True)]
R=["/","/trans","/clinicians","/allies","/resources","/supply","/costs","/medicines","/medicines/testosterone-undecanoate","/using","/easy/helping","/clinician-guide","/accessibility","/search?q=patches","/feedback"]
TAP="""(()=>{const bad=[];document.querySelectorAll('header a,header button,.view.on button,.view.on .tile,.view.on .chip,.view.on .aud .ql a,.view.on .cta,footer a').forEach(e=>{const r=e.getBoundingClientRect();if(r.width&&r.height&&getComputedStyle(e).visibility!=='hidden'&&(r.width<24||r.height<24))bad.push((e.id||e.className||e.tagName)+' '+Math.round(r.width)+'x'+Math.round(r.height));});return [...new Set(bad)].slice(0,4)})()"""
out={}
with sync_playwright() as p:
    b=p.chromium.launch(**({"executable_path":CHROME} if CHROME else {}))
    for name,w,h,touch in DEV:
        ctx=b.new_context(viewport={"width":w,"height":h},device_scale_factor=2,is_mobile=w<1000,has_touch=touch,bypass_csp=True); ctx.route("**/*", lambda r: r.abort() if "127.0.0.1" not in r.request.url else r.continue_()); pg=ctx.new_page()
        issues=[]
        for r in R:
            pg.goto(B+r); pg.wait_for_timeout(200)
            if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): issues.append("overflow "+r)
            t=pg.evaluate(TAP)
            if t: issues.append("small taps "+r+" "+";".join(t))
        pg.goto(B+"/"); pg.wait_for_timeout(200)
        pg.add_script_tag(content=axe); v=pg.evaluate("axe.run(document,{runOnly:['wcag2a','wcag2aa','wcag21aa']})")["violations"]
        if v: issues.append("axe "+",".join(x["id"] for x in v))
        hdr=pg.evaluate("document.querySelector('header').getBoundingClientRect().height")
        menu=pg.evaluate("getComputedStyle(document.getElementById('navbtn')).display")!="none"
        if menu:
            pg.tap("#navbtn"); pg.wait_for_timeout(150); pg.tap('nav#nav .ng[data-g=tgd] .ng-btn'); pg.wait_for_timeout(150)
            if pg.evaluate("document.querySelector('.ng[data-g=tgd] .ng-panel').getBoundingClientRect().height")<50: issues.append("menu group did not open")
            pg.screenshot(path=f"d_{w}_menu.png"); pg.goto(B+"/"); pg.wait_for_timeout(150)
        pg.tap("#a11yBtn"); pg.wait_for_timeout(150)
        fit=pg.evaluate("(()=>{const r=document.getElementById('a11yPanel').getBoundingClientRect();return r.bottom<=innerHeight+1&&r.right<=innerWidth+1&&r.left>=-1})()")
        if not fit: issues.append("a11y panel off-screen")
        pg.tap("#a11yBtn"); pg.screenshot(path=f"d_{w}.png")
        out[f"{name} {w}x{h}"]={"header":round(hdr),"menuButton":menu,"issues":issues or "ok"}
        ctx.close()
    b.close()
for k,v in out.items(): print(k,v)
