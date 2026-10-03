#!/usr/bin/env python3
"""Build the GAMSA logo and gradient stripe into the clinician Word documents themselves,
so a fresh PDF export already carries them (no stamping needed).

  python3 tools/docx_brand.py "file1.docx" "file2.docx" ...    # edits in place; safe to re-run
Needs python-docx and Pillow; draws the logo from static/logo.svg via og_images.render (Playwright Chromium).
Each document's first table is the teal title band (fill 0B5D7A). A narrow teal cell holding the logo is added
at its right end (before the QR cell on the treatment-room card), and a thin blue-white-pink stripe image is
placed directly under the band. Export to PDF afterwards (LibreOffice: soffice --headless --convert-to pdf).
"""
import copy, io, os, pathlib, sys
from docx import Document
from docx.shared import Pt, Emu
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from PIL import Image
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "tools"))
TAG = "gamsa-logo-5b"

def images():
    import og_images
    logo = io.BytesIO(); og_images.render((R / "static/logo.svg").read_text(), 480).save(logo, "PNG")
    w, h = 2400, 12; im = Image.new("RGB", (w, h)); px = im.load()
    for x in range(w):
        t = x / (w - 1); a, b, u = (("#7FD8FB", "#FFFFFF", t * 2) if t < .5 else ("#FFFFFF", "#F7B6C3", t * 2 - 1))
        A, B = og_images.hx(a), og_images.hx(b)
        for y in range(h): px[x, y] = tuple(int(A[i] + (B[i] - A[i]) * u) for i in range(3))
    stripe = io.BytesIO(); im.save(stripe, "PNG")
    return logo, stripe

def brand(path, logo, stripe):
    d = Document(path)
    if d.core_properties.keywords and TAG in d.core_properties.keywords: return "already done"
    t = d.tables[0]; tbl = t._tbl
    tcs = tbl.findall(qn("w:tr"))[0].findall(qn("w:tc"))
    text_tc = tcs[0]
    cw = Emu(int(Pt(46)))                     # logo cell width
    # grid: shrink the first column, insert a new column after it
    grid = tbl.find(qn("w:tblGrid")); cols = grid.findall(qn("w:gridCol"))
    first = int(cols[0].get(qn("w:w"))); twips = int(cw / 635)
    cols[0].set(qn("w:w"), str(first - twips))
    nc = OxmlElement("w:gridCol"); nc.set(qn("w:w"), str(twips)); cols[0].addnext(nc)
    tcw = text_tc.find(qn("w:tcPr")).find(qn("w:tcW"))
    if tcw is not None and tcw.get(qn("w:type")) == "dxa": tcw.set(qn("w:w"), str(int(tcw.get(qn("w:w"))) - twips))
    new = copy.deepcopy(text_tc)
    for p in new.findall(qn("w:p"))[1:]: new.remove(p)
    p0 = new.find(qn("w:p"))
    for r in list(p0):
        if r.tag != qn("w:pPr"): p0.remove(r)
    pr = new.find(qn("w:tcPr")); w_ = pr.find(qn("w:tcW")); w_.set(qn("w:w"), str(twips)); w_.set(qn("w:type"), "dxa")
    va = pr.find(qn("w:vAlign"))
    if va is None: va = OxmlElement("w:vAlign"); pr.append(va)
    va.set(qn("w:val"), "center")
    text_tc.addnext(new)
    def border(tc, side, colour):
        pr = tc.find(qn("w:tcPr")); b = pr.find(qn("w:tcBorders"))
        if b is None:
            b = OxmlElement("w:tcBorders"); after = [pr.find(qn(x)) for x in ("w:tcW", "w:gridSpan", "w:vMerge")]
            after = [a for a in after if a is not None]
            (after[-1].addnext(b) if after else pr.insert(0, b))   # schema order: tcW, gridSpan, vMerge, tcBorders, shd ...
        e = OxmlElement(f"w:{side}"); e.set(qn("w:val"), "single"); e.set(qn("w:sz"), "4"); e.set(qn("w:color"), colour); b.append(e)
    border(text_tc, "right", "0B5D7A"); border(new, "left", "0B5D7A")
    for c in (text_tc, new): border(c, "bottom", "0B5D7A")   # no white line above the stripe   # no white line between title and logo
    from docx.table import _Cell
    cell = _Cell(new, t); para = cell.paragraphs[0]
    para.alignment = 1; para.paragraph_format.space_before = Pt(0); para.paragraph_format.space_after = Pt(0)
    logo.seek(0); para.add_run().add_picture(logo, width=Pt(30))
    # stripe: a 3 pt row at the bottom of the band table, spanning every column, so it lines up exactly
    ncols = len(tbl.find(qn("w:tblGrid")).findall(qn("w:gridCol")))
    total = sum(int(c.get(qn("w:w"))) for c in tbl.find(qn("w:tblGrid")).findall(qn("w:gridCol")))
    tr = OxmlElement("w:tr"); trPr = OxmlElement("w:trPr"); hh = OxmlElement("w:trHeight")
    hh.set(qn("w:val"), "80"); hh.set(qn("w:hRule"), "exact"); trPr.append(hh); tr.append(trPr)
    tc = OxmlElement("w:tc"); pr = OxmlElement("w:tcPr")
    w_ = OxmlElement("w:tcW"); w_.set(qn("w:w"), str(total)); w_.set(qn("w:type"), "dxa"); pr.append(w_)
    gs = OxmlElement("w:gridSpan"); gs.set(qn("w:val"), str(ncols)); pr.append(gs)
    bd = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        e = OxmlElement(f"w:{side}"); e.set(qn("w:val"), "nil"); bd.append(e)
    pr.append(bd)
    mar = OxmlElement("w:tcMar")
    for side in ("top", "left", "bottom", "right"):
        e = OxmlElement(f"w:{side}"); e.set(qn("w:w"), "0"); e.set(qn("w:type"), "dxa"); mar.append(e)
    pr.append(mar); tc.append(pr); tc.append(OxmlElement("w:p")); tr.append(tc); tbl.append(tr)
    from docx.table import _Cell
    sc = _Cell(tc, t); P = sc.paragraphs[0]; pf = P.paragraph_format
    pf.space_before = Pt(0); pf.space_after = Pt(0); pf.left_indent = Emu(-172 * 635); pf.right_indent = Pt(0); pf.first_line_indent = Pt(0); P.alignment = 0
    stripe.seek(0); run = P.add_run(); run.add_picture(stripe, width=Emu((total + 172) * 635), height=Pt(4))   # LibreOffice draws the band 172 twips wider on the left; run.font.size = Pt(2)
    d.core_properties.keywords = ((d.core_properties.keywords or "") + " " + TAG).strip()
    d.save(path)
    return "logo cell and stripe added"

if __name__ == "__main__":
    logo, stripe = images()
    for f in sys.argv[1:]: print(pathlib.Path(f).name, "-", brand(f, logo, stripe))
