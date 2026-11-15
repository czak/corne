"""Keymap data for the typing tutor (docs/tutor/keymap.js, see ``render_data``). The tutor itself is static: paste a text,
then type it with the chord for each character highlighted on the combined keymap.

For every character the keymap can produce, ``chords`` finds the cheapest way to type it: a key to tap, plus the
keys to hold first (a base-layer key that activates the layer, then AltGr and/or Shift on that layer). Holds prefer
the hand opposite the tapped key, as home-row mods require. AltGr combinations follow the Polish (programmer) layout.
"""
from __future__ import annotations

import json

from .keycodes import QK_LAYER_TAP, QK_MOD_TAP, QK_MODS, Codec, label
from .keyboard import POSITIONS
from .layout import Keymap
from .render import Svg, activators, combined_svg, legend, load_geometry

SHIFT_MODS = (0x02, 0x12)          # MOD_LSFT, MOD_RSFT
SHIFT_KEYS = (0xE1, 0xE5)          # LSHIFT, RSHIFT
ALTGR_MOD = 0x14                   # MOD_RALT
ALTGR_KEY = 0xE6                   # RALT
ALTGR = dict(zip("acelnoszx", "ąćęłńóśżź"))   # Polish (programmer) layout: AltGr+letter; Shift gives uppercase
WHITESPACE = {0x2C: " ", 0x28: "\n", 0x2B: "\t"}   # SPACE, ENTER, TAB


def _chars(basic: int) -> tuple[str | None, str | None]:
    """(unshifted, shifted) character a basic keycode types on a US layout."""
    if 0x04 <= basic <= 0x1D:
        c = chr(ord("a") + basic - 0x04)
        return c, c.upper()
    if basic in WHITESPACE:
        return WHITESPACE[basic], None
    lab = label(basic)
    if lab:
        parts = lab.split("\n")
        if len(parts) == 2 and all(len(p) == 1 for p in parts):
            return parts[1], parts[0]
    return None, None


def _tap(v: int) -> tuple[int, bool] | None:
    """(basic keycode, shift included) sent when ``v`` is tapped, or None if it types no character."""
    if v <= 0xFF:
        return v, False
    if QK_MODS <= v < QK_MOD_TAP:
        return (v & 0xFF, True) if (v >> 8) & 0x1F in SHIFT_MODS else None
    if QK_MOD_TAP <= v < 0x5000:      # mod-tap and layer-tap: the tap is the basic keycode
        return v & 0xFF, False
    return None


def _is_shift(v: int) -> bool:
    return v in SHIFT_KEYS or (QK_MOD_TAP <= v < QK_LAYER_TAP and (v >> 8) & 0x1F in SHIFT_MODS)


def _is_altgr(v: int) -> bool:
    return v == ALTGR_KEY or (QK_MOD_TAP <= v < QK_LAYER_TAP and (v >> 8) & 0x1F == ALTGR_MOD)


def _left(pos: tuple[int, int]) -> bool:
    return pos[1] < 6


def _pick(cands, tap):
    """Prefer a hold key on the other hand from ``tap``."""
    cands = sorted(cands, key=lambda p: (_left(p) == _left(tap), POSITIONS.index(p)))
    return cands[0] if cands else None


def chords(km: Keymap) -> dict[str, dict]:
    """char -> {"tap": "r,c", "hold": ["r,c", ...], "layer": name | None, "altgr": bool, "shift": bool}.

    ``hold`` is ordered: layer key (if ``layer``), then AltGr (if ``altgr``), then Shift (if ``shift``).
    """
    layers = km.raw()
    acts = activators(km)
    best: dict[str, tuple] = {}
    for li, m in enumerate(layers):
        if li and li not in acts:
            continue                       # not reachable from the base layer
        eff = {p: (layers[0] if m[p[0]][p[1]] == 1 else m)[p[0]][p[1]] for p in POSITIONS}   # TRNS falls through
        shifts = [p for p in POSITIONS if _is_shift(eff[p])]
        altgrs = [p for p in POSITIONS if _is_altgr(eff[p])]
        for pos in POSITIONS:
            if li and pos in acts[li]:
                continue                   # held to reach this layer
            t = _tap(eff[pos])
            if not t:
                continue
            plain, shifted = _chars(t[0])
            act = _pick(acts.get(li, ()), pos) if li else None
            options = [(shifted, False, False)] if t[1] else [(plain, False, False), (shifted, False, True)]
            if not t[1] and plain in ALTGR:
                options += [(ALTGR[plain], True, False), (ALTGR[plain].upper(), True, True)]
            for ch, need_altgr, need_shift in options:
                if not ch:
                    continue
                hold = [act] if act else []
                for need, keys in ((need_altgr, altgrs), (need_shift, shifts)):
                    if need:
                        k = _pick([p for p in keys if p != pos and p not in hold], pos)
                        if not k:
                            break
                        hold.append(k)
                else:
                    cost = (len(hold), li)
                    if ch not in best or cost < best[ch][0]:
                        best[ch] = (cost, pos, hold, li, need_altgr, need_shift)
    return {ch: {"tap": f"{pos[0]},{pos[1]}", "hold": [f"{r},{c}" for r, c in hold],
                 "layer": km.names[li] if li else None, "altgr": altgr, "shift": shift}
            for ch, (_, pos, hold, li, altgr, shift) in sorted(best.items())}


def _names(km: Keymap) -> dict[str, str]:
    """"r,c" -> short base-layer name of the key, for the hint line."""
    codec = Codec(km.names)
    out = {}
    for r, c in POSITIONS:
        lg = legend(km.raw()[0][r][c], codec)
        out[f"{r},{c}"] = " ".join(lg.tap) or lg.hold or ""
    return out


def render_data(km: Keymap) -> str:
    """docs/tutor/keymap.js: everything the static tutor page needs from the keymap, one entry per line for small diffs."""
    svg = combined_svg(km, Svg(load_geometry()), pos_attrs=True, layer_labels=True)
    svg = (svg.split("\n", 1)[1] if svg.startswith("<?xml") else svg).strip()
    svg = svg.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")   # template-literal escapes

    def obj(d: dict) -> str:
        return "{\n" + "".join(f"    {_js(k)}: {_js(v)},\n" for k, v in d.items()) + "  }"

    return ("// Generated by `kb render` from keymap.toml. Do not edit.\n"
            "const KEYMAP = {\n"
            f"  layers: {_js(km.names)},\n"
            f"  chords: {obj(chords(km))},\n"
            f"  names: {obj(_names(km))},\n"
            f"  svg: `\n{svg}\n`,\n"
            "};\n")


def _js(v) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(", ", ": ")).replace("</", "<\\/")
