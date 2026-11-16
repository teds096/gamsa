import os, pathlib as _pl
CHROME=os.environ.get("CHROME") or None
_ax=_pl.Path("node_modules/axe-core/axe.min.js")
AXE=_ax.read_text() if _ax.exists() else ""
from playwright.sync_api import sync_playwright
from PIL import Image
axe=AXE
B="http://127.0.0.1:8767"
DEV=[("Android small",360,780,True),("iPhone SE",375,667,True),("iPhone 15",393,852,True),("iPhone SE landscape",667,375,True),("iPhone 15 landscape",852,393,True),("iPad mini portrait",744,1133,True),("iPad portrait",820,1180,True),("iPad landscape",1180,820,True),("iPad Pro portrait",1024,1366,True),("iPad Pro landscape",1366,1024,True),
     # v19.7 (Ted, 13 Nov 2026: all screen sizes): narrow and large phones, small tablet, laptop, desktop and big monitor
     ("Phone 320",320,640,True),("Phone 430",430,932,True),("Small tablet 600",600,960,True),("Laptop 1440",1440,900,True),("Desktop 1920",1920,1080,True),("Big monitor 2560",2560,1440,True),
     # v19.7 screens (14 Nov 2026): very small phone, ultrawide monitor and a short desktop window (phone landscape is already above)
     ("Tiny phone 280",280,653,True),("Ultrawide 3440",3440,1440,True),("Short desktop 1280x600",1280,600,True)]
R=["/","/trans","/clinicians","/allies","/resources","/supply","/costs","/medicines","/medicines/testosterone-undecanoate","/using","/easy/helping","/clinician-guide","/accessibility","/search?q=patches","/feedback"]
TAP="""(()=>{const bad=[];document.querySelectorAll('header a,header button,.view.on button,.view.on .tile,.view.on .chip,.view.on .x-path a,.view.on .x-task,.x-help,footer a').forEach(e=>{const r=e.getBoundingClientRect();if(r.width&&r.height&&getComputedStyle(e).visibility!=='hidden'&&(r.width<24||r.height<24))bad.push((e.id||e.className||e.tagName)+' '+Math.round(r.width)+'x'+Math.round(r.height));});return [...new Set(bad)].slice(0,4)})()"""
# text blocks drawn on top of each other (e.g. the v17.9 phone footer)
OVERLAP="""(()=>{const sel='.view.on h1,.view.on h2,.view.on h3,.view.on p,.view.on li,.view.on .sr,footer p,footer h2,footer li,footer .flags';
const els=[...document.querySelectorAll(sel)].filter(e=>{const r=e.getBoundingClientRect();return r.width>4&&r.height>4&&getComputedStyle(e).visibility!=='hidden'&&(!e.checkVisibility||e.checkVisibility())}).slice(0,500);
const rs=els.map(e=>e.getBoundingClientRect());const bad=[];
for(let i=0;i<els.length;i++)for(let j=i+1;j<els.length;j++){if(els[i].contains(els[j])||els[j].contains(els[i]))continue;const a=rs[i],b=rs[j];
const w=Math.min(a.right,b.right)-Math.max(a.left,b.left),h=Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top);
if(w>6&&h>6)bad.push((els[i].className||els[i].tagName)+' / '+(els[j].className||els[j].tagName));}
return [...new Set(bad)].slice(0,3)})()"""
# chips in a wrapped row must line up and stay inside their box
CHIPS="""(()=>{const box=document.querySelector('.hs-pop');if(!box)return '';const b=box.getBoundingClientRect();const cs=[...box.querySelectorAll('a')].map(a=>a.getBoundingClientRect());
const rows={};cs.forEach(r=>{const k=Math.round(r.top/4);(rows[k]=rows[k]||[]).push(r)});const lefts=Object.values(rows).map(r=>Math.min(...r.map(x=>x.left)));
if(cs.some(r=>r.right>b.right+1))return 'chip past edge';const ks=Object.keys(rows);if(ks.length>1){const firstRowStarts=lefts.slice(1);if(new Set(firstRowStarts.map(Math.round)).size>1)return 'chip rows misaligned'}return ''})()"""
# paragraphs whose lines run past about 82 characters on wide screens (v19.7 screens: reading text is capped at about 78)
LINES="""(()=>{const v=document.querySelector('.view.on');if(!v)return [];const bad=[];[...v.querySelectorAll('p')].filter(p=>p.offsetWidth>0&&p.textContent.trim().length>180&&!p.closest('nav,header,footer,.side,table')).slice(0,40).forEach(p=>{const r=document.createRange();r.selectNodeContents(p);const n=new Set([...r.getClientRects()].map(x=>Math.round(x.top))).size||1;const c=Math.round(p.textContent.trim().length/n);if(c>82)bad.push((p.className||p.parentElement.className||'p')+' '+c)});return [...new Set(bad)].slice(0,3)})()"""
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
            o=pg.evaluate(OVERLAP)
            if o: issues.append("overlapping text "+r+" "+";".join(o))
            if w>=1280:   # v19.7: wide screens keep a readable line length (about 82 characters at most)
                lim=110 if w>=2240 or (w>=1920 and r in ("/about","/accessibility","/disclaimer","/privacy")) else 90 if w>=1600 else 82   # Ted, 16 Nov 2026: B and C, up to 110 characters on very wide screens (two-column pages such as /accessibility from 1920 px)
                ln=pg.evaluate(LINES.replace('if(c>82)',"if(c>(p.classList.contains('note')?110:%d))"%lim))   # Ted, 16 Nov 2026: fill big screens, up to 90 characters from 1600 px; note boxes are as wide as the text (Ted: boxes the same length as the text) in smaller print, so up to 110
                if ln: issues.append("long lines "+r+" "+";".join(ln))
        pg.goto(B+"/"); pg.wait_for_timeout(200)
        pg.add_script_tag(content=axe); v=pg.evaluate("axe.run(document,{runOnly:['wcag2a','wcag2aa','wcag21aa']})")["violations"]
        if v: issues.append("axe "+",".join(x["id"] for x in v))
        c=pg.evaluate(CHIPS)
        if c: issues.append(c)
        pg.evaluate("document.querySelector('footer').scrollIntoView()"); pg.wait_for_timeout(150)
        pg.screenshot(path=f"d_{w}x{h}_footer.png")
        pg.evaluate("scrollTo(0,0)")
        hdr=pg.evaluate("document.querySelector('header').getBoundingClientRect().height")
        menu=pg.evaluate("getComputedStyle(document.getElementById('navbtn')).display")!="none"
        if menu:
            # the Menu button opens the pop-up menu: it must open, lock the page, reach its last link and close with Esc
            pg.tap("#navbtn"); pg.wait_for_timeout(300)
            m=pg.evaluate("""(()=>{const mn=document.getElementById('xMenu');if(!mn||mn.hidden)return {open:false};const p=mn.querySelector('.x-menu-p');const y=scrollY;p.scrollTop=p.scrollHeight;
              const ls=[...p.querySelectorAll('a')].filter(a=>a.offsetParent);const r=ls[ls.length-1].getBoundingClientRect();
              return {open:true,last:r.bottom<=innerHeight+1&&r.top>=0,locked:document.documentElement.classList.contains('x-lock'),pageMoved:scrollY!==y}})()""")
            if not m["open"]: issues.append("menu did not open")
            else:
                if not m["last"]: issues.append("menu: last link cannot be reached")
                if not m["locked"]: issues.append("menu: page behind still scrolls")
            pg.screenshot(path=f"d_{w}_menu.png"); pg.keyboard.press("Escape"); pg.wait_for_timeout(150)
            if not pg.evaluate("document.getElementById('xMenu').hidden"): issues.append("menu: Esc did not close it")
            pg.goto(B+"/"); pg.wait_for_timeout(150)
        pg.tap("#a11yBtn"); pg.wait_for_timeout(150)
        fit=pg.evaluate("(()=>{const r=document.getElementById('a11yPanel').getBoundingClientRect();return r.bottom<=innerHeight+1&&r.right<=innerWidth+1&&r.left>=-1})()")
        if not fit: issues.append("a11y panel off-screen")
        pg.tap("#a11yBtn"); pg.screenshot(path=f"d_{w}.png")
        out[f"{name} {w}x{h}"]={"header":round(hdr),"menuButton":menu,"issues":issues or "ok"}
        ctx.close()
    b.close()
for k,v in out.items(): print(k,v)
# dark mode: figures and Easy Read pictures follow the theme (no light plates); extra_checks.py figures checks them at 3:1
