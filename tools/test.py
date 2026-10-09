import os, pathlib as _pl
CHROME=os.environ.get("CHROME") or None
_ax=_pl.Path("node_modules/axe-core/axe.min.js")
AXE=_ax.read_text() if _ax.exists() else ""
from playwright.sync_api import sync_playwright
import pathlib, json
url="file://"+str(pathlib.Path("preview.html").resolve())
B=CHROME
ROUTES=["#/","#/supply","#/medicines","#/med/spironolactone","#/med/testosterone-undecanoate",
        "#/doses","#/using","#/pharmacy","#/costs","#/easy","#/easy/doses","#/feedback","#/pharmacy-reports","#/sightings"]
fails=[]; notes=[]
def chk(ok, msg):
    (notes if ok else fails).append(("PASS " if ok else "FAIL ")+msg)

with sync_playwright() as pw:
    b=pw.chromium.launch(**({"executable_path":CHROME} if CHROME else {}),args=["--no-sandbox"])

    # ---------- MOBILE ----------
    m=b.new_context(viewport={"width":390,"height":844},device_scale_factor=2,
                    is_mobile=True,has_touch=True,
                    user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
    pg=m.new_page(); errs=[]
    pg.on("pageerror", lambda e: errs.append("mobile: "+str(e)))
    pg.on("console", lambda c: errs.append("mobile console: "+c.text) if (c.type=="error" and "TUNNEL" not in c.text) else None)
    pg.goto(url); pg.wait_for_timeout(900)

    # pill visible + tap target size
    box=pg.locator("#a11yBtn").bounding_box()
    chk(box is not None and box["height"]>=44 and box["width"]>=44,
        "accessibility pill tap target %sx%s (need 44x44)"%(round(box["width"]),round(box["height"])))
    chk(pg.locator("#a11yBtn").is_visible(), "accessibility pill visible on mobile")

    # no horizontal overflow
    ov=pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    chk(ov<=1, "no horizontal scroll on mobile (overflow %spx)"%ov)

    pg.tap("#a11yBtn"); pg.wait_for_timeout(500)
    chk(pg.locator("#a11yPanel").is_visible(), "menu opens on tap")
    pb=pg.locator("#a11yPanel").bounding_box()
    chk(pb["x"]>=0 and pb["x"]+pb["width"]<=391, "menu fits the screen (x=%s w=%s)"%(round(pb["x"]),round(pb["width"])))
    for bid in ["ttsBtn","dysBtn","easyBtn","erLink"]:
        bb=pg.locator("#"+bid).bounding_box()
        chk(bb and bb["height"]>=30, "%s tap target height %s"%(bid, round(bb["height"]) if bb else "none"))

    pg.tap("#dysBtn"); pg.wait_for_timeout(400)
    chk(pg.evaluate("document.body.classList.contains('dys')"), "dyslexia mode on (mobile)")
    chk(pg.evaluate("getComputedStyle(document.body).backgroundColor")=="rgb(252, 249, 240)",
        "dyslexia cream background applied")
    ov=pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    chk(ov<=1, "no overflow with dyslexia mode on (%spx)"%ov)

    pg.tap("#easyBtn"); pg.wait_for_timeout(300)
    chk(pg.evaluate("document.body.classList.contains('easy')"), "bigger-text mode on (mobile)")
    ov=pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    chk(ov<=1, "no overflow with both modes on (%spx)"%ov)
    pg.tap("#dysBtn"); pg.tap("#easyBtn"); pg.wait_for_timeout(200)

    # persistence across reload
    pg.tap("#dysBtn"); pg.wait_for_timeout(200); pg.reload(); pg.wait_for_timeout(900)
    chk(pg.evaluate("document.body.classList.contains('dys')"), "setting remembered after reload")
    pg.tap("#a11yBtn"); pg.wait_for_timeout(400); pg.tap("#dysBtn"); pg.wait_for_timeout(300); pg.tap("#a11yBtn"); pg.wait_for_timeout(300)

    # easy read on mobile
    pg.goto(url+"#/easy"); pg.wait_for_timeout(800)
    chk(pg.eval_on_selector_all("#v-easy .er-card","e=>e.length")>=9, "easy read index renders on mobile")
    ov=pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    chk(ov<=1, "easy read no overflow on mobile (%spx)"%ov)

    # read aloud on mobile
    pg.goto(url+"#/supply"); pg.wait_for_timeout(800)
    pg.evaluate("""() => { window.__c=[]; const s=speechSynthesis;
        s.speak=u=>{ window.__c.push(u.text); setTimeout(()=>u.onend&&u.onend(),1); }; }""")
    pg.tap("#a11yBtn"); pg.wait_for_selector("#a11yPanel:not([hidden])", timeout=5000); pg.wait_for_timeout(200)
    pg.evaluate("""() => { const s=speechSynthesis; s.speak=u=>{ window.__c.push(u.text); setTimeout(()=>u.onend&&u.onend(),40); }; }""")
    pg.tap("#ttsBtn"); pg.wait_for_timeout(700)
    chk(pg.locator("#ttsBar").is_visible(), "speech control bar shows on mobile")
    bb=pg.locator("#ttsToggle").bounding_box() or {"x":-1,"width":0}
    chk(bb["x"]>=0 and bb["x"]+bb["width"]<=391, "speech bar fits the screen")
    pg.evaluate("document.getElementById('ttsMenu').click()"); pg.wait_for_timeout(300)
    pg.evaluate("document.getElementById('ttsNext').click()"); pg.wait_for_timeout(5000)
    c=pg.evaluate("window.__c")
    chk(len(c)>20, "read aloud runs on mobile (%d pieces)"%len(c))
    chk(not any("menu has" in x for x in c[:3]), "read aloud does not start by reading the whole menu")
    chk(any(x.startswith("Site menu") for x in c), "Menu button on the speech bar reads the menu")
    pg.evaluate("document.getElementById('ttsStop').click()")

    # figure window on mobile (touch)
    pg.goto(url+"#/costs"); pg.wait_for_timeout(900)
    figs=pg.query_selector_all("#v-costs figure")
    figs[-2].tap(); pg.wait_for_timeout(500)
    chk(pg.locator("#figZoom").is_visible(), "diagram window opens on tap")
    lbb=pg.locator("#figZoom").bounding_box()
    chk(lbb["x"]>=-1 and lbb["x"]+lbb["width"]<=392, "diagram window fits the screen (x=%s w=%s)"%(round(lbb["x"]),round(lbb["width"])))
    pg.tap("#lbIn"); pg.wait_for_timeout(200)
    chk(pg.locator("#lbLvl").inner_text()!="100%", "zoom in works by tap (%s)"%pg.locator("#lbLvl").inner_text())
    pg.tap("#lbLensBtn"); pg.wait_for_timeout(200)
    chk(pg.evaluate("document.getElementById('lbLensBtn').getAttribute('aria-pressed')")=="true",
        "magnifier toggles on mobile")
    pg.tap("#lbClose"); pg.wait_for_timeout(200)
    chk(not pg.locator("#figZoom").is_visible(), "diagram window closes")
    pg.screenshot(path="/tmp/gamsa-mob.png")

    # ---------- ALL ROUTES, DESKTOP + MOBILE ----------
    d=b.new_context(viewport={"width":1280,"height":900})
    dp=d.new_page()
    dp.on("pageerror", lambda e: errs.append("desktop: "+str(e)))
    dp.on("console", lambda c: errs.append("desktop console: "+c.text) if (c.type=="error" and "TUNNEL" not in c.text) else None)
    for r in ROUTES:
        for page,label,w in ((dp,"desktop",1280),(pg,"mobile",390)):
            page.goto(url+r); page.wait_for_timeout(500)
            vis=page.evaluate("!!document.querySelector('#main .view.on')")
            txt=page.evaluate("(document.querySelector('#main .view.on')||{innerText:''}).innerText.trim().length")
            chk(vis and txt>200, "%s %s renders (%d chars)"%(label,r,txt))
            o=page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            chk(o<=1, "%s %s no horizontal overflow"%(label,r))

    # duplicate ids + a11y basics on desktop
    dp.goto(url+"#/costs"); dp.wait_for_timeout(700)
    dup=dp.evaluate("""() => { const ids={},d=[];
        document.querySelectorAll('[id]').forEach(e=>{ids[e.id]=(ids[e.id]||0)+1;});
        for(const k in ids) if(ids[k]>1) d.push(k+' x'+ids[k]); return d; }""")
    chk(not dup, "no duplicate element ids (%s)"%(", ".join(dup[:5]) or "none"))
    noalt=dp.evaluate("""() => [...document.querySelectorAll('#main svg[role=img]')].filter(s=>!s.querySelector('title')).length""")
    chk(noalt==0, "every diagram has a title for screen readers (%d missing)"%noalt)
    small=dp.evaluate("""() => [...document.querySelectorAll('#main svg text')].filter(t=>parseFloat(t.getAttribute('font-size')||'13')<13).length""")
    chk(small==0, "no diagram text under 13px (%d)"%small)
    links=dp.evaluate("""() => [...document.querySelectorAll('#main a[href^="#"]')].filter(a=>{
        const h=a.getAttribute('href').slice(1);
        return h && !h.startsWith('/') && !document.getElementById(h); }).map(a=>a.getAttribute('href'))""")
    chk(not links, "all in-page citation links resolve (%s)"%(", ".join(links[:4]) or "none"))
    chk(not errs, "no javascript errors (%s)"%(errs[0] if errs else "none"))
    b.close()

print("\n".join(notes))
print()
print("\n".join(fails) if fails else "ALL CHECKS PASSED")
print("\n%d passed, %d failed"%(len(notes),len(fails)))
