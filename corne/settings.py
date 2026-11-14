"""Vial QMK settings, named after the corresponding QMK config.h options.

qsid numbers, widths and bit positions follow vial-gui's qmk_settings.json.
Bitfield qsids (1, 3, 8, 21) are exposed as one boolean per bit.
The magic qsid (21) bits are QMK's ``keymap_config`` field names.
"""
from __future__ import annotations

from dataclasses import dataclass

# (qsid, bit or None) -> name
NAMES: dict[tuple[int, int | None], str] = {
    (1, 0): "GRAVE_ESC_ALT_OVERRIDE",
    (1, 1): "GRAVE_ESC_CTRL_OVERRIDE",
    (1, 2): "GRAVE_ESC_GUI_OVERRIDE",
    (1, 3): "GRAVE_ESC_SHIFT_OVERRIDE",
    (2, None): "COMBO_TERM",
    (3, 0): "AUTO_SHIFT_ENABLE",
    (3, 1): "AUTO_SHIFT_MODIFIERS",
    (3, 2): "NO_AUTO_SHIFT_SPECIAL",
    (3, 3): "NO_AUTO_SHIFT_NUMERIC",
    (3, 4): "NO_AUTO_SHIFT_ALPHA",
    (3, 5): "AUTO_SHIFT_REPEAT",
    (3, 6): "AUTO_SHIFT_NO_AUTO_REPEAT",
    (4, None): "AUTO_SHIFT_TIMEOUT",
    (5, None): "ONESHOT_TAP_TOGGLE",
    (6, None): "ONESHOT_TIMEOUT",
    (7, None): "TAPPING_TERM",
    (8, 0): "PERMISSIVE_HOLD",
    (8, 1): "IGNORE_MOD_TAP_INTERRUPT",
    (8, 2): "TAPPING_FORCE_HOLD",
    (8, 3): "RETRO_TAPPING",
    (9, None): "MOUSEKEY_DELAY",
    (10, None): "MOUSEKEY_INTERVAL",
    (11, None): "MOUSEKEY_MOVE_DELTA",
    (12, None): "MOUSEKEY_MAX_SPEED",
    (13, None): "MOUSEKEY_TIME_TO_MAX",
    (14, None): "MOUSEKEY_WHEEL_DELAY",
    (15, None): "MOUSEKEY_WHEEL_INTERVAL",
    (16, None): "MOUSEKEY_WHEEL_MAX_SPEED",
    (17, None): "MOUSEKEY_WHEEL_TIME_TO_MAX",
    (18, None): "TAP_CODE_DELAY",
    (19, None): "TAP_HOLD_CAPS_DELAY",
    (20, None): "TAPPING_TOGGLE",
    (21, 0): "swap_control_capslock",
    (21, 1): "capslock_to_control",
    (21, 2): "swap_lalt_lgui",
    (21, 3): "swap_ralt_rgui",
    (21, 4): "no_gui",
    (21, 5): "swap_grave_esc",
    (21, 6): "swap_backslash_backspace",
    (21, 7): "nkro",
    (21, 8): "swap_lctl_lgui",
    (21, 9): "swap_rctl_rgui",
    # newer firmware: separate qsids instead of the qsid 8 bitfield
    (22, None): "PERMISSIVE_HOLD",
    (23, None): "HOLD_ON_OTHER_KEY_PRESS",
    (24, None): "RETRO_TAPPING",
    (25, None): "QUICK_TAP_TERM",
    (26, None): "CHORDAL_HOLD",
    (27, None): "FLOW_TAP_TERM",
}


# Byte width of each qsid's value (from vial-gui's qmk_settings.json; default 1).
WIDTHS = {2: 2, 4: 2, 6: 2, 7: 2, 9: 2, 10: 2, 11: 2, 12: 2, 13: 2, 14: 2, 15: 2, 16: 2, 17: 2,
          18: 2, 19: 2, 21: 4, 25: 2, 27: 2}
BOOLEAN_QSIDS = {22, 23, 24, 26}


@dataclass(frozen=True)
class Field:
    name: str
    qsid: int
    width: int
    bit: int | None   # None: whole value
    boolean: bool


def fields_for(supported: list[int]) -> list[Field]:
    """Fields available on a keyboard that reports the given qsids."""
    out, seen = [], set()
    for (qsid, bit), name in NAMES.items():
        if qsid not in supported:
            continue
        if name in seen:
            raise RuntimeError(f"keyboard supports two settings named {name}")
        seen.add(name)
        out.append(Field(name, qsid, WIDTHS.get(qsid, 1), bit, bit is not None or qsid in BOOLEAN_QSIDS))
    return out


def decode(fields: list[Field], raw: dict[int, int]) -> dict[str, int | bool]:
    out: dict[str, int | bool] = {}
    for f in fields:
        v = raw[f.qsid]
        out[f.name] = bool(v >> f.bit & 1) if f.bit is not None else (bool(v) if f.boolean else v)
    return out


def encode(fields: list[Field], named: dict[str, int | bool], base: dict[int, int]) -> dict[int, int]:
    """Apply named values on top of raw qsid values ``base``; returns new raw values."""
    by_name = {f.name: f for f in fields}
    unknown = set(named) - set(by_name)
    if unknown:
        raise ValueError(f"unknown settings: {', '.join(sorted(unknown))}")
    raw = dict(base)
    for name, val in named.items():
        f = by_name[name]
        if f.bit is not None:
            raw[f.qsid] = raw[f.qsid] & ~(1 << f.bit) | (int(bool(val)) << f.bit)
        else:
            raw[f.qsid] = int(val)
    return raw


def widths(fields: list[Field]) -> dict[int, int]:
    return {f.qsid: f.width for f in fields}
