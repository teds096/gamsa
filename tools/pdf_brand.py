#!/usr/bin/env python3
"""Add the GAMSA logo and the blue-white-pink stripe to the downloadable PDFs.

  python3 tools/pdf_brand.py      # (usually via tools/brand.py) needs pymupdf (pip install pymupdf)
Finds each PDF's teal title band, puts the logo (vector, from static/logo.svg) at its right end where no
text is, and draws the gradient stripe under it, as on the site header. Safe to re-run: stamped files are
skipped. Also rebuilds the training package zip from the stamped PDFs.
"""
import pathlib, zipfile
import pymupdf as fitz
R = pathlib.Path(__file__).resolve().parents[1]; S = R / "static"
MARK = "gamsa-brand-5b"
STOPS = [(0x7F, 0xD8, 0xFB), (0xFF, 0xFF, 0xFF), (0xF7, 0xB6, 0xC3)]

def colour(t):
    a, b, u = (STOPS[0], STOPS[1], t * 2) if t < .5 else (STOPS[1], STOPS[2], t * 2 - 1)
    return tuple((a[i] + (b[i] - a[i]) * u) / 255 for i in range(3))

def brand(path, logo):
    d = fitz.open(path)
    kw = d.metadata.get("keywords") or ""
    if MARK in kw: return "already done"
    if "gamsa-logo-5b" in kw: return "logo built into the Word original (tools/docx_brand.py) - nothing to add"
    pg = d[0]
    bands = [dr["rect"] for dr in pg.get_drawings() if dr.get("fill") and dr["rect"].width > pg.rect.width * .5
             and dr["rect"].height > 30 and abs(dr["fill"][0] * 255 - 11) < 3 and abs(dr["fill"][2] * 255 - 122) < 3]
    if not bands: return "no title band found - skipped"
    band = bands[0]
    lines = [fitz.Rect(l["bbox"]) for b in pg.get_text("dict")["blocks"] for l in b.get("lines", []) if fitz.Rect(l["bbox"]).intersects(band)]
    for s in (36, 32, 28, 26):
        x1 = band.x1 - 10; x0 = x1 - s
        mid = (band.y0 + band.y1 - s) / 2   # try the vertical centre first, then step outwards
        for y0 in sorted(range(int(band.y0 + 5), int(band.y1 - 5 - s) + 1), key=lambda y: abs(y - mid)):
            r = fitz.Rect(x0, y0, x1, y0 + s)
            if not any(l.intersects(fitz.Rect(r.x0 - 6, r.y0, r.x1, r.y1)) for l in lines): break
        else: continue
        break
    else: return "no free space in the band - skipped"
    pg.show_pdf_page(r, logo, 0)
    n = 120; w = band.width / n
    for i in range(n):
        pg.draw_rect(fitz.Rect(band.x0 + i * w, band.y1, band.x0 + (i + 1) * w + .3, band.y1 + 3), color=None, fill=colour(i / (n - 1)), width=0)
    m = d.metadata; m["keywords"] = ((m.get("keywords") or "") + " " + MARK).strip(); d.set_metadata(m)
    tmp = path.with_suffix(".tmp.pdf"); d.save(tmp, garbage=3, deflate=True); d.close(); tmp.replace(path)
    return f"logo {int(r.width)} pt at ({int(r.x0)},{int(r.y0)}), stripe added"

def main():
    svg = (S / "logo.svg").read_text().encode()
    logo = fitz.open(stream=fitz.open(stream=svg, filetype="svg").convert_to_pdf(), filetype="pdf")
    pdfs = sorted(S.glob("*/*.pdf"))
    for p in pdfs: print(p.relative_to(S), "-", brand(p, logo))
    z = S / "clinicians/testosterone-undecanoate-im-training-package.zip"
    if z.exists():
        names = zipfile.ZipFile(z).namelist()
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as out:
            for n in names: out.write(S / "clinicians" / n, n)
        print("training package zip rebuilt:", len(names), "files")

if __name__ == "__main__":
    main()
