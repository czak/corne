"""Render keymap.toml to standalone SVGs (combined + one per layer), a local preview page, and the README section.

Key geometry comes from corne/keyboard.py.
"""
from __future__ import annotations

import html
import math
from dataclasses import dataclass

from .keycodes import (LAYER_FNS, MAX_LAYER, QK_LAYER_MOD, QK_LAYER_TAP, QK_MOD_TAP, QK_MODS,
                       QK_ONE_SHOT_MOD, Codec, label, mods_to_str)
from .keyboard import GEOMETRY, POSITIONS
from .layout import Keymap

U = 60          # px per key unit
PAD = 3         # gap between keys (px, each side)
MARGIN = 12
# Keycap top surface inset from the skirt (px); the deeper bottom shade carries the hold label
CAP_SIDE, CAP_TOP, CAP_BOTTOM = 4, 2, 14
# Concave keycap top: the upper rim shades the dish, which brightens toward the bottom; the rim itself catches
# the light (strongest on top). Both are white/black overlays, so they work on any cap color.
GRADIENT_DEFS = """\
  <linearGradient id="dish" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" class="dish-shade"/>
    <stop offset="0.5" class="dish-shade dish-clear"/>
    <stop offset="0.5" class="dish-light dish-clear"/>
    <stop offset="1" class="dish-light"/>
  </linearGradient>
  <linearGradient id="rim" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" class="rim-top"/>
    <stop offset="1" class="rim-bottom"/>
  </linearGradient>"""
RIM = 1.2   # rim highlight stroke width (px), drawn just inside the cap edge

# Layer colors (hue only; lightness set per theme in CSS)
HUES = [220, 15, 165, 280, 45, 200, 330, 100, 0, 250, 130, 60, 300, 185, 35, 260]

MOD_LABELS = {"CTL": "Ctrl", "SFT": "Shift", "ALT": "Alt", "GUI": "Gui"}


# ---------------------------------------------------------------- geometry
@dataclass
class KeyGeom:
    pos: tuple[int, int]
    x: float
    y: float
    w: float
    h: float
    r: float
    rx: float
    ry: float

    def corners(self):
        pts = [(self.x, self.y), (self.x + self.w, self.y),
               (self.x, self.y + self.h), (self.x + self.w, self.y + self.h)]
        a = math.radians(self.r)
        for px, py in pts:
            dx, dy = px - self.rx, py - self.ry
            yield (self.rx + dx * math.cos(a) - dy * math.sin(a),
                   self.ry + dx * math.sin(a) + dy * math.cos(a))


def load_geometry() -> list[KeyGeom]:
    return [KeyGeom(pos, *(list(GEOMETRY[pos]) + [0, 0, 0])[:7]) for pos in POSITIONS]


# ---------------------------------------------------------------- legends
@dataclass
class Legend:
    tap: list[str]            # lines of the main legend
    shifted: str | None = None
    hold: str | None = None
    hold_layer: int | None = None   # hold activates this layer
    kind: str = "key"         # key | none | trns | mod | layer


def _basic_lines(v: int, codec: Codec) -> tuple[list[str], str | None]:
    lab = label(v)
    if lab is None:
        return [codec.decode(v)], None
    parts = lab.split("\n")
    if len(parts) == 2 and all(len(p) == 1 for p in parts):   # keycap pair: shifted over base
        return [parts[1]], parts[0]
    return parts, None


def _mods_label(m: int) -> str:
    s = mods_to_str(m)
    if s in ("MOD_MEH", "MOD_HYPR"):
        return s[4:].capitalize()
    right = m & 0x10
    names = [MOD_LABELS[p[5:]] for p in s.split("|")]
    if right and names == ["Alt"]:
        return "AltGr"
    return ("R" if right else "") + "+".join(names)


def legend(v: int, codec: Codec) -> Legend:
    if v == 0:
        return Legend([], kind="none")
    if v == 1:
        return Legend(["▽"], kind="trns")
    lo = v & 0xFF
    if v <= 0xFF or label(v) is not None:   # basic key, or a named keycode like LCBR
        lines, sh = _basic_lines(v, codec)
        kind = "mod" if 0xE0 <= v <= 0xE7 else "key"
        return Legend(lines, sh, kind=kind)
    if QK_MODS <= v < QK_MOD_TAP:
        lines, _ = _basic_lines(lo, codec)
        return Legend([f"{_mods_label(v >> 8)}+{' '.join(lines)}"])
    if QK_MOD_TAP <= v < QK_LAYER_TAP:
        lines, sh = _basic_lines(lo, codec)
        return Legend(lines, sh, hold=_mods_label(v >> 8))
    if QK_LAYER_TAP <= v < 0x5000:
        layer = (v >> 8) & 0xF
        lines, sh = _basic_lines(lo, codec)
        return Legend(lines, sh, hold=codec.layer_str(layer), hold_layer=layer)
    if QK_LAYER_MOD <= v < 0x5200:
        layer = (v >> 5) & 0xF
        return Legend([], hold=f"{codec.layer_str(layer)}+{_mods_label(v & 0x1F)}", hold_layer=layer, kind="layer")
    if QK_ONE_SHOT_MOD <= v < QK_ONE_SHOT_MOD + 0x20:
        return Legend(["OS " + _mods_label(v & 0x1F)], kind="mod")
    for fn, base in LAYER_FNS.items():
        if base <= v <= base + MAX_LAYER:
            layer = v - base
            return Legend([codec.layer_str(layer)], hold=fn, hold_layer=layer, kind="layer")
    return Legend([codec.decode(v)])


def activators(km: Keymap) -> dict[int, set[tuple[int, int]]]:
    """layer -> base-layer positions whose hold/press activates it."""
    codec = Codec(km.names)
    base = km.raw()[0]
    out: dict[int, set] = {}
    for r, c in POSITIONS:
        lg = legend(base[r][c], codec)
        if lg.hold_layer is not None:
            out.setdefault(lg.hold_layer, set()).add((r, c))
    return out


# ---------------------------------------------------------------- svg
def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _fit(text: str, size: float, width: float) -> float:
    """Shrink font size so text fits ``width`` px (approximate glyph width)."""
    est = len(text) * size * 0.58
    return size if est <= width else max(6.0, size * width / est)


def _n(v: float) -> str:
    """Compact number: one decimal at most, no trailing ``.0``."""
    return f"{v:.1f}".removesuffix(".0").replace("-0", "0") if v else "0"


def _text(x, y, s, size, cls, width) -> str:
    fs = _fit(s, size, width)
    return f'<text x="{_n(x)}" y="{_n(y)}" class="{cls}" font-size="{_n(fs)}">{_esc(s)}</text>'


def _body_id(w: float, h: float) -> str:
    return f"key-{_n(w)}x{_n(h)}"   # skirt size in px


def _body(w: float, h: float) -> str:
    """Keycap body of skirt size ``w`` x ``h`` px (skirt, top, dish, rim) at the origin, shared by every key of this size via ``<use>``.

    Colors come from custom properties set on the key's ``<g>`` (``--k-*``), which inherit into the ``<use>`` copy.
    """
    tw, th = w - 2 * CAP_SIDE, h - CAP_TOP - CAP_BOTTOM
    rect = f'x="{_n(CAP_SIDE)}" y="{_n(CAP_TOP)}" width="{_n(tw)}" height="{_n(th)}" rx="4"'
    return (f'  <g id="{_body_id(w, h)}">\n'
            f'    <rect class="skirt" width="{_n(w)}" height="{_n(h)}" rx="6"/>\n'
            f'    <rect class="cap" {rect}/>\n'
            f'    <rect class="dish" {rect}/>\n'
            f'    <rect class="rim" x="{_n(CAP_SIDE + RIM / 2)}" y="{_n(CAP_TOP + RIM / 2)}" width="{_n(tw - RIM)}" '
            f'height="{_n(th - RIM)}" rx="{_n(4 - RIM / 2)}" stroke-width="{_n(RIM)}"/>\n'
            f'  </g>')


class Svg:
    def __init__(self, geoms: list[KeyGeom]):
        self.geoms = geoms
        xs, ys = zip(*(p for g in geoms for p in g.corners()))
        self.ox, self.oy = min(xs) * U - MARGIN, min(ys) * U - MARGIN
        self.width = (max(xs) - min(xs)) * U + 2 * MARGIN
        self.height = (max(ys) - min(ys)) * U + 2 * MARGIN

    def render(self, key_fn, title: str, css: str, pos_attrs: bool = False) -> str:
        """Standalone SVG document, one element per line so diffs stay small.

        ``key_fn(geom)`` returns ``(cls, skirt, inner)``: the key's CSS classes, an optional ``(text, cls)`` written
        on the skirt's bottom shade below the keycap top (the hold function), and ``inner(cx, cy, w, h)`` giving the text elements
        for the top surface's box. Each key is drawn in its own coordinates (origin at the skirt's top-left corner).
        ``pos_attrs`` tags each key with ``data-pos="row,col"`` (matrix position) for scripts.
        """
        sizes = dict.fromkeys(((g.w * U - 2 * PAD, g.h * U - 2 * PAD) for g in self.geoms))
        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" role="img" width="{self.width:.0f}" '
                 f'height="{self.height:.0f}" viewBox="{_n(self.ox)} {_n(self.oy)} {_n(self.width)} {_n(self.height)}">',
                 f'<title>{_esc(title)}</title>',
                 f'<style>{css.rstrip()}\n</style>',
                 '<defs>', GRADIENT_DEFS, *(_body(w, h) for w, h in sizes), '</defs>']
        for g in self.geoms:
            cls, skirt, inner = key_fn(g)
            x, y, w, h = g.x * U + PAD, g.y * U + PAD, g.w * U - 2 * PAD, g.h * U - 2 * PAD
            tr = f"translate({_n(x)} {_n(y)})"
            if g.r:
                tr = f"rotate({_n(g.r)} {_n(g.rx * U)} {_n(g.ry * U)}) {tr}"
            tw, th = w - 2 * CAP_SIDE, h - CAP_TOP - CAP_BOTTOM
            pa = f' data-pos="{g.pos[0]},{g.pos[1]}"' if pos_attrs else ""
            parts.append(f'<g class="key {cls}"{pa} transform="{tr}">')
            parts.append(f'  <use href="#{_body_id(w, h)}"/>')
            if skirt:
                parts.append("  " + _text(w / 2, h - 4, skirt[0], 9, skirt[1], w - 6))
            parts.extend("  " + t for t in inner(CAP_SIDE + tw / 2, CAP_TOP + th / 2, tw, th))
            parts.append("</g>")
        parts.append("</svg>\n")
        return "\n".join(parts)


def _hold_label(lg: Legend) -> tuple[str, str] | None:
    if not lg.hold:
        return None
    return lg.hold, (f"hold l{lg.hold_layer}" if lg.hold_layer is not None else "hold")


def _tap_texts(lg: Legend, cx, cy, w, h, big=15.0) -> list[str]:
    out = []
    n = len(lg.tap)
    if lg.shifted:
        out.append(_text(cx, cy - h / 2 + 9, lg.shifted, 8, "shifted", w - 6))
        cy += 4
    if n:
        size = big if n == 1 else 11.0
        lh = size * 1.1
        y0 = cy - (n - 1) * lh / 2 + size * 0.35
        for i, line in enumerate(lg.tap):
            out.append(_text(cx, y0 + i * lh, line, size, "tap", w - 6))
    return out


def layer_svg(km: Keymap, li: int, svg: Svg, acts) -> str:
    codec = Codec(km.names)
    m = km.raw()[li]
    held = acts.get(li, set()) if li else set()

    def key_fn(g: KeyGeom):
        v = m[g.pos[0]][g.pos[1]]
        lg = legend(v, codec)
        if g.pos in held:
            return f"held l{li}", ("held", "hold"), lambda cx, cy, w, h: [
                _text(cx, cy + 4, km.names[li], 12, "tap", w - 6)]
        cls = lg.kind
        if lg.hold_layer is not None:
            cls += f" lt l{lg.hold_layer}"
        return cls, _hold_label(lg), lambda cx, cy, w, h: _tap_texts(lg, cx, cy, w, h)

    return svg.render(key_fn, f"{km.names[li]} layer", svg_css(len(km.layers)))


def combined_svg(km: Keymap, svg: Svg, pos_attrs: bool = False, layer_labels: bool = False) -> str:
    """All layers on one keyboard. ``layer_labels`` adds hidden full-size legends per layer (class ``lay l<i>``)."""
    codec = Codec(km.names)
    layers = km.raw()
    corners = [(-1, -1), (1, -1), (-1, 1), (1, 1)]  # TL TR BL BR

    def key_fn(g: KeyGeom):
        r, c = g.pos
        base = legend(layers[0][r][c], codec)
        extras = []
        for li in range(1, len(layers)):
            lg = legend(layers[li][r][c], codec)
            if lg.kind in ("none", "trns", "mod") or not (lg.tap or lg.hold):
                continue
            text = " ".join(lg.tap) or lg.hold
            if len(text) > 7:
                text = codec.decode(layers[li][r][c])   # compact official token
            extras.append((li, text))
        cls = base.kind + (f" lt l{base.hold_layer}" if base.hold_layer is not None else "")

        def inner(cx, cy, w, h):
            out = []
            n = len(base.tap)
            if n:
                size = min(13.0, h * 0.34) if n == 1 else 9.0
                y0 = cy - (n - 1) * size * 0.55 + size * 0.35
                for i, line in enumerate(base.tap):
                    out.append(_text(cx, y0 + i * size * 1.1, line, size, "tap", w - 14))
            for (li, s), (sx, sy) in zip(extras[:4], corners):
                tx = cx + sx * (w / 4)
                ty = cy + sy * (h / 2 - 5) + 2.5
                out.append(_text(tx, ty, s, 7, f"sub l{li}", w / 2 - 4))
            if layer_labels:   # every layer's full legend, centered; the page shows one layer at a time
                for li in range(1, len(layers)):
                    lg = legend(layers[li][r][c], codec)
                    if lg.kind in ("none", "trns", "layer") or not lg.tap:
                        continue
                    size = min(15.0, h * 0.4) if len(lg.tap) == 1 else 10.0
                    y0 = cy - (len(lg.tap) - 1) * size * 0.55 + size * 0.35
                    for i, line in enumerate(lg.tap):
                        out.append(_text(cx, y0 + i * size * 1.1, line, size, f"lay l{li}", w - 6))
            return out

        return cls, _hold_label(base), inner

    return svg.render(key_fn, "All layers", svg_css(len(layers)), pos_attrs)


# ---------------------------------------------------------------- styles + output
SVG_CSS = """
:root { --fg:#222; --muted:#6f6f6b; --cap:#f6f6f3; --skirt:#dcdcd7; --edge:#b9b9b3;
        --none-cap:#f4f4f1; --none-skirt:#e7e7e3; --mod-cap:#f1f0ec; --mod-skirt:#d4d3cd;
        --S:70%; --Lt:36%; --capS:60%; --capL:95%; --skirtL:84%; --edgeL:62%; --heldCapL:86%; --heldSkirtL:72%;
        --dish-shade:0.07; --dish-light:0.35; --rim-top:0.6; --rim-bottom:0.3; }
@media (prefers-color-scheme: dark) {
  :root { --fg:#ececea; --muted:#9a9a98; --cap:#3a3d42; --skirt:#25272b; --edge:#17181a;
          --none-cap:#24262a; --none-skirt:#1c1d20; --mod-cap:#34363b; --mod-skirt:#222327;
          --S:55%; --Lt:74%; --capS:32%; --capL:30%; --skirtL:19%; --edgeL:12%; --heldCapL:40%; --heldSkirtL:27%;
          --dish-shade:0.25; --dish-light:0.05; --rim-top:0.06; --rim-bottom:0.025; } }
text { font-family: system-ui, sans-serif; }
.key { --k-cap: var(--cap); --k-skirt: var(--skirt); --k-edge: var(--edge); --k-dash: none; }
.skirt { fill: var(--k-skirt); stroke: var(--k-edge); stroke-width: 1; stroke-dasharray: var(--k-dash); }
.cap { fill: var(--k-cap); }
.dish { fill: url(#dish); }
.rim { fill: none; stroke: url(#rim); }
.dish-shade { stop-color: #000; stop-opacity: var(--dish-shade); }
.dish-light { stop-color: #fff; stop-opacity: var(--dish-light); }
.dish-clear { stop-opacity: 0; }
.rim-top { stop-color: #fff; stop-opacity: var(--rim-top); }
.rim-bottom { stop-color: #fff; stop-opacity: var(--rim-bottom); }
.key.none { --k-cap: var(--none-cap); --k-skirt: var(--none-skirt); --k-dash: 3 3; }
.key.trns { --k-cap: var(--none-cap); --k-skirt: var(--none-skirt); }
.key.mod { --k-cap: var(--mod-cap); --k-skirt: var(--mod-skirt); }
.key text { text-anchor: middle; fill: var(--fg); }
.key .shifted, .key.trns text { fill: var(--muted); }
.key .hold { font-weight: 600; fill: var(--muted); }
.key .sub { font-weight: 600; }
"""


def svg_css(n: int) -> str:
    out = [SVG_CSS.strip()]
    for i in range(n):
        h = HUES[i % len(HUES)]
        out += [f".key.lt.l{i} {{ --k-cap: hsl({h} var(--capS) var(--capL)); "
                f"--k-skirt: hsl({h} 35% var(--skirtL)); --k-edge: hsl({h} 30% var(--edgeL)); }}",
                f".key.held.l{i} {{ --k-cap: hsl({h} var(--capS) var(--heldCapL)); "
                f"--k-skirt: hsl({h} 45% var(--heldSkirtL)); --k-edge: hsl({h} 50% var(--edgeL)); }}",
                f".key text.l{i} {{ fill: hsl({h} var(--S) var(--Lt)); }}"]
    return "\n" + "\n".join(out)


PAGE_CSS = """
:root { color-scheme: light dark; }
body { margin: 0; background: #f6f6f4; color: #222; font: 15px/1.4 system-ui, sans-serif; }
@media (prefers-color-scheme: dark) { body { background: #17181a; color: #e8e8e6; } }
main { max-width: 1100px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 22px; margin: 0 0 8px; } h2 { font-size: 17px; margin: 32px 0 8px; }
img { width: 100%; height: auto; display: block; }
"""


def svg_name(layer: str) -> str:
    return f"{layer.lower()}.svg"


def render_svgs(km: Keymap) -> dict[str, str]:
    """filename -> SVG document: combined.svg plus one per layer."""
    svg = Svg(load_geometry())
    acts = activators(km)
    out = {"combined.svg": combined_svg(km, svg)}
    for i, name in enumerate(km.names):
        out[svg_name(name)] = layer_svg(km, i, svg, acts)
    return out


def render_html(km: Keymap) -> str:
    """Local preview page showing the SVG files."""
    body = ['<h1>Corne keymap</h1>', '<p><a href="tutor/index.html">Typing tutor</a></p>', '<img src="combined.svg" alt="All layers">']
    for name in km.names:
        body += [f'<h2>{_esc(name)}</h2>', f'<img src="{svg_name(name)}" alt="{_esc(name)} layer">']
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>Corne keymap</title>\n<style>{PAGE_CSS}</style>\n</head>\n'
            f'<body>\n<main>\n{chr(10).join(body)}\n</main>\n</body>\n</html>\n')


README_START, README_END = "<!-- keymap:start -->", "<!-- keymap:end -->"


def readme_section(km: Keymap, docs: str = "docs") -> str:
    lines = [README_START, "", f"![All layers]({docs}/combined.svg)"]
    for name in km.names:
        lines += ["", f"### {name}", "", f"![{name} layer]({docs}/{svg_name(name)})"]
    return "\n".join(lines + ["", README_END])


def update_readme(text: str, km: Keymap) -> str:
    """Replace the generated section between the markers (appended if missing)."""
    section = readme_section(km)
    if README_START in text and README_END in text:
        a = text.index(README_START)
        b = text.index(README_END) + len(README_END)
        return text[:a] + section + text[b:]
    return text.rstrip("\n") + "\n\n" + section + "\n"
