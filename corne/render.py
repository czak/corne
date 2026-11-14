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


def _text(x, y, s, size, cls, width) -> str:
    fs = _fit(s, size, width)
    return (f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" font-size="{fs:.1f}">{_esc(s)}</text>')


class Svg:
    def __init__(self, geoms: list[KeyGeom]):
        self.geoms = geoms
        xs, ys = zip(*(p for g in geoms for p in g.corners()))
        self.ox, self.oy = min(xs) * U - MARGIN, min(ys) * U - MARGIN
        self.width = (max(xs) - min(xs)) * U + 2 * MARGIN
        self.height = (max(ys) - min(ys)) * U + 2 * MARGIN

    def render(self, key_fn, title: str, css: str) -> str:
        """Standalone SVG document."""
        oy, h = self.oy, self.height
        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" role="img" width="{self.width:.0f}" height="{h:.0f}" '
                 f'viewBox="{self.ox:.1f} {oy:.1f} {self.width:.1f} {h:.1f}">'
                 f'<title>{_esc(title)}</title><style>{css}</style>']
        for g in self.geoms:
            cls, inner = key_fn(g)
            x, y, w, h = g.x * U + PAD, g.y * U + PAD, g.w * U - 2 * PAD, g.h * U - 2 * PAD
            tr = f' transform="rotate({g.r} {g.rx * U:.1f} {g.ry * U:.1f})"' if g.r else ""
            cx, cy = x + w / 2, y + h / 2
            parts.append(f'<g class="key {cls}"{tr}><rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" '
                         f'height="{h:.1f}" rx="6"/>')
            parts.extend(inner(cx, cy, w, h))
            parts.append("</g>")
        parts.append("</svg>")
        return "".join(parts)


def _tap_texts(lg: Legend, cx, cy, w, h, big=15.0) -> list[str]:
    out = []
    n = len(lg.tap)
    if n:
        size = big if n == 1 else 11.0
        lh = size * 1.1
        y0 = cy - (n - 1) * lh / 2 + size * 0.35 - (5 if lg.hold else 0)
        for i, line in enumerate(lg.tap):
            out.append(_text(cx, y0 + i * lh, line, size, "tap", w - 8))
    if lg.shifted:
        out.append(_text(cx, cy - h / 2 + 12, lg.shifted, 9, "shifted", w - 8))
    if lg.hold:
        cls = f"hold l{lg.hold_layer}" if lg.hold_layer is not None else "hold"
        out.append(_text(cx, cy + h / 2 - 7, lg.hold, 9, cls, w - 8))
    return out


def layer_svg(km: Keymap, li: int, svg: Svg, acts) -> str:
    codec = Codec(km.names)
    m = km.raw()[li]
    held = acts.get(li, set()) if li else set()

    def key_fn(g: KeyGeom):
        v = m[g.pos[0]][g.pos[1]]
        lg = legend(v, codec)
        if g.pos in held:
            return f"held l{li}", lambda cx, cy, w, h: [
                _text(cx, cy + 4, km.names[li], 12, "tap", w - 8),
                _text(cx, cy + h / 2 - 7, "held", 9, "hold", w - 8)]
        cls = lg.kind
        if lg.hold_layer is not None:
            cls += f" lt l{lg.hold_layer}"
        return cls, lambda cx, cy, w, h: _tap_texts(lg, cx, cy, w, h)

    return svg.render(key_fn, f"{km.names[li]} layer", svg_css(len(km.layers)))


def combined_svg(km: Keymap, svg: Svg) -> str:
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
                size = 14.0 if n == 1 else 10.0
                y0 = cy - (n - 1) * size * 0.55 + size * 0.35 - 2
                for i, line in enumerate(base.tap):
                    out.append(_text(cx, y0 + i * size * 1.1, line, size, "tap", w - 10))
            if base.hold:
                hc = f"hold l{base.hold_layer}" if base.hold_layer is not None else "hold"
                out.append(_text(cx, cy + 11, base.hold, 8, hc, w - 10))
            for (li, s), (sx, sy) in zip(extras[:4], corners):
                tx = cx + sx * (w / 4)
                ty = cy + sy * (h / 2 - 8) + 3
                out.append(_text(tx, ty, s, 8, f"sub l{li}", w / 2 - 4))
            return out

        return cls, inner

    return svg.render(key_fn, "All layers", svg_css(len(layers)))


# ---------------------------------------------------------------- styles + output
SVG_CSS = """
:root { --fg:#222; --muted:#888; --key:#fff; --stroke:#c9c9c4; --none:#efefec; --mod:#ecebe6;
        --L:58%; --Lt:38%; --S:70%; --tint:93%; --held:80%; }
@media (prefers-color-scheme: dark) {
  :root { --fg:#e8e8e6; --muted:#8a8a8a; --key:#26282b; --stroke:#3b3e43; --none:#1e2022; --mod:#2e3034;
          --L:68%; --Lt:72%; --S:60%; --tint:22%; --held:34%; } }
text { font-family: system-ui, sans-serif; }
.key rect { fill: var(--key); stroke: var(--stroke); stroke-width: 1; }
.key.none rect { fill: var(--none); stroke-dasharray: 3 3; }
.key.trns rect { fill: var(--none); }
.key.mod rect { fill: var(--mod); }
.key text { text-anchor: middle; fill: var(--fg); }
.key .shifted, .key.trns text { fill: var(--muted); }
.key .hold { font-weight: 600; fill: var(--muted); }
.key .sub { font-weight: 600; }
"""


def svg_css(n: int) -> str:
    out = [SVG_CSS]
    for i in range(n):
        h = HUES[i % len(HUES)]
        col = f"hsl({h} var(--S) var(--L))"
        out.append(
            f".key.lt.l{i} rect {{ fill: hsl({h} 60% var(--tint)); stroke: {col}; }}"
            f".key.held.l{i} rect {{ fill: hsl({h} 60% var(--held)); stroke: {col}; stroke-width: 2; }}"
            f".key text.l{i} {{ fill: hsl({h} var(--S) var(--Lt)); }}")
    return "\n".join(out)


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
    body = ['<h1>Corne keymap</h1><img src="combined.svg" alt="All layers">']
    for name in km.names:
        body.append(f'<h2>{_esc(name)}</h2><img src="{svg_name(name)}" alt="{_esc(name)} layer">')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>Corne keymap</title><style>{PAGE_CSS}</style></head>'
            f'<body><main>{"".join(body)}</main></body></html>\n')


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
