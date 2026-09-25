#!/usr/bin/env python3
"""Generate the anatomy diagrams for content/administration.json.

Deliberately schematic: a clean mannequin body map rather than an attempt at
realistic anatomy, which is what patient leaflets use and what stays legible at
phone size.
"""
import json, pathlib

INK, DIM, LINE = "#10181F", "#4A5966", "#DCE3E8"
BRAND, BSOFT = "#0B5D7A", "#E6F1F6"
RED, RSOFT = "#A32B25", "#FBEAE8"
AMB, ASOFT = "#8A5B08", "#FDF1DC"
GRN, GSOFT = "#1F6B43", "#E6F3EB"
BODY, BEDGE = "#F6F8FA", "#AEBCC6"
F = 'font-family="Public Sans, sans-serif"'

_UID = [0]

def head(w, h, title, desc):
    _UID[0] += 1
    t, d = f"fig{_UID[0]}t", f"fig{_UID[0]}d"
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" '
            f'aria-labelledby="{t}" aria-describedby="{d}" xmlns="http://www.w3.org/2000/svg">'
            f'<title id="{t}">{title}</title><desc id="{d}">{desc}</desc>')

def _smooth(pts, close=True):
    """Catmull-Rom through pts -> cubic bezier path (symmetric, no kinks)."""
    p = list(pts)
    if close:
        p = [pts[-1]] + pts + [pts[0], pts[1]]
    else:
        p = [pts[0]] + pts + [pts[-1]]
    d = [f"M{p[1][0]:.1f} {p[1][1]:.1f}"]
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}")
    if close:
        d.append("Z")
    return " ".join(d)

# Half silhouette, left side only, measured from the centre line at the neck.
_HALF = [(7, 40), (20, 46), (31, 52),            # shoulder slope
         (39, 62), (43, 96), (41, 122), (37, 133),  # outer arm to hand
         (29, 130), (26, 98), (24, 70),          # inner arm back up to armpit
         (25, 84), (21, 106),                    # waist
         (30, 132), (32, 158),                   # hip
         (28, 198), (24, 236), (21, 258),        # outer leg
         (9, 258), (7, 200), (4, 168), (0, 150)] # inner leg to crotch

def torso(cx, top=0, s=1.0, back=False):
    """A single, symmetric body silhouette: head, shoulders, arms, waist, hips, legs."""
    left = [(cx - x * s, top + y * s) for x, y in _HALF]
    right = [(cx + x * s, top + y * s) for x, y in reversed(_HALF[:-1])]
    body = _smooth(left + right)
    g = [f'<g fill="{BODY}" stroke="{BEDGE}" stroke-width="{1.6 * s:.2f}" stroke-linejoin="round">',
         f'<circle cx="{cx:.1f}" cy="{top + 18 * s:.1f}" r="{14.5 * s:.1f}"/>',
         f'<path d="{body}"/>', '</g>']
    if not back:
        g.append(f'<circle cx="{cx:.1f}" cy="{top + 112 * s:.1f}" r="{2.6 * s:.1f}" fill="{DIM}"/>')
    return "".join(g)

def dot(x, y, n, r=12):
    return (f'<g><circle cx="{x}" cy="{y}" r="{r}" fill="{BSOFT}" stroke="{BRAND}" stroke-width="2"/>'
            f'<text x="{x}" y="{y+5}" {F} font-size="14" font-weight="700" fill="{BRAND}" '
            f'text-anchor="middle">{n}</text></g>')

def avoid(x, y, w, h, label=None, ly=None):
    o = (f'<g><rect x="{x-w/2}" y="{y-h/2}" width="{w}" height="{h}" rx="7" fill="{RSOFT}" '
         f'stroke="{RED}" stroke-width="1.8" stroke-dasharray="5 4"/>'
         f'<path d="M{x-8} {y-8} l16 16 M{x+8} {y-8} l-16 16" stroke="{RED}" stroke-width="2.4" '
         f'stroke-linecap="round" fill="none"/></g>')
    if label:
        o += f'<text x="{x}" y="{ly}" {F} font-size="14" fill="{RED}" text-anchor="middle">{label}</text>'
    return o

def cap(x, y, text, anchor="start", size=14, fill=DIM, weight="400"):
    return (f'<text x="{x}" y="{y}" {F} font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}" font-weight="{weight}">{text}</text>')

def key(x, y, w, rows):
    """Legend panel: list of (swatch-kind, text)."""
    h = 16 + len(rows) * 26
    o = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{BODY}" stroke="{LINE}"/>']
    for i, (kind, text) in enumerate(rows):
        ty = y + 30 + i * 26
        if kind == "num":
            o.append(f'<circle cx="{x+22}" cy="{ty-5}" r="9" fill="{BSOFT}" stroke="{BRAND}" stroke-width="2"/>')
        elif kind == "avoid":
            o.append(f'<rect x="{x+13}" y="{ty-14}" width="18" height="18" rx="4" fill="{RSOFT}" '
                     f'stroke="{RED}" stroke-width="1.6" stroke-dasharray="4 3"/>'
                     f'<path d="M{x+17} {ty-10} l10 10 M{x+27} {ty-10} l-10 10" stroke="{RED}" '
                     f'stroke-width="2" stroke-linecap="round" fill="none"/>')
        elif kind == "area":
            o.append(f'<rect x="{x+13}" y="{ty-14}" width="18" height="18" rx="4" fill="{BSOFT}" '
                     f'stroke="{BRAND}" stroke-width="1.8"/>')
        o.append(cap(x + 42, ty, text, size=14, fill=INK))
    return "".join(o), h

def d_patch():
    w = 400
    o = [head(w, 480, "Where an oestrogen patch goes",
              "Front and back body maps. Numbered spots mark patch sites on the lower belly, "
              "hips and upper outer buttock. Crossed dashed areas mark the chest and beltline, "
              "where a patch should not go.")]
    o.append(cap(0, 18, "Where a patch goes", size=17, fill=INK, weight="700"))
    o.append(cap(0, 38, "Front of the body, facing you", size=14))
    o.append(torso(96, 52, 0.82))
    o.append(avoid(96, 104, 54, 26))
    for i, (dx, dy) in enumerate([(-15, 150), (15, 150)], start=1):
        o.append(dot(96 + dx, dy, i, 11))
    o.append(dot(96 - 27, 174, 3, 11))
    o.append(dot(96 + 27, 174, 4, 11))
    o.append(cap(96, 292, "Estradot: on the abdomen", size=13.5, anchor="middle"))
    o.append(cap(96, 312, "Not the chest or the beltline", size=13.5, fill=RED, anchor="middle"))

    o.append(cap(230, 38, "Back of the body", size=14))
    o.append(torso(300, 52, 0.82, back=True))
    o.append(dot(300 - 22, 172, 5, 11))
    o.append(dot(300 + 22, 172, 6, 11))
    o.append(cap(300, 292, "Estraderm MX: on the buttock", size=13.5, anchor="middle"))

    k, h = key(0, 336, w, [("num", "A patch goes here — clean, dry, hair-free skin"),
                           ("num", "Move to the next number each time you change it"),
                           ("avoid", "Never here: a waistband or belt rubs a patch off")])
    o.append(k)
    return "".join(o) + "</svg>"

def d_gel():
    w = 400
    o = [head(w, 470, "Where testosterone gel goes",
              "Front body map. Shaded areas on the shoulders, upper arms and belly mark where "
              "gel is applied. Crossed dashed areas mark the upper chest and genitals.")]
    o.append(cap(0, 18, "Where the gel goes", size=17, fill=INK, weight="700"))
    o.append(cap(0, 38, "Testosterone gel. Front of the body, facing you.", size=14))
    o.append(torso(150, 52, 1.0))
    # apply areas: both shoulders and upper arms
    for sx in (-1, 1):
        o.append(f'<rect x="{150 + sx * 44 - 15}" y="{52 + 54}" width="30" height="62" rx="14" '
                 f'fill="{BSOFT}" stroke="{BRAND}" stroke-width="1.8"/>')
    o.append(avoid(150, 52 + 78, 46, 24))
    o.append(avoid(150, 52 + 150, 38, 22))
    o.append(cap(238, 118, "Shoulders and", size=14, fill=BRAND))
    o.append(cap(238, 136, "upper arms", size=14, fill=BRAND))
    o.append(cap(238, 162, "Not the upper chest", size=14, fill=RED))
    o.append(cap(238, 216, "Not the genitals", size=14, fill=RED))
    k, h = key(0, 332, w, [("area", "Apply to clean, dry, unbroken skin"),
                           ("avoid", "Never here"),
                           ("num", "Let it dry, then cover with clothing")])
    o.append(k)
    o.append(cap(0, 332 + h + 20, "Oestrogen gel uses different areas — follow your own leaflet.", size=13.5))
    return "".join(o) + "</svg>"

def d_hip():
    w, BONE = 400, "#E7ECF0"
    o = [head(w, 620, "Where the long-acting injection goes",
              "The right hip seen from the side. The hip bone and the top of the thigh bone are "
              "drawn inside the body outline. A hand is placed over them with the index and "
              "middle fingers spread apart, and the injection site sits between the fingertips, "
              "above the bony knob of the thigh bone.")]
    o.append(cap(0, 18, "Where the long-acting injection goes", size=17, fill=INK, weight="700"))
    o.append(cap(0, 38, "The ventrogluteal site \u2014 the side of the hip", size=14))

    # body outline: waist, hip flare, buttock curve, tapering thigh
    o.append(f'<path d="M162 58 C150 78 138 98 130 122 C120 152 118 184 124 214 '
             f'C131 248 142 274 148 304 C154 338 152 392 152 440 L238 440 '
             f'C238 392 240 340 246 306 C252 274 266 248 274 216 '
             f'C282 184 280 150 268 120 C260 96 250 76 242 58 Z" '
             f'fill="{BODY}" stroke="{BEDGE}" stroke-width="2" stroke-linejoin="round"/>')
    # hip bone (ilium), femoral head, greater trochanter, thigh bone
    o.append(f'<path d="M158 108 C194 94 228 98 248 116 C254 152 250 194 236 222 '
             f'C218 250 182 252 166 236 C152 204 150 148 158 108 Z" '
             f'fill="{BONE}" stroke="{DIM}" stroke-width="1.8" stroke-linejoin="round"/>')
    o.append(f'<path d="M198 292 L208 440" stroke="{DIM}" stroke-width="19" stroke-linecap="round" fill="none"/>')
    o.append(f'<path d="M198 292 L208 440" stroke="{BONE}" stroke-width="15" stroke-linecap="round" fill="none"/>')
    o.append(f'<circle cx="208" cy="266" r="20" fill="{BONE}" stroke="{DIM}" stroke-width="1.8"/>')
    o.append(f'<circle cx="172" cy="278" r="18" fill="{BONE}" stroke="{DIM}" stroke-width="1.8"/>')

    # the triangle between the three bony landmarks
    crest, asis, troch = (178, 120), (244, 130), (172, 278)
    o.append(f'<path d="M{crest[0]} {crest[1]} L{asis[0]} {asis[1]} L{troch[0]} {troch[1]} Z" '
             f'fill="{BSOFT}" fill-opacity="0.85" stroke="{BRAND}" stroke-width="2.4" '
             f'stroke-dasharray="7 5" stroke-linejoin="round"/>')
    for (x, y) in (crest, asis, troch):
        o.append(f'<circle cx="{x}" cy="{y}" r="6" fill="{INK}"/>')

    # injection site, in the middle of the triangle
    o.append(f'<circle cx="197" cy="184" r="12" fill="{BRAND}"/>')
    o.append(f'<path d="M112 184 h71" stroke="{BRAND}" stroke-width="2.2" fill="none"/>')
    o.append(f'<path d="M183 178 l12 6 -12 6 Z" fill="{BRAND}"/>')
    o.append(cap(108, 172, "Injection site", size=14, fill=BRAND, weight="700", anchor="end"))

    # labels
    o.append(f'<path d="M116 118 h56" stroke="{DIM}" stroke-width="1.4" fill="none"/>')
    o.append(cap(112, 104, "Top ridge of hip", size=13, fill=INK, anchor="end"))
    o.append(cap(112, 120, "bone (iliac crest)", size=13, anchor="end"))
    o.append(f'<path d="M250 130 h32" stroke="{DIM}" stroke-width="1.4" fill="none"/>')
    o.append(cap(286, 108, "Front point of", size=13, fill=INK))
    o.append(cap(286, 124, "hip bone (ASIS)", size=13))
    o.append(f'<path d="M190 278 h92" stroke="{DIM}" stroke-width="1.4" fill="none"/>')
    o.append(cap(286, 262, "Bony knob of", size=13, fill=INK))
    o.append(cap(286, 278, "thigh bone", size=13))
    o.append(cap(286, 294, "(trochanter)", size=13))

    rows = [("1", "Palm flat on the bony knob, fingers pointing up"),
            ("2", "Index finger on the front point of the hip bone"),
            ("3", "Spread your middle finger back along the top ridge"),
            ("t", "Needle into the V between them, straight in at 90\u00b0")]
    ky, h = 468, 16 + len(rows) * 30
    o.append(f'<rect x="0" y="{ky}" width="{w}" height="{h}" rx="9" fill="{BODY}" stroke="{LINE}"/>')
    for i, (kind, text) in enumerate(rows):
        cy = ky + 30 + i * 30
        if kind == "t":
            o.append(f'<circle cx="26" cy="{cy-5}" r="9" fill="{BRAND}"/>')
        else:
            o.append(dot(26, cy - 5, kind, 11))
        o.append(cap(50, cy, text, size=14, fill=INK))
    o.append(cap(0, ky + h + 26, "Use the hand opposite the hip: right hand on the left hip.", size=14))
    return "".join(o) + "</svg>"


def d_adjunct():
    w = 400
    rows = [(["Acne"], "Topical retinoid with benzoyl peroxide; doxycycline; isotretinoin for severe acne"),
            (["Scalp hair", "loss"], "Topical minoxidil; finasteride in some cases"),
            (["Periods still", "coming"], "Norethisterone; medroxyprogesterone; a hormonal IUD"),
            (["Vaginal", "dryness"], "Low-dose vaginal oestrogen")]
    rh, top = 78, 96
    h = top + rh * len(rows) + 54
    o = [head(w, h, "Other medicines used alongside hormone therapy",
              "Four rows pair a common effect of hormone therapy with the medicines used for it: "
              "acne, scalp hair loss, periods continuing, and vaginal dryness.")]
    o.append(cap(0, 18, "What else might be prescribed", size=17, fill=INK, weight="700"))
    o.append(cap(0, 38, "These treat effects of hormone therapy. They are not", size=14))
    o.append(cap(0, 56, "hormone therapy themselves, and none is automatic.", size=14))
    o.append(cap(0, 84, "THE EFFECT", size=11.5, fill=DIM, weight="700"))
    o.append(cap(140, 84, "WHAT MAY BE OFFERED", size=11.5, fill=DIM, weight="700"))
    for i, (eff, opts) in enumerate(rows):
        y = top + i * rh
        o.append(f'<rect x="0" y="{y}" width="{w}" height="{rh-10}" rx="12" fill="{BODY}" stroke="{LINE}"/>')
        o.append(f'<rect x="0" y="{y}" width="5" height="{rh-10}" rx="2.5" fill="{BRAND}"/>')
        for k, part in enumerate(eff):
            o.append(cap(16, y + 26 + k * 17, part, size=14.5, fill=INK, weight="700"))
        words, line, lines = opts.split(" "), "", []
        for wd in words:
            if len(line + " " + wd) > 31:
                lines.append(line); line = wd
            else:
                line = (line + " " + wd).strip()
        lines.append(line)
        for j, ln in enumerate(lines[:3]):
            o.append(cap(140, y + 26 + j * 17, ln, size=13.5, fill=DIM))
    o.append(cap(0, h - 26, "Ask your prescriber which, if any, is right for you.", size=13.5, fill=DIM))
    return "".join(o) + "</svg>"

def d_layers():
    w = 400
    o = [head(w, 400, "Under the skin versus into the muscle",
              "A cross-section of skin, fat and muscle drawn to a millimetre scale. A short "
              "needle at 45 degrees stops in the fat layer. A longer needle at 90 degrees "
              "reaches the muscle.")]
    o.append(cap(0, 18, "Under the skin, or into the muscle", size=17, fill=INK, weight="700"))
    y0, H = 74, 150
    bands = [("Skin", "#E9EDF0", 18), ("Fat", "#FBF3E4", 62), ("Muscle", "#F2E4E3", 70)]
    y = y0
    for name, fill, h in bands:
        o.append(f'<rect x="0" y="{y}" width="290" height="{h}" fill="{fill}" stroke="{LINE}"/>')
        o.append(cap(8, y + h / 2 + 5, name, size=14, fill=DIM, weight="600"))
        y += h
    # scale
    o.append(f'<line x1="300" y1="{y0}" x2="300" y2="{y0+H}" stroke="{DIM}" stroke-width="1.4"/>')
    for mm, yy in [(0, y0), (10, y0 + 50), (20, y0 + 100), (30, y0 + 150)]:
        o.append(f'<line x1="296" y1="{yy}" x2="304" y2="{yy}" stroke="{DIM}" stroke-width="1.4"/>')
        o.append(cap(310, yy + 5, f"{mm} mm", size=12.5))
    # needle A: 45 deg, stops in fat
    o.append(f'<line x1="70" y1="{y0-20}" x2="118" y2="{y0+48}" stroke="{BRAND}" stroke-width="3.4" '
             f'stroke-linecap="round"/>')
    o.append(f'<circle cx="118" cy="{y0+48}" r="4" fill="{BRAND}"/>')
    o.append(cap(0, 42, "A  45°, short needle", size=13.5, fill=BRAND, weight="600"))
    # needle B: 90 deg into muscle
    o.append(f'<line x1="220" y1="{y0-20}" x2="220" y2="{y0+118}" stroke="{GRN}" stroke-width="3.4" '
             f'stroke-linecap="round"/>')
    o.append(f'<circle cx="220" cy="{y0+118}" r="4" fill="{GRN}"/>')
    o.append(cap(180, 42, "B  90°, longer needle", size=13.5, fill=GRN, weight="600"))
    o.append(cap(0, y0 + H + 30, "A — under the skin (subcutaneous): the medicine sits", size=13.5, fill=INK))
    o.append(cap(0, y0 + H + 52, "in the fat and is taken up slowly.", size=13.5, fill=INK))
    o.append(cap(0, y0 + H + 96, "B — into the muscle (intramuscular): the needle goes", size=13.5, fill=INK))
    o.append(cap(0, y0 + H + 118, "through the fat into the muscle.", size=13.5, fill=INK))
    o.append(cap(0, y0 + H + 146, "Your needle length is set by the person who trains you.", size=13.5, fill=DIM))
    return "".join(o) + "</svg>"

def d_rotate():
    w = 400
    o = [head(w, 440, "Rotating your injection sites",
              "Front body map with six numbered injection sites: four around the belly, avoiding "
              "the navel, and one on the middle third of each thigh. An arrow strip shows the "
              "order one to six and back to one.")]
    o.append(cap(0, 18, "Rotate your sites", size=17, fill=INK, weight="700"))
    o.append(cap(0, 38, "Use the next number each time. Front of the body, facing you.", size=14))
    cx, top = 150, 52
    o.append(torso(cx, top, 1.0))
    for n, (dx, dy) in [(1, (-30, 92)), (2, (30, 92)), (3, (-30, 120)), (4, (30, 120))]:
        o.append(dot(cx + dx, top + dy, n, 12))
    o.append(dot(cx - 22, top + 196, 5, 12))
    o.append(dot(cx + 22, top + 196, 6, 12))
    o.append(cap(252, 140, "Around the belly,", size=14, fill=DIM))
    o.append(cap(252, 158, "clear of the navel", size=14, fill=DIM))
    o.append(cap(252, 250, "Middle third", size=14, fill=DIM))
    o.append(cap(252, 268, "of each thigh", size=14, fill=DIM))
    # order strip
    sy = 352
    o.append(f'<rect x="0" y="{sy-24}" width="{w}" height="52" rx="9" fill="{BODY}" stroke="{LINE}"/>')
    for i in range(6):
        x = 34 + i * 60
        o.append(dot(x, sy, i + 1, 11))
        if i < 5:
            o.append(f'<path d="M{x+15} {sy} h22" stroke="{BRAND}" stroke-width="1.8" fill="none" '
                     f'marker-end="url(#ar)"/>')
    o.append(f'<defs><marker id="ar" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">'
             f'<path d="M0 0 L7 3.5 L0 7 z" fill="{BRAND}"/></marker></defs>')
    o.append(cap(w, sy + 36, "then back to 1", size=13, anchor="end"))
    return "".join(o) + "</svg>"

DIAGRAMS = {
    "Other medicines used alongside hormone therapy": (d_adjunct, "The effects of hormone therapy that are commonly treated, and the medicines Australian guidance names for each. Based on the Australian position statement, AusPATH standards of care and RACGP guidance."),
    "Putting on and changing a patch": (d_patch, "Where an oestrogen patch goes, and where it should not. Based on the Royal Children's Hospital patch information sheet and the Estradot Consumer Medicine Information."),
    "Applying gel, and keeping it off other people": (d_gel, "Where testosterone gel is applied, and the areas to keep it away from. Based on the Testogel Consumer Medicine Information (Besins Healthcare) and TransHub guidance."),
    "Your long-acting injection: finding the right spot": (d_hip, "The side of the hip (ventrogluteal site) and the three bony landmarks that locate it. Based on SA Health's long-acting intramuscular injections brochure and factsheet."),
    "Learning to inject testosterone yourself": (d_layers, "Under the skin versus into the muscle, drawn to a millimetre scale. Based on the Fenway Health transgender health injection guide."),
    "Doing the injection, and what to watch for": (d_rotate, "Rotating injection sites around the belly and thighs. Based on the Fenway Health transgender health injection guide."),
}

def _apply(p):
    d = json.loads(p.read_text())
    n = 0
    for s in d["sections"]:
        if s["h"] in DIAGRAMS:
            fn, capn = DIAGRAMS[s["h"]]
            s["svg"] = fn()
            s["svgCaption"] = capn
            n += 1
    p.write_text(json.dumps(d, ensure_ascii=False))
    print(f"replaced {n} diagrams")


if __name__ == "__main__":
    for fname in ("administration", "dosing"):
        _apply(pathlib.Path(__file__).parent / f"content/{fname}.json")
