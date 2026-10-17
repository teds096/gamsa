#!/usr/bin/env python3
"""Brand images: share images from the logo (static/logo.svg); favicon.ico and the home-screen icon from the tab icon masters.

  python3 tools/og_images.py        # (usually via tools/brand.py) needs Pillow and Playwright's Chromium (CHROME=/path if not bundled)
  python3 tools/og_images.py icons  # favicon.ico and apple-touch-icon.png only
Writes static/og-image.png (site-wide share image), static/og/*.jpg (hubs, key pages, every medicine),
static/favicon.ico and static/apple-touch-icon.png. Tab icon N8 "Adaptive 5b cross" (v18.1.1, 15 Oct 2026), no tile:
  static/favicon-master.svg = the tab icon (template.html line 4 is this file as a data URI): teal keyline, bar teal in light
    tabs (.L) and white in dark tabs (.D); favicon.ico (no media query there) takes the white-bar art (.D): 16 and 32 px from this 16 grid,
  static/apple-touch-icon-master.svg = the 64 master on the teal tile (iOS shows a transparent icon on black): apple-touch-icon.png (180),
    and its inner 64 art, without the tile, is favicon.ico's 48 px. static/mask-icon.svg is Safari's pinned-tab silhouette (hand-drawn).
Icons are drawn at 4-16x and box-filtered down (same as the design round's ship.py, so the files come out byte-identical).
Run after adding or renaming a medicine or hub, or after any logo, icon or palette change.
"""
import io, json, os, pathlib, re, sys, textwrap
from PIL import Image, ImageDraw, ImageFont
R = pathlib.Path(__file__).resolve().parents[1]
S = R / "static"; OUT = S / "og"
TEAL, DEEP, BLUE, PINK = "#0B5D7A", "#08485E", "#7FD8FB", "#F7B6C3"
HUB = {"trans": ("#2A6F92", BLUE), "clinicians": ("#2D6E62", "#8FD1C0"), "allies": ("#F7B6C3", "#8C4A86"), "resources": (BLUE, PINK)}
FLAG = (BLUE, PINK)

def font(bold, size):
    for d in ("/usr/share/fonts/truetype/dejavu/", "/Library/Fonts/", "/System/Library/Fonts/Supplemental/"):
        for n in (("DejaVuSans-Bold.ttf", "Arial Bold.ttf") if bold else ("DejaVuSans.ttf", "Arial.ttf")):
            if (pathlib.Path(d) / n).exists(): return ImageFont.truetype(str(pathlib.Path(d) / n), size)
    return ImageFont.load_default()

def render(svg, px, transparent=True, ss=1):
    """svg at px x px; ss > 1 draws it ss times larger and box-filters it down (crisper small icons)"""
    from playwright.sync_api import sync_playwright
    n = px * ss
    with sync_playwright() as p:
        kw = {"executable_path": os.environ["CHROME"]} if os.environ.get("CHROME") else {}
        b = p.chromium.launch(**kw); pg = b.new_page(viewport={"width": n, "height": n})
        pg.set_content(f"<style>html,body{{margin:0;background:transparent}}svg{{width:{n}px;height:{n}px;display:block}}</style>{svg}")
        img = Image.open(io.BytesIO(pg.screenshot(omit_background=transparent))).convert("RGBA"); b.close()
    return img if ss == 1 else img.resize((px, px), Image.BOX)

def icons():
    """favicon.ico (16/32/48, white-bar art) and apple-touch-icon.png (180, teal tile) from the N8 masters"""
    fav, tile = (S / "favicon-master.svg").read_text(), (S / "apple-touch-icon-master.svg").read_text()
    dark = re.search(r'<g class="D">(.*?)</g></svg>', fav, re.S).group(1)
    a16 = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">{dark}</svg>'
    a64 = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">' + re.search(r'<g transform="translate\(6\.4 6\.4\) scale\(\.8\)">(.*)</g></svg>', tile, re.S).group(1) + "</svg>"
    f16, f32, f48 = render(a16, 16, ss=16), render(a16, 32, ss=8), render(a64, 48, ss=4)
    f48.save(S / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)], append_images=[f16, f32])
    render(re.sub(r' width="64" height="64"', "", tile, count=1), 180, ss=4).convert("RGB").save(S / "apple-touch-icon.png")

def hx(h): return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))

def background():
    w, h = 1200, 630
    g = Image.new("RGB", (w, h)); px = g.load(); a, b = hx(DEEP), hx("#136182")
    for y in range(h):
        for x in range(0, w, 4):
            t = min(1, max(0, (x * .45 + y) / (w * .45 + h)))
            c = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
            for k in range(4):
                if x + k < w: px[x + k, y] = c
    return g

def main():
    OUT.mkdir(exist_ok=True)
    logo = (S / "logo.svg").read_text()
    big = render(logo, 112)
    faint = render(logo.replace('<rect x="1.5" y="1.5" width="61" height="61" rx="14" fill="#0B5D7A"/>', ""), 460)
    faint.putalpha(faint.getchannel("A").point(lambda v: int(v * .13)))
    bg = background(); bg.paste(faint, (760, 150), faint)
    def make(path, title, sub, stops):
        im = bg.copy(); d = ImageDraw.Draw(im); im.paste(big, (72, 66), big)
        d.text((204, 92), "GAMSA", font=font(1, 40), fill="white")
        d.text((204, 142), "Gender-Affirming Medicines South Australia", font=font(0, 23), fill="#CFE6EF")
        a, b = map(hx, stops)
        for x in range(380):
            t = x / 379; d.line([(80 + x, 214), (80 + x, 222)], fill=tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)))
        size = 72 if len(title) < 22 else 60 if len(title) < 34 else 50; y = 252
        for line in textwrap.wrap(title, width=int(1450 / size))[:3]:
            d.text((80, y), line, font=font(1, size), fill="white"); y += int(size * 1.18)
        d.text((80, y + 18), sub, font=font(0, 28), fill="#DCEBF3")
        d.text((80, 560), "gamsa.au", font=font(1, 26), fill="white")
        im.save(path, **({"quality": 85, "optimize": True, "progressive": True} if str(path).endswith(".jpg") else {"optimize": True}))
    make(S / "og-image.png", "Gender-affirming medicines in South Australia", "Supply, costs and how to use each medicine", FLAG)
    pages = {"trans": ("For trans and gender diverse people", "Medicines, supply, costs and support in SA", HUB["trans"]),
             "clinicians": ("For clinicians and pharmacists", "Prescribing, PBS Authority, monitoring and supply", HUB["clinicians"]),
             "allies": ("For family, friends and allies", "How to help someone get and use their medicines", HUB["allies"]),
             "resources": ("Resources and support", "Services, guides and downloads in South Australia", HUB["resources"]),
             "supply": ("Medicine supply and shortages", "Checked every day against the TGA", FLAG),
             "costs": ("PBS costs", "What each medicine costs and how to pay less", FLAG),
             "medicines": ("Medicines A–Z", "Every gender-affirming medicine available in Australia", FLAG)}
    for k, (t, s2, c) in pages.items(): make(OUT / f"{k}.jpg", t, s2, c)
    meds = json.loads((R / "content/medicines.json").read_text())["medicines"]
    for m in meds: make(OUT / f"medicines-{m['id']}.jpg", m["name"].split(" (")[0], "Doses, cost, supply and how to use it", FLAG)
    icons()
    print(f"og-image.png + {len(pages) + len(meds)} share images, favicon.ico, apple-touch-icon.png written")

if __name__ == "__main__":
    if "icons" in sys.argv[1:]: icons(); print("favicon.ico, apple-touch-icon.png written")
    else: main()
