#!/usr/bin/env python3
"""GAMSA figure component: infographics as HTML + inline SVG, built from definitions in content/*.json.

Style A "Clear line" (picked by Ted, 16 Oct 2026). A content section carries a "figure" definition (words, numbers
and a small geometry block) instead of a hand-drawn "svg". build.py calls render_content(content); each definition
becomes section["fig"] = {"id", "type", "cap", "html", "er"} in the page payload (cap = raw caption, which the page
script runs through its citation linker; medicine pages show it without the guide's citation numbers):
  html  the page view: <figure class="gf">, title, art (shapes only), every word in HTML, key, steps, notes, caption
  er    the Easy Read panel view of the same figure (one idea per panel), shown inside the Easy Read guides
Art carries role classes only (k-*): no colours, no words. template.html's ".gf" CSS gives weight and colour per
mode (light, dark, high contrast, colour-blind, print). Words are sized with the site's Text size (var(--fs)).
IDs inside a figure start with "gfU"; the page script swaps that for a unique prefix wherever the figure is shown.

Definition (one per figure; see content/administration.json sections 1-6):
  id       unique slug, e.g. "patch-sites"
  type     anatomy | steps | body-map | comparison | table | chart-bar | chart-timeline | list
  title    short title shown on the figure (and read first by Read aloud: "Diagram: title")
  sub      optional line under the title
  alt      text alternative for the drawing, 100 characters or fewer
  long     the long description, shown on the page (what the drawing shows, in words)
  caption  what it is and where it comes from, with the page's citation numbers, e.g. "... [3][1]."
  easy     Easy Read panels: [{"pic": pictogram name, "text": one short sentence}], 3 to 5 of them
  geom     optional geometry for anatomy and body-map art (positions in the art's own units, never colours)
  key      [{"n": pin number, or "sym": spot|site|here|v|next|band|not, "lead": bold words, "term": medical term, "text"}]
  steps, note, views, seq   words for the other parts of the figure (see each renderer below)
Phase 2 (17 Oct 2026) added comparison, table, list, chart-bar and chart-timeline (costs.json, dosing.json). Phase 3 removed
the old hand-drawn "svg" path (and gen_svgs.py): every diagram is a figure definition; extra_checks fails an old "svg".
  rows, axis, legend, items, cols, table, events, curve   words and numbers for the data figures (see the renderers)
"""
import html as _h, json, math, re

TYPES = ("anatomy", "steps", "body-map", "comparison", "table", "chart-bar", "chart-timeline", "list")
LIMIT = 8192          # bytes per figure view (page view and Easy Read view each)
ALT_MAX = 100

E = lambda s: _h.escape(str(s), quote=False)
A = lambda s: _h.escape(str(s), quote=True)


def f(v):
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def n(v):
    """compact number: 1 decimal, no leading zero, no trailing .0"""
    t = f"{v:.1f}".rstrip("0").rstrip(".")
    t = "0" if t in ("-0", "") else t
    return t.replace("0.", ".", 1) if t.startswith(("0.", "-0.")) else t


def nums(*vs):
    out = ""
    for v in vs:
        t = n(v)
        out += t if (not out or t.startswith("-") or (t.startswith(".") and "." in out.split(" ")[-1].split("-")[-1])) else " " + t
    return out


def smooth(pts, close=True):
    """Catmull-Rom through pts -> cubic Bezier path (no kinks), written with relative commands to keep figures small."""
    p = ([pts[-1]] + pts + [pts[0], pts[1]]) if close else ([pts[0]] + pts + [pts[-1]])
    d = ["M" + nums(p[1][0], p[1][1])]
    cx, cy = p[1]
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        # relative to the rounded current point, so rounding errors never add up
        d.append("c" + nums(c1[0] - cx, c1[1] - cy, c2[0] - cx, c2[1] - cy, p2[0] - cx, p2[1] - cy))
        cx, cy = cx + float(n(p2[0] - cx)), cy + float(n(p2[1] - cy))
    if close:
        d.append("z")
    return "".join(d)


def hatch(pid, gap=6):
    """45 degree hatching for "not here" (texture, so the meaning never rests on colour)."""
    return (f'<pattern id="{pid}" width="{gap}" height="{gap}" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
            f'<path class="k-hp" d="M0 0V{gap}"/></pattern>')


def pos(x, y, w, h):
    return f"left:{100 * x / w:.1f}%;top:{100 * y / h:.1f}%"


def svg(vb, inner, cls="", label=None, desc=None, uid=""):
    """Art SVG. With a label it is role=img (title = alt, described by the visible long description)."""
    if label is None:
        return f'<svg viewBox="{vb}" class="{cls}" aria-hidden="true" focusable="false">{inner}</svg>'
    return (f'<svg viewBox="{vb}" class="{cls}" role="img" aria-labelledby="{uid}-a"'
            + (f' aria-describedby="{desc}"' if desc else "") + f'><title id="{uid}-a">{E(label)}</title>{inner}</svg>')


# =====================================================================================================  body (front/back)
# One neutral standing figure, drawn from the centre line (x = 0); y runs down from the top of the head.
# Landmarks: head centre (0,22) r17, nipple line 72, waist 104, navel 108, hips widest 146, crotch 154, knee 212, feet 281.
BODY_W, BODY_H, BODY_GAP = 124, 286, 16
LM = {"navel": (0, 108), "crotch": (0, 154), "waist": 101}
_HALF = [(7.5, 40), (9.5, 47), (22, 52), (34, 57), (41.5, 66), (44, 86), (46.5, 110), (49.5, 134), (51.5, 150),
         (52, 161), (48.5, 168), (43.5, 165), (42, 152), (40, 132), (37.5, 110), (34, 90), (31, 77),
         (29, 90), (26.5, 104), (28.5, 120), (32, 134), (33, 147), (31.5, 166), (28, 194), (25.5, 212),
         (24.5, 232), (21, 256), (17.5, 271), (19.5, 279), (8, 281), (7, 270), (8, 242), (7.5, 214),
         (6, 188), (3.5, 166), (0, 155)]


def body_path(cx):
    L = [(cx - x, y) for x, y in _HALF]
    R = [(cx + x, y) for x, y in reversed(_HALF[:-1])]
    return smooth(L + R)


# named regions on the body (front view unless said); x is from the centre line
REGION = {
    "chest": lambda cx: f'<rect x="{f(cx - 23)}" y="58" width="46" height="29" rx="9"/>',
    "upper-chest": lambda cx: f'<rect x="{f(cx - 21)}" y="58" width="42" height="24" rx="9"/>',
    "groin": lambda cx: f'<rect x="{f(cx - 12)}" y="146" width="24" height="21" rx="8"/>',
    "belly": lambda cx: f'<rect x="{f(cx - 21)}" y="96" width="42" height="41" rx="13"/>',
    "shoulders": lambda cx: "".join(
        f'<path d="{smooth([(cx + s * 12, 51.5), (cx + s * 24, 54.5), (cx + s * 36, 60), (cx + s * 42, 70), (cx + s * 44.2, 88), (cx + s * 45.2, 104), (cx + s * 39, 106), (cx + s * 36, 92), (cx + s * 32.5, 79), (cx + s * 25, 67), (cx + s * 14, 58)])}"/>'
        for s in (-1, 1)),
}


def body_view(view, cx, uid, g):
    """One body (front or back) with its marks. g = geometry block of the figure definition."""
    o = []
    if g.get("arch", True):
        o.append(f'<path class="k-soft" d="M{f(cx - 58)} 281V96A58 58 0 0 1 {f(cx + 58)} 96V281Z"/>')
    o.append(f'<g class="k-body"><circle cx="{f(cx)}" cy="22" r="17"/><path d="{body_path(cx)}"/></g>')
    if view == "front":
        o.append(f'<circle class="k-mark" cx="{f(cx)}" cy="{LM["navel"][1]}" r="2.4"/>')
    else:
        o.append(f'<path class="k-bone" d="M{f(cx)} 128V152"/>')
    for z in g.get("zones", []):
        if z.get("view", "front") != view:
            continue
        shape = REGION[z["region"]](cx)
        if z["kind"] == "here":
            o.append(f'<g class="k-zone">{shape}</g>')
        else:
            hp = f"{uid}-h{view[0]}"
            if f'id="{hp}"' not in "".join(o):
                o.insert(0, f"<defs>{hatch(hp)}</defs>")
            m = re.search(r'x="([\d.-]+)" y="([\d.-]+)" width="([\d.]+)" height="([\d.]+)"', shape)
            x, y, w, h = (float(v) for v in m.groups())
            mx, my, r = x + w / 2, y + h / 2, min(7.0, h / 2 - 3)
            filled = shape.replace("<rect ", '<rect fill="url(#' + hp + ')" ')
            o.append(f'<g class="k-not">{filled}'
                     f'<path class="k-x" d="M{f(mx - r)} {f(my - r)}l{f(2 * r)} {f(2 * r)}m0-{f(2 * r)}-{f(2 * r)} {f(2 * r)}"/></g>')
    for b in g.get("bands", []):
        if b.get("view", "front") == view:
            y = b.get("y", LM["waist"])
            o.append(f'<path class="k-band" d="M{f(cx - 28)} {f(y)}h56"/>')
    for s in g.get("spots", []):
        if s.get("view", "front") == view:
            o.append(f'<circle class="k-spot" cx="{f(cx + s["x"])}" cy="{f(s["y"])}" r="9"/>')
    return "".join(o)


def bodies_art(d, uid, U):
    g = d["geom"]
    views = [v["side"] for v in d["views"]]
    W = BODY_W * len(views) + BODY_GAP * (len(views) - 1)
    inner, pins = [], []
    for i, v in enumerate(views):
        cx = BODY_W / 2 + i * (BODY_W + BODY_GAP)
        inner.append(body_view(v, cx, uid, g))
        for s in g.get("spots", []):
            if s.get("view", "front") == v:
                pins.append(f'<span class="gf-pin" aria-hidden="true" style="{pos(cx + s["x"], s["y"], W, BODY_H)}">{E(s["n"])}</span>')
    art = svg(f"0 0 {W} {BODY_H}", "".join(inner), "", d["alt"], f"{U}-d", U)
    return art, "".join(pins), len(views)


# =====================================================================================================  hip, side view
# Right hip seen from the side, back of the body to the left, front to the right (SA Health brochure view):
# palm on the greater trochanter (1), index finger on the ASIS (2), middle finger back along the iliac crest (3).
HIP_W, HIP_H = 300, 340
HIP = {"troch": (148, 212), "asis": (228, 92), "crest": (138, 62)}
_BACK = [(96, -20), (90, 20), (80, 70), (70, 120), (64, 170), (68, 220), (80, 270), (90, 320), (94, 370)]
_FRONT = [(204, 370), (212, 300), (222, 240), (232, 180), (238, 130), (232, 80), (220, 30), (214, -20)]
_ILIUM = [(108, 100), (122, 72), (150, 54), (186, 58), (214, 74), (228, 92), (218, 108), (200, 128),
          (186, 150), (172, 160), (148, 156), (126, 140), (112, 122)]


def hip_art(d, uid, U):
    g = d.get("geom", {})
    t, a, c = HIP["troch"], HIP["asis"], HIP["crest"]
    s = g.get("site", {"x": 171, "y": 122}); s = (s["x"], s["y"])
    o = [f'<circle class="k-soft" cx="160" cy="166" r="140"/>',
         f'<path class="k-body" d="{smooth(_BACK + _FRONT)}"/>',
         f'<path class="k-bone" d="{smooth(_ILIUM)}"/>',
         '<path class="k-bone" d="M136 224C140 270 150 320 156 372H186C178 320 170 270 164 226Z"/>',
         '<path class="k-bone" d="M140 204L170 166A14 14 0 0 1 192 178L162 218Z"/>',
         f'<circle class="k-bone" cx="{t[0]}" cy="{t[1]}" r="17"/>',
         f'<path class="k-zone" d="M{t[0]} {t[1]}L{a[0]} {a[1]}L{c[0]} {c[1]}Z"/>',
         f'<path class="k-v" d="M{a[0]} {a[1]}L{t[0]} {t[1]}L{c[0]} {c[1]}"/>']
    for k in ("troch", "asis", "crest"):
        x, y = HIP[k]
        o.append(f'<circle class="k-mark" cx="{x}" cy="{y}" r="4.5"/>')
    o.append(f'<circle class="k-site" cx="{s[0]}" cy="{s[1]}" r="7"/>')
    pins = []
    off = {"troch": (-30, 8), "asis": (22, -16), "crest": (-21, -15)}
    for m in d["key"]:
        if m.get("at") in HIP:
            x, y = HIP[m["at"]]; dx, dy = off[m["at"]]
            pins.append(f'<span class="gf-pin" aria-hidden="true" style="{pos(x + dx, y + dy, HIP_W, HIP_H)}">{E(m["n"])}</span>')
    return svg(f"0 0 {HIP_W} {HIP_H}", "".join(o), "", d["alt"], f"{U}-d", U), "".join(pins)


# =====================================================================================================  skin layers
# A slice through skin, fat and muscle, to scale: 5 units = 1 mm, surface at y = 36.
LAY_W, LAY_H, MM, SURF = 320, 196, 5, 36


def layers_art(d, uid, U):
    g = d["geom"]
    lay = g["layers"]               # [{"kind", "name", "to": mm}]
    sc = g["scale"]                 # {"to": mm, "step": mm} (an object: a bare [0, 10, 20] list would read as citations)
    ticks = list(range(0, sc["to"] + 1, sc["step"]))
    y = lambda mm: SURF + MM * mm
    o = [f'<defs><pattern id="{uid}-fat" width="28" height="20" patternUnits="userSpaceOnUse">'
         '<circle class="k-tex" cx="7" cy="6" r="2.8"/><circle class="k-tex" cx="21" cy="15" r="2.8"/></pattern>'
         f'<pattern id="{uid}-mus" width="26" height="9" patternUnits="userSpaceOnUse"><path class="k-tex" d="M2 4.5h18"/></pattern></defs>']
    top = 0
    for i, L in enumerate(lay):
        fill = {"skin": "", "fat": f' fill="url(#{uid}-fat)"', "muscle": f' fill="url(#{uid}-mus)"'}[L["kind"]]
        cls = "k-skin" if L["kind"] == "skin" else "k-layer"
        o.append(f'<rect class="{cls}"{fill} x="0" y="{f(y(top))}" width="{LAY_W - 40}" height="{f(MM * (L["to"] - top))}"/>')
        top = L["to"]
    for mm in [0] + [L["to"] for L in lay[:-1]]:
        o.append(f'<path class="{"k-edge" if mm == 0 else "k-edge2"}" d="M0 {f(y(mm))}H{LAY_W - 40}"/>')
    # depth ruler
    R = LAY_W - 18
    o.append(f'<path class="k-axis" d="M{R} {f(y(0))}V{f(y(ticks[-1]))}"/>')
    for mm in ticks:
        o.append(f'<path class="k-axis" d="M{R - 6} {f(y(mm))}H{R}"/>')
    pins, labels = [], []
    for n in g["needles"]:
        ang = n["angle"]
        tip = (n["x"], y(n["depth"]))
        if ang == 90:
            start = (tip[0], 6)
        else:
            dy = tip[1] - 8
            start = (tip[0] - dy / math.tan(math.radians(ang)), 8)
        ux, uy = tip[0] - start[0], tip[1] - start[1]
        ln = (ux * ux + uy * uy) ** .5
        hub = (start[0] + ux / ln * 12, start[1] + uy / ln * 12)
        o.append(f'<path class="k-needle" d="M{f(start[0])} {f(start[1])}L{f(tip[0])} {f(tip[1])}"/>'
                 f'<path class="k-hub" d="M{f(start[0])} {f(start[1])}L{f(hub[0])} {f(hub[1])}"/>'
                 f'<ellipse class="k-site" cx="{f(tip[0])}" cy="{f(tip[1] + 1)}" rx="6" ry="4.5"/>')
        pins.append(f'<span class="gf-pin" aria-hidden="true" style="{pos(start[0] - 17, start[1] + 6, LAY_W, LAY_H)}">{E(n["n"])}</span>')
    top = 0
    for L in lay:
        mid = (top + min(L["to"], ticks[-1])) / 2
        labels.append(f'<span class="gf-lab" style="{pos(6, y(mid), LAY_W, LAY_H)}">{E(L["name"])}</span>')
        top = L["to"]
    for mm in ticks:
        labels.append(f'<span class="gf-tick" style="right:{100 * (LAY_W - R + 9) / LAY_W:.1f}%;top:{100 * y(mm) / LAY_H:.1f}%">{mm} mm</span>')
    return svg(f"0 0 {LAY_W} {LAY_H}", "".join(o), "", d["alt"], f"{U}-d", U), "".join(pins) + "".join(labels)


# =====================================================================================================  pictograms
# Line pictograms for steps and Easy Read panels (same line as the diagrams). 64 x 64 unless the body crops (64 x 70).
_TORSO = ("M20 17C24 15 40 15 44 17C48 19 50 27 52 40L47 41L43 27L44 44L45 66H34.5L32 50L29.5 66H19L20 44L21 27L17 41L12 40C14 27 16 19 20 17Z")
PICS = {
    "lie": '<circle class="k-p" cx="13" cy="30" r="6"/><rect class="k-p" x="21" y="25" width="35" height="12" rx="6"/>'
           '<path class="k-pl" d="M4 44h56M4 34v18M60 38v14"/>',
    "hip": '<path class="k-pl" d="M18 2C13 22 12 42 16 62M48 2C53 22 52 44 47 62"/><path class="k-za" d="M28 50L46 22L24 14Z"/>'
           '<path class="k-pa" d="M46 22L28 50L24 14"/><circle class="k-pf" cx="33" cy="29" r="4"/>',
    "find": '<path class="k-pl" d="M18 2C13 22 12 42 16 62M48 2C53 22 52 44 47 62"/><path class="k-pa" d="M46 22L28 50L24 14"/>'
            '<circle class="k-pm" cx="28" cy="50" r="3"/><circle class="k-pm" cx="46" cy="22" r="3"/><circle class="k-pm" cx="24" cy="14" r="3"/>',
    "clock": '<circle class="k-p" cx="32" cy="34" r="24"/><path class="k-za" d="M32 34V10A24 24 0 0 1 44 13.2Z"/><path class="k-pl" d="M32 34V18M32 34l10 6M26 4h12"/>',
    "timer": '<circle class="k-p" cx="32" cy="34" r="24"/><path class="k-za" d="M32 34V10A24 24 0 0 1 56 34Z"/><path class="k-pl" d="M32 34V14M32 34h16M26 4h12"/>',
    "plaster": '<g transform="rotate(-30 32 32)"><rect class="k-p" x="6" y="22" width="52" height="20" rx="10"/><rect class="k-pl" x="24" y="25" width="16" height="14" rx="3"/></g>',
    "alert": '<path class="k-p" d="M8 10h48v32H30L18 54V42H8Z"/><path class="k-pa" d="M32 17v12"/><circle class="k-pf" cx="32" cy="35" r="2.6"/>',
    "calendar": '<rect class="k-p" x="8" y="12" width="48" height="44" rx="6"/><path class="k-pl" d="M8 24h48M20 6v12M44 6v12"/><path class="k-pa" d="M22 39l7 7 13-13"/>',
    "cycle": '<path class="k-pl" d="M50 26A20 20 0 0 0 14 22M14 38A20 20 0 0 0 50 42"/><path class="k-pl" d="M14 12v10h10M50 52V42H40"/>'
             '<circle class="k-pf" cx="32" cy="32" r="4"/>',
    "wash": '<path class="k-pl" d="M8 10h22a6 6 0 0 1 6 6v4"/><path class="k-za" d="M36 26c-2 3-3 5-3 6a3 3 0 0 0 6 0c0-1-1-3-3-6z"/>'
            '<path class="k-za" d="M28 36c-2 3-3 5-3 6a3 3 0 0 0 6 0c0-1-1-3-3-6z"/><path class="k-za" d="M44 36c-2 3-3 5-3 6a3 3 0 0 0 6 0c0-1-1-3-3-6z"/>'
            '<path class="k-pl" d="M6 52c6 0 10-6 16-6h10c3 0 3 4 0 4h-6M58 52c-6 0-10-6-16-6h-8M6 58h52"/>',
    "shirt": '<path class="k-p" d="M24 8l-14 8-6 14 9 4 4-8v34h30V26l4 8 9-4-6-14-14-8c-2 5-5 7-8 7s-6-2-8-7z"/>',
    "people": '<circle class="k-p" cx="21" cy="20" r="8"/><path class="k-p" d="M6 54c0-12 7-20 15-20s15 8 15 20z"/>'
              '<circle class="k-p" cx="45" cy="24" r="7"/><path class="k-p" d="M32 56c0-10 6-17 13-17s13 7 13 17z"/>',
    "gel": '<rect class="k-p" x="20" y="22" width="24" height="36" rx="5"/><path class="k-pl" d="M26 22v-8h12v8M38 14h10"/>'
           '<path class="k-za" d="M50 26c-2 3-3 5-3 6a3 3 0 0 0 6 0c0-1-1-3-3-6z"/>',
    "sc": '<path class="k-edge" d="M4 24h56"/><path class="k-edge2" d="M4 30h56M4 46h56"/><path class="k-pl" d="M14 6l18 18 12 12"/><circle class="k-pf" cx="44" cy="36" r="3.5"/>',
    "im": '<path class="k-edge" d="M4 24h56"/><path class="k-edge2" d="M4 30h56M4 46h56"/><path class="k-pl" d="M32 4v50"/><circle class="k-pf" cx="32" cy="54" r="3.5"/>',
}


def _bodypic(view, mode):
    """small body (head to mid-thigh) for Easy Read panels and step icons"""
    o = ['<circle class="k-p" cx="32" cy="8" r="6"/>', f'<path class="k-p" d="{_TORSO}"/>']
    if view == "front":
        o.append('<circle class="k-pm" cx="32" cy="38" r="1.6"/>')
    else:
        o.append('<path class="k-pl" d="M32 44V49" stroke-dasharray="1 3"/>')
    if mode == "patch":
        sp = [(27, 43.5), (37, 43.5)] if view == "front" else [(25.5, 46), (38.5, 46)]   # lower belly / buttocks, as F01 (17 Oct)
        o += [f'<circle class="k-pf" cx="{x}" cy="{y}" r="3"/>' for x, y in sp]
    elif mode == "not-chest":
        o.append('<g class="k-pn"><rect x="22" y="20" width="20" height="13" rx="4"/><path d="M28 23l8 8m0-8-8 8"/></g>')
    elif mode == "not-gel":
        o.append('<g class="k-pn"><rect x="23" y="19" width="18" height="10" rx="4"/><path d="M29 21l6 6m0-6-6 6"/>'
                 '<rect x="26" y="45" width="12" height="9" rx="3"/></g>')
    elif mode == "gel":
        o.append('<path class="k-za" d="M14 25C16 19 20 17 24 17L26 22L19 37L13 36Z"/><path class="k-za" d="M50 25C48 19 44 17 40 17L38 22L45 37L51 36Z"/>'
                 '<rect class="k-za" x="23" y="34" width="18" height="16" rx="6"/>')
    elif mode == "belly":
        o += [f'<circle class="k-pf" cx="{x}" cy="{y}" r="3"/>' for x, y in ((26, 33), (38, 33), (26, 44), (38, 44))]
    elif mode == "thigh":
        o += [f'<circle class="k-pf" cx="{x}" cy="60" r="3"/>' for x in (24.5, 39.5)]
    return '<svg viewBox="0 0 64 70" aria-hidden="true" focusable="false">' + "".join(o) + "</svg>"


def picto(name):
    if ":" in name:
        view, mode = name.split(":")
        return _bodypic(view, mode)
    return '<svg viewBox="0 0 64 64" aria-hidden="true" focusable="false">' + PICS[name] + "</svg>"


# =====================================================================================================  key swatches
def swatch(sym, uid):
    S = {"spot": '<circle class="k-spot k-on" cx="14" cy="14" r="10"/>',
         "site": '<circle class="k-site" cx="14" cy="14" r="7"/>',
         "here": '<rect class="k-zone k-zb" x="3" y="5" width="22" height="18" rx="6"/>',
         "v": '<path class="k-v" d="M6 6l8 17 8-17"/>',
         "next": '<path class="k-arrow" d="M4 14h18m-6-6 6 6-6 6"/>',
         "band": '<path class="k-band" d="M2 14h24"/>',
         "not": f'<defs>{hatch(uid + "-sn", 5)}</defs><g class="k-not"><rect x="3" y="3" width="22" height="22" rx="6" fill="url(#{uid}-sn)"/>'
                '<path class="k-x" d="M9 9l10 10m0-10-10 10"/></g>'}
    return f'<svg viewBox="0 0 28 28" class="gf-sw" aria-hidden="true" focusable="false">{S[sym]}</svg>'


# =====================================================================================================  shared parts
def head(d, U, sub=None):
    s = d.get("sub") if sub is None else sub
    return (f'<div class="gf-hd"><p class="gf-t" id="{U}-t">{E(d["title"])}</p>'
            + (f'<p class="gf-s">{E(s)}</p>' if s else "") + "</div>")


def term(t):
    return f' <span class="gf-term">({E(t)})</span>' if t else ""


def key_list(d, uid):
    items = []
    for i, k in enumerate(d.get("key", [])):
        if k.get("n"):
            mark = f'<span class="gf-pin gf-pin-s{" gf-pa" if k.get("here") else ""}">{E(k["n"])}</span>'
        else:
            mark = swatch(k["sym"], f"{uid}-k{i}")
        lead = k.get("lead", "")
        join = (" " if lead.endswith(":") else ": ") if lead else ""
        body = ((f'<b>{E(lead)}</b>' if lead else "") + term(k.get("term"))
                + (join + E(k["text"]) if k.get("text") else ""))
        items.append(f"<li>{mark}<span>{body}</span></li>")
    return f'<ul class="gf-key" role="list">{"".join(items)}</ul>' if items else ""


def notes(d):
    o = ""
    for n in ([d["note"]] if isinstance(d.get("note"), str) else d.get("note", [])):
        o += f'<p class="gf-note">{E(n)}</p>'
    return o


def wrap(d, U, inner, extra=""):
    if d["type"] in ("steps", "list", "table", "comparison") or ("gf-art" not in inner and "gf-chart" not in inner):   # words only: no Enlarge
        extra += " gf-plain"
    return (f'<figure class="gf gf-{d["type"]}{extra}" data-fig="{A(d["id"])}" aria-labelledby="{U}-t">'
            + inner + f'<figcaption>{E(d["caption"])}</figcaption></figure>')


def long_p(d, U):
    return f'<p class="gf-long" id="{U}-d">{E(d["long"])}</p>'


# =====================================================================================================  renderers (page view)
def r_body_map(d, U):
    art, pins, n = bodies_art(d, U, U)
    sides = "".join(f'<p class="gf-side"><b>{E(v["label"])}</b>' + (f'<span>{E(v["note"])}</span>' if v.get("note") else "") + "</p>"
                    for v in d["views"])
    seq = ""
    if d.get("seq"):
        s = d["seq"]
        # inline chips (so Read aloud hears "Order: 1 2 3 ..."), each arrow kept with the number after it
        ch = [f'<b class="gf-chip">{E(x)}</b>' for x in s["order"]]
        chips = ch[0] + "".join(f' <span class="gf-nw"><span class="gf-arr" aria-hidden="true">→</span> {c}</span>' for c in ch[1:])
        seq = f'<p class="gf-seq"><b>{E(s["label"])}</b> {chips} {E(s["then"])}</p>'
    words = key_list(d, U) + seq + notes(d)
    pic = f'<div class="gf-art gf-bod">{art}{pins}</div><div class="gf-sides">{sides}</div>' + long_p(d, U)
    if n == 1:
        return wrap(d, U, head(d, U) + f'<div class="gf-bd gf-v1 gf-2c"><div class="gf-ac">{pic}</div><div class="gf-tx">{words}</div></div>')
    return wrap(d, U, head(d, U) + f'<div class="gf-bd gf-v{n}">{pic}{words}</div>')


def r_anatomy(d, U):
    if d["art"] == "hip":
        art, pins = hip_art(d, U, U)
        steps = "".join(f"<li>{E(s)}</li>" for s in d.get("steps", []))
        tx = (key_list(d, U) + (f'<p class="gf-h">{E(d["stepsTitle"])}</p><ol class="gf-steps">{steps}</ol>' if steps else "")
              + notes(d))
        return wrap(d, U, head(d, U) + f'<div class="gf-bd gf-2c"><div class="gf-ac"><div class="gf-art gf-hip">{art}{pins}</div>'
                    + long_p(d, U) + f'</div><div class="gf-tx">{tx}</div></div>')
    if d["art"] == "skin-layers":
        art, over = layers_art(d, U, U)
        return wrap(d, U, head(d, U) + f'<div class="gf-bd"><div class="gf-art gf-lay">{art}{over}</div>'
                    + long_p(d, U) + key_list(d, U) + notes(d) + "</div>")
    raise ValueError(f"figure {d['id']}: no art called {d['art']!r}")


def r_steps(d, U):
    items = []
    for s in d["steps"]:
        ic = f'<span class="gf-ic">{picto(s["pic"])}</span>' if s.get("pic") else ""
        lead = f'<b class="gf-warnw">{E(s["warn"])}</b> ' if s.get("warn") else ""
        cls = ' class="gf-warn"' if s.get("warn") else ""
        items.append(f'<li{cls}>{ic}<span>{lead}{E(s["text"])}</span></li>')
    return wrap(d, U, head(d, U, d["long"]).replace('class="gf-s"', f'class="gf-s" id="{U}-d"')
                + f'<div class="gf-bd"><ol class="gf-sl" aria-label="{A(d["alt"])}">{"".join(items)}</ol>' + notes(d) + "</div>")


# =====================================================================================================  phase 2: data figures
# Charts follow C's rules (dataviz): one axis with ticks and units only where they add meaning, proportional scales,
# solid teal marks with 4 px rounded data ends square at the baseline, a 2 px surface gap between touching marks,
# hatching as the backup to colour for "after / not counted", the accent only for "here" (a threshold, a due window,
# the moment to test), direct labels, no chart junk. Marks are HTML (sized in px, so they stay crisp at any width) or
# a small SVG for a curve; they are aria-hidden. Every value is also in the words: each chart row is a list item whose
# text carries its numbers, and a key explains each kind of mark. Lists, comparisons and tables are plain HTML.
PICS.update({
    "tablet": '<path class="k-p" d="M6 26v11c0 6.6 11.7 12 26 12s26 -5.4 26 -12v-11"/><ellipse class="k-p" cx="32" cy="26" rx="26" ry="12"/><path class="k-pl" d="M20.3 21.8L43.7 30.2"/>',
    "same": '<path class="k-p" d="M2 28v7c0 3.9 6.3 7 14 7s14 -3.1 14 -7v-7"/><ellipse class="k-p" cx="16" cy="28" rx="14" ry="7"/><path class="k-pl" d="M9.7 25.6L22.3 30.4"/><path class="k-p" d="M34 28v7c0 3.9 6.3 7 14 7s14 -3.1 14 -7v-7"/><ellipse class="k-p" cx="48" cy="28" rx="14" ry="7"/><path class="k-pl" d="M41.7 25.6L54.3 30.4"/>',
    "differ": '<path class="k-p" d="M3 28v7c0 3.9 6.3 7 14 7s14 -3.1 14 -7v-7"/><ellipse class="k-p" cx="17" cy="28" rx="14" ry="7"/><path class="k-pl" d="M10.7 25.6L23.3 30.4"/><g transform="rotate(-25 47 31)"><rect class="k-p" x="33" y="23" width="28" height="16" rx="8"/><path class="k-pl" d="M47 23v16"/></g>',
    "patch": '<rect class="k-p" x="9" y="14" width="46" height="36" rx="10"/><rect class="k-pl" x="21" y="24" width="22" height="16" rx="4"/>',
    "syringe": '<g transform="rotate(-40 32 32)"><rect class="k-p" x="16" y="25" width="28" height="14" rx="2"/><path class="k-pl" d="M44 32h14M4 32h12M4 26v12M24 25v6M32 25v6"/></g>',
    "tube": '<path class="k-p" d="M24 6h16v42a8 8 0 0 1-16 0z"/><path class="k-za" d="M27 30h10v18a5 5 0 0 1-10 0z"/><path class="k-pl" d="M20 6h24"/>',
    "card": '<rect class="k-p" x="6" y="14" width="52" height="36" rx="6"/><path class="k-pl" d="M6 24h52M14 40h16"/><circle class="k-pf" cx="47" cy="39" r="4"/>',
    "money": '<rect class="k-p" x="6" y="16" width="52" height="32" rx="5"/><circle class="k-pl" cx="32" cy="32" r="8"/><path class="k-pl" d="M15 25v14M49 25v14"/>',
    "tag": '<path class="k-p" d="M8 31V10h21l27 27-19 19z"/><circle class="k-pf" cx="18" cy="20" r="4"/><path class="k-pl" d="M28 38l9-9"/>',
    "shield": '<path class="k-p" d="M32 6l21 8v16c0 13-9 23-21 28C20 53 11 43 11 30V14z"/><path class="k-pa" d="M22 31l7 7 13-13"/>',
    "speak": '<path class="k-p" d="M8 10h48v32H30L18 54V42H8Z"/><path class="k-pl" d="M18 22h28M18 31h18"/>',
    "doc": '<path class="k-p" d="M14 6h25l11 11v41H14z"/><path class="k-pl" d="M39 6v11h11M21 29h22M21 38h22M21 47h13"/>',
    "curve": '<path class="k-pl" d="M8 6v48h50"/><path class="k-pl" d="M12 46C15 20 19 12 24 14S38 38 47 44"/><circle class="k-pf" cx="47" cy="44" r="4.5"/>',
    "pills": '<g transform="rotate(-35 22 22)"><rect class="k-p" x="6" y="14" width="32" height="16" rx="8"/><path class="k-pl" d="M22 14v16"/></g><path class="k-p" d="M25 42v7c0 4.4 7.7 8 17 8s17 -3.6 17 -8v-7"/><ellipse class="k-p" cx="42" cy="42" rx="17" ry="8"/><path class="k-pl" d="M34.4 39.2L49.6 44.8"/>',
})


def num(v):
    """a number from 7.7, "$1,748.20" or {"total": "$277.20", "per": "$7.70"} (how many scripts reach the total)"""
    if isinstance(v, dict):
        return round(num(v["total"]) / num(v["per"]))
    if isinstance(v, str):
        return float(re.sub(r"[^\d.]", "", v))
    return float(v)


def money(v):
    return f"${v:,.2f}"


def rich(s):
    """escape, then **bold** for the numbers that matter"""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", E(s))


def pct(v, lo, hi):
    return f"{100 * (v - lo) / (hi - lo):.2f}".rstrip("0").rstrip(".") + "%"


def axis(ax, extra=""):
    """tick labels under a chart (aria-hidden: the values are in the words) and the axis title"""
    lo, hi, st = ax.get("from", 0), ax["to"], ax["step"]
    ticks, v = [], lo
    while v <= hi + 1e-9:
        t = (ax.get("pre", "") + n(v) + ax.get("post", "")) if not ax.get("names", {}).get(n(v)) else ax["names"][n(v)]
        ticks.append(f'<span style="left:{pct(v, lo, hi)}">{E(t)}</span>')
        v += st
    many = " gf-many" if len(ticks) > 6 else ""        # big text on a phone: every other tick label
    return (f'<div class="gf-ax" aria-hidden="true"><div class="gf-axt{many}">{"".join(ticks)}{extra}</div>'
            + (f'<p class="gf-axl">{E(ax["label"])}</p>' if ax.get("label") else "") + "</div>")


def grid(ax):
    lo, hi, st = ax.get("from", 0), ax["to"], ax["step"]
    out, v = [], lo + st
    while v < hi - 1e-9:
        out.append(f'<i class="gf-g" style="left:{pct(v, lo, hi)}"></i>')
        v += st
    return "".join(out)


def legend(items):
    """key for the kinds of mark (identity never rests on colour: each swatch has a shape or texture as well)"""
    sw = {"bar": '<i class="gf-mk gf-bar"></i>', "hatch": '<i class="gf-mk gf-hat"></i>', "acc": '<i class="gf-mk gf-acch"></i>',
          "thr": '<i class="gf-mk gf-thr"></i>', "dot": '<i class="gf-mk gf-dot"></i>', "ring": '<i class="gf-mk gf-dot gf-ring"></i>',
          "win": '<i class="gf-mk gf-win"></i>', "daily": '<i class="gf-mk gf-daily"></i>', "cont": '<i class="gf-mk gf-cont"></i>'}
    li = "".join(f'<li><span class="gf-lg" aria-hidden="true">{sw[k["mark"]]}</span><span>{rich(k["text"])}</span></li>' for k in items)
    return f'<ul class="gf-key gf-lgd" role="list">{li}</ul>'


def bar_values(d):
    """per chart-bar row: {r1} its first value, {t1} its total in dollars (placeholders for alt, long and the Easy Read words)"""
    out = {}
    for i, r in enumerate(d.get("rows", [])):
        v = [num(s["v"]) for s in r["segs"] if s["k"] != "rest"]
        out[f"{{r{i + 1}}}"], out[f"{{t{i + 1}}}"] = n(v[0]), money(sum(v))
    return out


def fill(d):
    if d.get("type") != "chart-bar":
        return d
    vals = bar_values(d)
    s = json.dumps(d, ensure_ascii=False)
    for k, v in vals.items():
        s = s.replace(k, v)
    return json.loads(s)


def r_chart_bar(d, U):
    """horizontal bars on one proportional axis. rows: [{"label", "text" ({n} = first value), "segs": [{"k": bar|acc|rest,
    "v": number, money or {"total","per"}}], "thr": true (accent threshold at the end of the first segment), "then"}]"""
    ax = d["axis"]; lo, hi = ax.get("from", 0), ax["to"]
    rows = []
    for r in d["rows"]:
        segs, x, first, k = [], lo, None, r["segs"]
        for i, s in enumerate(k):
            if s["k"] == "rest":
                segs.append(f'<i class="gf-mk gf-hat gf-rest" style="left:calc({pct(x, lo, hi)} + 2px)"></i>')
                continue
            v = num(s["v"])
            sq = " gf-sq" if i + 1 < len(k) and k[i + 1]["k"] != "rest" else ""    # only the data end is rounded
            left = "0" if x == lo else f"calc({pct(x, lo, hi)} + 2px)"
            width = pct(v + lo, lo, hi) if x == lo else f"calc({pct(v + lo, lo, hi)} - 2px)"
            segs.append(f'<i class="gf-mk {"gf-bar" if s["k"] == "bar" else "gf-acch"}{sq}" style="left:{left};width:{width}"></i>')
            first = v if first is None else first
            x += v
        if r.get("thr"):
            segs.append(f'<i class="gf-mk gf-thr" style="left:{pct(lo + first, lo, hi)}"></i>')
        total = x - lo
        text = r["text"].replace("{n}", n(first)).replace("{total}", money(total))
        then = f' <span class="gf-then">{rich(r["then"])}</span>' if r.get("then") else ""
        rows.append(f'<li><p class="gf-rl"><b>{E(r["label"])}</b> <span>{rich(text)}</span>{then}</p>'
                    f'<div class="gf-tr" aria-hidden="true">{"".join(segs)}</div></li>')
    body = (f'<div class="gf-chart"><ul class="gf-rows" role="list" aria-label="{A(d["alt"])}">{"".join(rows)}</ul>{axis(ax)}</div>'
            + long_p(d, U) + legend(d.get("legend", [])) + notes(d))
    return wrap(d, U, head(d, U) + f'<div class="gf-bd">{body}</div>')


def r_chart_timeline(d, U):
    """time on one proportional axis. form "rows": one track per row with dose dots, due windows or a daily line;
    form "milestones": one track with events and a dotted carry-on, words in an ordered list; form "curve": a level
    over time (SVG) with numbered pins and a key"""
    ax = d.get("axis", {})
    lo, hi = ax.get("from", 0), ax.get("to", 1)
    if d["form"] == "rows":
        rows = []
        for r in d["rows"]:
            m = [grid(ax)]
            for e in r["marks"]:
                if e["k"] == "daily":
                    m.append('<i class="gf-mk gf-daily"></i>')
                elif e["k"] == "win":
                    m.append(f'<i class="gf-mk gf-win" style="left:{pct(e["from"], lo, hi)};width:{pct(e["to"] - e["from"] + lo, lo, hi)}"></i>')
                else:
                    m.append(f'<i class="gf-mk gf-dot" style="left:{pct(e["at"], lo, hi)}"></i>')
            rows.append(f'<li><p class="gf-rl"><b>{E(r["label"])}</b> <span>{rich(r["text"])}</span></p>'
                        f'<div class="gf-tr gf-tt" aria-hidden="true">{"".join(m)}</div></li>')
        chart = f'<div class="gf-chart"><ul class="gf-rows" role="list" aria-label="{A(d["alt"])}">{"".join(rows)}</ul>{axis(ax)}</div>'
        body = chart + long_p(d, U) + legend(d.get("legend", [])) + notes(d)
    elif d["form"] == "milestones":
        span = ax["to"] - lo
        end = 100 * span / (span + ax.get("more", 0))          # the carry-on part sits after the last tick
        X = lambda v: f"{end * (v - lo) / span:.2f}".rstrip("0").rstrip(".") + "%"
        m = [f'<i class="gf-mk gf-line" style="width:{X(ax["to"])}"></i>', f'<i class="gf-mk gf-cont" style="left:{X(ax["to"])}"></i>']
        for e in d["events"]:
            m.append(f'<i class="gf-mk gf-dot{" gf-ring" if e.get("ring") else ""}" style="left:{X(e["at"])}"></i>')
        ticks = "".join(f'<span style="left:{X(e["at"])}">{E(e["tick"])}</span>' for e in d["events"] if e.get("tick"))
        more = f'<p class="gf-msl" aria-hidden="true">{E(ax["moreLabel"])}</p>' if ax.get("moreLabel") else ""
        items = "".join(f'<li><b>{E(i["lead"])}</b> {rich(i["text"])}</li>' for i in d["items"])
        body = (f'<div class="gf-chart">{more}<div class="gf-tr gf-ms" aria-hidden="true">{"".join(m)}</div>'
                f'<div class="gf-ax" aria-hidden="true"><div class="gf-axt">{ticks}</div>'
                + (f'<p class="gf-axl">{E(ax["label"])}</p>' if ax.get("label") else "") + '</div></div>'
                + long_p(d, U) + f'<ol class="gf-mi" aria-label="{A(d["alt"])}">{items}</ol>'
                + legend(d.get("legend", [])) + notes(d))
    else:  # curve
        c = d["curve"]; W, H = 600, 200
        pts = [(p["x"] * W / 100, p["y"] * H / 100) for p in c["points"]]
        path = smooth(pts, close=False)
        base = c.get("base", 92) * H / 100
        o = [f'<path class="k-axis" d="M6 4V{n(base)}H{W - 4}"/>', f'<path class="k-line" d="{path}"/>']
        for g in c.get("guides", []):
            o.append(f'<path class="k-guide" d="M{n(g["x"] * W / 100)} 8V{n(base)}"/>')
        art = svg(f"0 0 {W} {H}", "".join(o), "", d["alt"], f"{U}-d", U).replace("<svg ", '<svg preserveAspectRatio="none" ', 1)
        pins = []
        for k in d["key"]:
            if k.get("at"):
                p = k["at"]
                pins.append(f'<i class="gf-mk gf-dot{" gf-acd" if k.get("here") else " gf-ring"}" style="left:{p["x"]}%;top:{p["y"]}%"></i>'
                            f'<span class="gf-pin{" gf-pa" if k.get("here") else ""}" aria-hidden="true" '
                            f'style="left:calc({p["x"]}% + {p.get("dx", 0)}px);top:calc({p["y"]}% + {p.get("dy", -24)}px)">{E(k["n"])}</span>')
        labs = "".join(f'<span class="gf-lab gf-cl" style="left:{l["x"]}%;top:{l["y"]}%">{E(l["text"])}</span>' for l in c.get("labels", []))
        ticks = "".join(f'<span style="left:{t["x"]}%">{E(t["text"])}</span>' for t in c.get("ticks", []))
        body = ((f'<p class="gf-axl gf-axy" aria-hidden="true">{E(c["ylabel"])}</p>' if c.get("ylabel") else "")
                + f'<div class="gf-art gf-cv">{art}{"".join(pins)}{labs}</div>'
                + f'<div class="gf-ax gf-axc" aria-hidden="true"><div class="gf-axt">{ticks}</div>'
                + (f'<p class="gf-axl">{E(c["xlabel"])}</p>' if c.get("xlabel") else "") + "</div>"
                + long_p(d, U) + key_list(d, U) + notes(d))
    return wrap(d, U, head(d, U) + f'<div class="gf-bd">{body}</div>')


def r_comparison(d, U):
    """side-by-side columns (2 or 3), each with a line pictogram, a head, an optional big line and a list"""
    cols = []
    for c in d["cols"]:
        cols.append(f'<li><div class="gf-chd">' + (f'<span class="gf-ic">{picto(c["pic"])}</span>' if c.get("pic") else "")
                    + f'<p class="gf-cn">{E(c["head"])}</p></div>'
                    + (f'<p class="gf-hero">{E(c["hero"])}</p>' if c.get("hero") else "")
                    + '<ul class="gf-cli">' + "".join(f"<li>{rich(i)}</li>" for i in c["items"]) + "</ul></li>")
    body = (f'<ul class="gf-cmp gf-c{len(cols)}" role="list" aria-label="{A(d["alt"])}">{"".join(cols)}</ul>'
            + notes(d))
    return wrap(d, U, head(d, U, d["long"]).replace('class="gf-s"', f'class="gf-s" id="{U}-d"') + f'<div class="gf-bd">{body}</div>')


def r_table(d, U):
    t = d["table"]
    th = "".join(f'<th scope="col">{E(h)}</th>' for h in t["head"])
    tr = "".join("<tr>" + "".join((f'<th scope="row">{rich(c)}</th>' if j == 0 else f"<td>{rich(c)}</td>") for j, c in enumerate(r)) + "</tr>"
                 for r in t["rows"])
    body = (f'<div class="gf-tw"><table class="gf-tb" aria-label="{A(d["alt"])}"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>'
            + notes(d))
    return wrap(d, U, head(d, U, d["long"]).replace('class="gf-s"', f'class="gf-s" id="{U}-d"') + f'<div class="gf-bd">{body}</div>')


def r_list(d, U):
    """an ordered list of questions (or points), each with its answers: [{"q", "opts": [{"a": "Yes", "text"}]}]"""
    items = []
    for it in d["items"]:
        opts = "".join(f'<li><b class="gf-a">{E(o["a"])}</b> <span>{rich(o["text"])}</span></li>' for o in it.get("opts", []))
        items.append(f'<li><p class="gf-qq">{rich(it["q"])}</p>' + (f'<ul class="gf-opt" role="list">{opts}</ul>' if opts else "") + "</li>")
    body = f'<ol class="gf-ql" aria-label="{A(d["alt"])}">{"".join(items)}</ol>' + notes(d)
    return wrap(d, U, head(d, U, d["long"]).replace('class="gf-s"', f'class="gf-s" id="{U}-d"') + f'<div class="gf-bd">{body}</div>')


RENDER = {"body-map": r_body_map, "anatomy": r_anatomy, "steps": r_steps, "comparison": r_comparison, "table": r_table,
          "chart-bar": r_chart_bar, "chart-timeline": r_chart_timeline, "list": r_list}


# =====================================================================================================  Easy Read view
def easy(d, U):
    items = "".join(f'<li><span class="gf-pic">{picto(p["pic"])}</span><p>{E(p["text"])}</p></li>' for p in d["easy"])
    title = d.get("easyTitle") or d["title"]
    cap = re.sub(r"\s*\[[0-9][^\]]*\]", "", d["caption"])   # Easy Read guides have no reference list
    return (f'<figure class="gf gf-er gf-plain" data-fig="{A(d["id"])}" aria-labelledby="{U}-et">'
            f'<div class="gf-hd"><p class="gf-t" id="{U}-et">{E(title)}</p></div>'
            f'<ul class="gf-pn" role="list">{items}</ul><figcaption>{E(cap)}</figcaption></figure>')


# =====================================================================================================  checks + entry points
def problems(d):
    """schema problems for one definition (build fails on these; size and alt length are checked by extra_checks.py)"""
    p = []
    for k in ("id", "type", "title", "alt", "long", "caption", "easy"):
        if not d.get(k):
            p.append(f"missing {k}")
    if d.get("type") not in TYPES:
        p.append(f"type {d.get('type')!r} not one of {TYPES}")
    elif d["type"] not in RENDER:
        p.append(f"type {d['type']!r} has no renderer yet")
    for k in ("geom", "views", "key", "seq", "rows", "axis", "events", "curve", "legend"):   # bracketed numbers read as citations
        if re.search(r"\[\d+(?:,\s*\d+)*\]", json.dumps(d.get(k, ""))):
            p.append(f"{k} has a bare list of numbers (use an object, e.g. {{\"x\": 1, \"y\": 2}}): it would read as a citation")
    for c in d.get("cols", []) + [s for s in d.get("steps", []) if isinstance(s, dict)]:
        if c.get("pic") and c["pic"] not in PICS and ":" not in c["pic"]:
            p.append(f"unknown pictogram {c['pic']!r}")
    need = {"chart-bar": ("axis", "rows"), "comparison": ("cols",), "table": ("table",), "list": ("items",)}
    for k in need.get(d.get("type"), ()):
        if not d.get(k):
            p.append(f"missing {k}")
    if d.get("type") == "chart-timeline" and d.get("form") not in ("rows", "milestones", "curve"):
        p.append("chart-timeline needs form rows, milestones or curve")
    for e in d.get("easy", []):
        if e.get("pic") not in PICS and ":" not in e.get("pic", ""):
            p.append(f"unknown pictogram {e.get('pic')!r}")
    return p


def render(d):
    d = fill(d)
    bad = problems(d)
    if bad:
        raise ValueError(f"figure {d.get('id')}: " + "; ".join(bad))
    U = "gfU-" + d["id"]
    return {"id": d["id"], "type": d["type"], "cap": d["caption"], "html": RENDER[d["type"]](d, U), "er": easy(d, U)}


def render_content(content):
    """Replace every section "figure" definition with its rendered "fig". Returns [(id, page bytes, er bytes)]."""
    done, seen = [], set()
    for page in content.values():
        if not isinstance(page, dict):
            continue
        for s in page.get("sections", []):
            d = s.get("figure")
            if not d:
                continue
            if d["id"] in seen:
                raise ValueError(f"figure id {d['id']} used twice")
            seen.add(d["id"])
            r = render(d)
            s["fig"] = r
            del s["figure"]
            done.append((r["id"], len(r["html"].encode()), len(r["er"].encode())))
    return done


if __name__ == "__main__":   # python3 figures.py  -> sizes of every figure in content/
    import pathlib
    R = pathlib.Path(__file__).parent
    c = {p.stem: json.loads(p.read_text()) for p in (R / "content").glob("*.json")}
    for i, a, b in render_content(c):
        print(f"{i:24s} page {a:5d} B  easy {b:5d} B" + ("  OVER 8 KB" if max(a, b) > LIMIT else ""))
