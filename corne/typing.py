"""Keymap data for the typing tutor (docs/tutor/keymap.js, see ``render_data``). The tutor itself is static: paste a text,
then type it with the chord for each character highlighted on the combined keymap.

For every character the keymap can produce, ``chords`` finds the cheapest way to type it: a key to tap, plus the
keys to hold first (a base-layer key that activates the layer, then AltGr and/or Shift on that layer). Holds prefer
the hand opposite the tapped key, as home-row mods require. AltGr combinations follow the Polish (programmer) layout.
"""
from __future__ import annotations

import json

from .keycodes import QK_LAYER_MOD, QK_LAYER_TAP, QK_MOD_TAP, QK_MODS, QK_ONE_SHOT_MOD, QK_TAP_DANCE, Codec, label
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


def _is_oneshot(v: int, mods: tuple[int, ...]) -> bool:
    return QK_ONE_SHOT_MOD <= v < QK_ONE_SHOT_MOD + 0x20 and v & 0x1F in mods


def _is_shift(v: int) -> bool:
    return (v in SHIFT_KEYS or _is_oneshot(v, SHIFT_MODS)
            or (QK_MOD_TAP <= v < QK_LAYER_TAP and (v >> 8) & 0x1F in SHIFT_MODS))


def _is_altgr(v: int) -> bool:
    return (v == ALTGR_KEY or _is_oneshot(v, (ALTGR_MOD,))
            or (QK_MOD_TAP <= v < QK_LAYER_TAP and (v >> 8) & 0x1F == ALTGR_MOD))


def _td_tap(v: int, km: Keymap) -> int:
    """``v``, or its tap action if it is a tap dance (a Shift on tap is a Shift key for the tutor)."""
    if QK_TAP_DANCE <= v < QK_TAP_DANCE + len(km.tap_dance):
        return km.tap_dance[v - QK_TAP_DANCE][0]
    return v


def _left(pos: tuple[int, int]) -> bool:
    return pos[1] < 6


def _pick(cands, tap):
    """Prefer a hold key on the other hand from ``tap``."""
    cands = sorted(cands, key=lambda p: (_left(p) == _left(tap), POSITIONS.index(p)))
    return cands[0] if cands else None


def _typing_activators(km: Keymap) -> dict[int, set[tuple[int, int]]]:
    """Layer -> base-layer keys that reach it while only Shift/AltGr are held. A layer that holds Gui, Ctrl or Alt
    (``LM(n, MOD_LGUI)``) types shortcuts, not characters, so it is left out."""
    base = km.raw()[0]
    out = {}
    for li, positions in activators(km).items():
        ok = {p for p in positions
              if not (QK_LAYER_MOD <= base[p[0]][p[1]] < 0x5200
                      and (base[p[0]][p[1]] & 0x1F) & ~(SHIFT_MODS[1] | ALTGR_MOD))}
        if ok:
            out[li] = ok
    return out


def chords(km: Keymap) -> dict[str, dict]:
    """char -> {"tap": "r,c", "hold": ["r,c", ...], "layer": name | None, "altgr": bool, "shift": bool}.

    ``hold`` is ordered: layer key (if ``layer``), then AltGr (if ``altgr``), then Shift (if ``shift``).
    """
    layers = km.raw()
    acts = _typing_activators(km)
    best: dict[str, tuple] = {}
    for li, m in enumerate(layers):
        if li and li not in acts:
            continue                       # not reachable from the base layer, or held with Gui/Ctrl/Alt
        eff = {p: (layers[0] if m[p[0]][p[1]] == 1 else m)[p[0]][p[1]] for p in POSITIONS}   # TRNS falls through
        shifts = [p for p in POSITIONS if _is_shift(_td_tap(eff[p], km))]
        altgrs = [p for p in POSITIONS if _is_altgr(_td_tap(eff[p], km))]
        for pos in POSITIONS:
            if li and pos in acts[li]:
                continue                   # held to reach this layer
            v = eff[pos]
            if QK_TAP_DANCE <= v < QK_TAP_DANCE + len(km.tap_dance):
                on_tap, on_hold = km.tap_dance[v - QK_TAP_DANCE][:2]
                actions = [(_tap(on_tap), False), (_tap(on_hold), True)]     # (what is typed, held instead of tapped)
            else:
                actions = [(_tap(v), False)]
            act = _pick(acts.get(li, ()), pos) if li else None
            for t, held in actions:
                if not t:
                    continue
                plain, shifted = _chars(t[0])
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
                        cost = (len(hold) + 0.5 * held, li)   # a tap-dance hold beats holding Shift
                        if ch not in best or cost < best[ch][0]:
                            best[ch] = (cost, pos, hold, li, need_altgr, need_shift, held)
    return {ch: {"tap": f"{pos[0]},{pos[1]}", "hold": [f"{r},{c}" for r, c in hold],
                 "layer": li or None, "altgr": altgr, "shift": shift, "held": held}
            for ch, (_, pos, hold, li, altgr, shift, held) in sorted(best.items())}


def _names(km: Keymap) -> dict[str, str]:
    """"r,c" -> short base-layer name of the key, for the hint line."""
    codec = Codec()
    out = {}
    for r, c in POSITIONS:
        lg = legend(km.raw()[0][r][c], codec, km.tap_dance)
        out[f"{r},{c}"] = " ".join(lg.tap) or lg.hold or ""
    return out


def render_data(km: Keymap) -> str:
    """docs/tutor/keymap.js: everything the static tutor page needs from the keymap, one entry per line for small diffs."""
    svg = combined_svg(km, Svg(load_geometry()), pos_attrs=True, layer_labels=True)
    svg = (svg.split("\n", 1)[1] if svg.startswith("<?xml") else svg).strip()
    svg = svg.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")   # template-literal escapes

    def obj(d: dict) -> str:
        return "{\n" + "".join(f"    {_js(k)}: {_js(v)},\n" for k, v in d.items()) + "  }"

    return ("// Generated by `kb render` from the keyboard. Do not edit.\n"
            "const KEYMAP = {\n"
            f"  chords: {obj(chords(km))},\n"
            f"  names: {obj(_names(km))},\n"
            f"  svg: `\n{svg}\n`,\n"
            "};\n")


def _js(v) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(", ", ": ")).replace("</", "<\\/")
