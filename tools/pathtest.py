import os, pathlib as _pl
CHROME=os.environ.get("CHROME") or None
_ax=_pl.Path("node_modules/axe-core/axe.min.js")
AXE=_ax.read_text() if _ax.exists() else ""
from playwright.sync_api import sync_playwright
B="http://127.0.0.1:8767"
ok=[];bad=[]
def chk(c,m): (ok if c else bad).append(m)
with sync_playwright() as pw:
    b=pw.chromium.launch(**({"executable_path":CHROME} if CHROME else {}),args=["--no-sandbox"])
    pg=b.new_page(viewport={"width":1280,"height":900}); errs=[]
    pg.on("pageerror",lambda e: errs.append(str(e)))
    pg.on("response",lambda r: errs.append("HTTP %s %s"%(r.status,r.url)) if r.status>=400 else None)
    pg.on("console",lambda c: errs.append(c.text+" @ "+str(c.location.get("url"))) if (c.type=="error" and "TUNNEL" not in c.text and "fonts" not in c.text) else None)
    # direct load of deep pages
    for path,want in [("/","v-home"),("/costs","v-costs"),("/medicines/spironolactone","v-med"),("/pharmacy","v-pharmacy"),("/easy","v-easy"),("/easy/doses","v-easy-guide")]:
        pg.goto(B+path); pg.wait_for_timeout(600)
        on=pg.evaluate("(document.querySelector('#main .view.on')||{}).id")
        n=pg.evaluate("document.querySelector('#main .view.on').innerText.length")
        chk(on==want and n>500, f"direct load {path} shows {on} ({n} chars)")
    t=pg.evaluate("[document.title, document.querySelector('link[rel=canonical]').href, document.querySelector('meta[name=description]').content.slice(0,60)]")
    chk("Easy Read" in t[0] and t[1]=="https://gamsa.au/easy/doses", f"per-page head {t}")
    # nav click -> real path, no reload
    pg.goto(B+"/"); pg.wait_for_timeout(500)
    pg.evaluate("window.__stay=1")
    pg.click('nav#nav .ng[data-g=tgd] .ng-btn'); pg.wait_for_timeout(150)
    chk(pg.evaluate("document.querySelector('.ng[data-g=tgd]').classList.contains('open')"), "menu group opens on click")
    chk(pg.evaluate("document.querySelectorAll('.ng[data-g=tgd] .ng-col li a').length")>=10, "menu group lists page links")
    pg.click('nav#nav .ng-col a[href="/costs"]'); pg.wait_for_timeout(400)
    chk(not pg.evaluate("document.querySelector('.ng.open')"), "menu closes after choosing a page")
    chk(pg.url.endswith("/costs") and pg.evaluate("window.__stay===1"), f"nav click is in-app to {pg.url}")
    chk(pg.evaluate("document.querySelector('#v-costs').classList.contains('on')"), "costs view showing after nav")
    # rendered content links are real paths
    hrefs=pg.evaluate("[...document.querySelectorAll('#main a')].map(a=>a.getAttribute('href')).filter(h=>h&&h.startsWith('#/'))")
    chk(not hrefs, f"no #/ links left in rendered content ({hrefs[:3]})")
    # citation anchor does not re-route or jump to top
    pg.evaluate("window.scrollTo(0,0)")
    a=pg.query_selector('#v-costs sup a'); href=a.get_attribute("href"); a.click(); pg.wait_for_timeout(600)
    chk(pg.url.endswith("/costs"+href) and pg.evaluate("window.scrollY")>300, f"citation {href} scrolls in place (y={pg.evaluate('window.scrollY')})")
    # back button
    pg.go_back(); pg.wait_for_timeout(300); pg.go_back(); pg.wait_for_timeout(500)
    chk(pg.url.rstrip("/")==B and pg.evaluate("document.querySelector('#v-home').classList.contains('on')"), f"back returns home ({pg.url})")
    # medicine card navigation
    pg.goto(B+"/medicines"); pg.wait_for_timeout(500)
    pg.click('a.mcard[href="/medicines/spironolactone"]'); pg.wait_for_timeout(500)
    chk(pg.url.endswith("/medicines/spironolactone") and "Spironolactone" in pg.title(), f"medicine card -> {pg.url} | {pg.title()}")
    # supply card (data-href) navigation
    pg.goto(B+"/supply"); pg.wait_for_timeout(500)
    c=pg.query_selector('.med[data-href]')
    if c: c.click(); pg.wait_for_timeout(500); chk("/medicines/" in pg.url, f"supply card -> {pg.url}")
    # legacy hash link
    pg.goto(B+"/#/costs"); pg.wait_for_timeout(600)
    chk(pg.url.endswith("/costs") and pg.evaluate("document.querySelector('#v-costs').classList.contains('on')"), f"old link /#/costs -> {pg.url}")
    pg.goto(B+"/#/med/spironolactone"); pg.wait_for_timeout(600)
    chk(pg.url.endswith("/medicines/spironolactone"), f"old link /#/med/x -> {pg.url}")
    # nav current page marker
    chk(pg.evaluate("document.querySelector('nav#nav a[aria-current=page]').getAttribute('href')")=="/medicines", "nav marks Medicines as current on a medicine page")
    chk(pg.evaluate("document.querySelector('.ng.cur .ng-btn').textContent")=="Trans and gender diverse", "menu group marked current")
    # section jump from the menu
    pg.click('nav#nav .ng[data-g=res] .ng-btn'); pg.wait_for_timeout(150)
    pg.click('nav#nav a[href="/resources#sec-resources-1"]'); pg.wait_for_timeout(500)
    chk(pg.url.endswith("/resources#sec-resources-1") and pg.evaluate("document.activeElement.id")=="sec-resources-1", f"menu jump link lands on the section ({pg.url})")
    # site search
    pg.goto(B+"/"); pg.wait_for_timeout(400)
    pg.fill("#siteq","safety net"); pg.press("#siteq","Enter"); pg.wait_for_timeout(500)
    chk(pg.url.endswith("/search?q=safety%20net") and pg.evaluate("document.querySelectorAll('#srOut .sr').length")>3, f"home search shows results ({pg.url})")
    chk(pg.evaluate("document.querySelector('#srOut .sr h2 a').getAttribute('href')").startswith("/"), "search results use real paths")
    pg.fill("#srq","reandron"); pg.press("#srq","Enter"); pg.wait_for_timeout(400)
    chk("reandron" in pg.url and pg.evaluate("document.querySelector('#srOut .sr h2 a').textContent").startswith("Testosterone undecanoate"), "second search re-renders on the same route")
    pg.goto(B+"/search?q=patches"); pg.wait_for_timeout(600)
    chk(pg.evaluate("document.querySelectorAll('#srOut .sr').length")>3, "search URL loads directly with results")
    # dark mode persists
    pg.click("#themeBtn button[data-theme=dark]"); pg.wait_for_timeout(100)
    chk(pg.evaluate("document.documentElement.classList.contains('dark')"), "dark mode switches on")
    pg.goto(B+"/costs"); pg.wait_for_timeout(400)
    chk(pg.evaluate("document.documentElement.classList.contains('dark') && document.querySelector('#themeBtn button[data-theme=dark]').getAttribute('aria-pressed')==='true'"), "dark mode remembered on next page")
    pg.click("#themeBtn button[data-theme=light]"); pg.wait_for_timeout(100)
    chk(pg.evaluate("!document.documentElement.classList.contains('dark')"), "light mode switches back")
    for r in ("/privacy","/accessibility","/disclaimer"):
        pg.goto(B+r); pg.wait_for_timeout(400)
        chk(pg.evaluate("document.querySelectorAll('.view.on section.block').length")>=5, f"{r} renders")
    pg.goto(B+"/costs"); pg.wait_for_timeout(400); pg.evaluate("window.scrollTo(0,1500)"); pg.wait_for_timeout(200)
    chk(pg.evaluate("document.querySelector('header').getBoundingClientRect().top")==0, "header stays at the top when scrolled")
    pg.click("#a11yBtn"); pg.click("#hcBtn"); pg.click("#tsSeg button[data-ts='1.25']"); pg.wait_for_timeout(100)
    chk(pg.evaluate("document.documentElement.classList.contains('hc') && document.documentElement.classList.contains('ts125')"), "high contrast and text size apply")
    pg.goto(B+"/doses"); pg.wait_for_timeout(400)
    chk(pg.evaluate("document.documentElement.classList.contains('hc') && getComputedStyle(document.body).fontSize")=="21px", "accessibility settings persist across pages")
    pg.click("#a11yBtn"); pg.click("#resetBtn"); pg.wait_for_timeout(600)
    chk(pg.evaluate("!document.documentElement.classList.contains('hc') && getComputedStyle(document.body).fontSize")=="17px", "reset all clears settings")
    # new audience pages
    for r in ("/trans","/clinicians","/allies","/clinician-guide","/ally-guide","/resources"):
        pg.goto(B+r); pg.wait_for_timeout(400)
        chk(pg.evaluate("document.querySelector('.view.on h1').textContent").strip()!="" and pg.evaluate("(document.querySelectorAll('.view.on section.block').length>=3||document.querySelectorAll('.view.on .tile').length>=3)"), f"{r} renders sections or tiles")
    chk(pg.evaluate("document.querySelector('.ack p').textContent").startswith("GAMSA acknowledges the Kaurna"), "acknowledgement of country in footer")
    # read-aloud + figure window still work in path mode
    pg.goto(B+"/costs"); pg.wait_for_timeout(600)
    pg.query_selector_all("#v-costs figure")[0].click(); pg.wait_for_timeout(300)
    chk(pg.locator("#figZoom").is_visible(), "diagram window opens in path mode"); pg.click("#lbClose")
    chk(not errs, f"no JS/CSP errors ({errs[:2]})")
    b.close()
print("\n".join("PASS "+m for m in ok)); print("\n".join("FAIL "+m for m in bad) or "ALL PASSED")
