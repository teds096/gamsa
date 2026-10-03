#!/usr/bin/env python3
"""Make the share images in static/og/ (1200x630 JPEG) for the hubs, key pages and every medicine.
Run after adding or renaming a medicine:  python3 tools/og_images.py   (needs Pillow and DejaVu fonts)
Pages without their own image fall back to /og-image.png (build.py picks static/og/<path>.jpg if it exists).
"""
from PIL import Image, ImageDraw, ImageFont
import json, pathlib, textwrap
R = pathlib.Path(__file__).resolve().parents[1]
OUT = R / "static/og"
FONT_DIRS = ["/usr/share/fonts/truetype/dejavu/", "/Library/Fonts/", "/System/Library/Fonts/Supplemental/"]
def font(bold, size):
    for d in FONT_DIRS:
        for n in (("DejaVuSans-Bold.ttf", "Arial Bold.ttf") if bold else ("DejaVuSans.ttf", "Arial.ttf")):
            p = pathlib.Path(d) / n
            if p.exists(): return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()
def hx(h): return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
FLAG = ("#7FD8FB", "#F7B6C3")
PAGES = {"trans": ("For trans and gender diverse people", "Medicines, supply, costs and support in SA", ("#7FD8FB", "#FFFFFF")),
         "clinicians": ("For clinicians and pharmacists", "Prescribing, PBS Authority, monitoring and supply", ("#1C7A5E", "#9EDFC6")),
         "allies": ("For family, friends and allies", "How to help someone get and use their medicines", ("#B04A66", "#F7B6C3")),
         "resources": ("Resources and support", "Services, guides and downloads in South Australia", ("#6E5BB8", "#C9BEF5")),
         "supply": ("Medicine supply and shortages", "Checked every day against the TGA", FLAG),
         "costs": ("PBS costs", "What each medicine costs and how to pay less", FLAG),
         "medicines": ("Medicines A–Z", "Every gender-affirming medicine available in Australia", FLAG)}
def main():
    OUT.mkdir(exist_ok=True)
    base = Image.open(R / "static/og-image.png").convert("RGB")
    tl, tr, bl = [base.getpixel(p) for p in ((5, 5), (1195, 5), (5, 625))]
    br = tuple(int(bl[i] * .4 + tr[i] * .6) for i in range(3))
    s = Image.new("RGB", (2, 2)); s.putdata([tl, tr, bl, br]); bg = s.resize((1200, 630), Image.BILINEAR)
    d = ImageDraw.Draw(bg); cross = base.getpixel((990, 300))
    d.rounded_rectangle((934, 243, 1046, 700), radius=56, fill=cross); d.rounded_rectangle((793, 384, 1187, 496), radius=56, fill=cross)
    tile = base.crop((80, 96, 176, 192))
    def make(slug, title, sub, stops):
        im = bg.copy(); d = ImageDraw.Draw(im); im.paste(tile, (80, 80))
        d.text((196, 104), "GAMSA", font=font(1, 34), fill="white")
        d.text((196, 146), "Gender-Affirming Medicines South Australia", font=font(0, 22), fill="#CFE6EF")
        a, b = map(hx, stops)
        for x in range(360):
            t = x / 359; d.line([(80 + x, 214), (80 + x, 222)], fill=tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)))
        size = 72 if len(title) < 22 else 60 if len(title) < 34 else 50
        y = 250
        for line in textwrap.wrap(title, width=int(1450 / size))[:3]:
            d.text((80, y), line, font=font(1, size), fill="white"); y += int(size * 1.18)
        d.text((80, y + 18), sub, font=font(0, 28), fill="#DCEBF3")
        d.text((80, 560), "gamsa.au", font=font(1, 26), fill="white")
        im.save(OUT / f"{slug}.jpg", quality=85, optimize=True, progressive=True)
    for k, (t, s2, c) in PAGES.items(): make(k, t, s2, c)
    meds = json.loads((R / "content/medicines.json").read_text())["medicines"]
    for m in meds: make("medicines-" + m["id"], m["name"].split(" (")[0], "Doses, cost, supply and how to use it", FLAG)
    print(f"{len(PAGES) + len(meds)} share images written to static/og/")
if __name__ == "__main__":
    main()
