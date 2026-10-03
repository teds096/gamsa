#!/usr/bin/env python3
"""Brand images from the logo (static/logo.svg): share images, favicon.ico and the home-screen icon.

  python3 tools/og_images.py      # (usually via tools/brand.py) needs Pillow and Playwright's Chromium (CHROME=/path if not bundled)
Writes static/og-image.png (site-wide share image), static/og/*.jpg (hubs, key pages, every medicine),
static/favicon.ico (16/32/48, seamless small version) and static/apple-touch-icon.png (180, full-bleed).
Run after adding or renaming a medicine or hub, or after any logo or palette change.
"""
import io, json, os, pathlib, textwrap
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

def render(svg, px, transparent=True):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        kw = {"executable_path": os.environ["CHROME"]} if os.environ.get("CHROME") else {}
        b = p.chromium.launch(**kw); pg = b.new_page(viewport={"width": px, "height": px})
        pg.set_content(f"<style>html,body{{margin:0;background:transparent}}svg{{width:{px}px;height:{px}px;display:block}}</style>{svg}")
        img = Image.open(io.BytesIO(pg.screenshot(omit_background=transparent))).convert("RGBA"); b.close()
    return img

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
    small = logo.replace('<rect x="23.5" y="31" width="17" height="2" fill="#FFFFFF"/>', "")
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
    # icons
    ico = [render(small, n) for n in (16, 32, 48)]
    ico[2].save(S / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)], append_images=ico[:2])
    full = logo.replace('rx="14"', 'rx="0"').replace('x="1.5" y="1.5" width="61" height="61"', 'x="0" y="0" width="64" height="64"')
    render(full, 180, transparent=False).convert("RGB").save(S / "apple-touch-icon.png", optimize=True)
    print(f"og-image.png + {len(pages) + len(meds)} share images, favicon.ico, apple-touch-icon.png written")

if __name__ == "__main__":
    main()
