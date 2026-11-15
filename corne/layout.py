"""keymap.toml format.

Each half is an array of 4 rows, as seen from above:

    left:                                   right:
      outer  5 alphas  inner-extra            inner-extra  5 alphas  outer
      outer  5 alphas  inner-extra            inner-extra  5 alphas  outer
      outer  5 alphas                                      5 alphas  outer
                       3 thumbs                     3 thumbs

Rows have 7, 7, 6 and 3 keys.

Tap dances are an array of tables; entry n is ``TD(n)``. Their fields are those of Vial's tap dance entry
(``vial_tap_dance_entry_t``). Slots after the last entry are empty on the keyboard.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import toml_writer
from .keyboard import COLS, HALVES, POSITIONS, ROWS
from .device import TapDance
from .keycodes import QK_TAP_DANCE, Codec

Matrix = list[list[int]]  # [row][col] keycodes
TD_KEYS = ("on_tap", "on_hold", "on_double_tap", "on_tap_hold")
TD_FIELDS = (*TD_KEYS, "custom_tapping_term")


def trim_tap_dances(tds: list[TapDance]) -> list[TapDance]:
    """Drop trailing empty entries (no keycodes set)."""
    tds = [tuple(t) for t in tds]
    while tds and not any(tds[-1][:4]):
        tds.pop()
    return tds


@dataclass
class Keymap:
    layers: dict[str, Matrix]                       # ordered: layer index = position
    settings: dict[str, int | bool] = field(default_factory=dict)
    tap_dance: list[TapDance] = field(default_factory=list)   # entry n = TD(n); trailing empty ones trimmed

    @property
    def names(self) -> list[str]:
        return list(self.layers)

    def raw(self) -> list[Matrix]:
        return list(self.layers.values())


# ---------------------------------------------------------------- write
def _half_rows(grid, matrix: Matrix, codec: Codec) -> list[list[str]]:
    return [[codec.decode(matrix[p[0]][p[1]]) for p in line if p] for line in grid]


def dump(km: Keymap) -> str:
    codec = Codec(km.names)
    doc = {
        "settings": dict(km.settings),
        "layers": {
            name: {half: _half_rows(grid, m, codec) for half, grid in HALVES.items()}
            for name, m in km.layers.items()
        },
    }
    if km.tap_dance:
        doc["tap_dance"] = [{**{k: codec.decode(v) for k, v in zip(TD_KEYS, td)}, "custom_tapping_term": td[4]}
                            for td in km.tap_dance]
    return toml_writer.dumps(doc, comments={
        "settings": "QMK settings (QMK config.h names)",
        f"layers.{km.names[0]}": "Layer order = layer index. Each half: top (7), home (7), bottom (6), thumbs (3);\n"
                                 "left-to-right as seen from above. Keycodes: vial-gui names without KC_.\n"
                                 "The firmware has a fixed 8 layers and push needs all of them: keep unused ones as all-NO layers.",
        "tap_dance": "Tap dances: the n-th [[tap_dance]] is TD(n). Fields of Vial's tap dance entry;\n"
                     "custom_tapping_term (ms) is also the double-tap window.",
    })


def save(km: Keymap, path: Path):
    path.write_text(dump(km))


# ---------------------------------------------------------------- read
class KeymapError(ValueError):
    pass


def parse(text: str) -> Keymap:
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise KeymapError(f"invalid TOML: {e}") from None
    layers_doc = doc.get("layers") or {}
    if not isinstance(layers_doc, dict) or not layers_doc:
        raise KeymapError("'layers' must be a non-empty mapping")
    names = [str(n) for n in layers_doc]
    codec = Codec(names)
    layers: dict[str, Matrix] = {}
    errors = []
    for name, halves in layers_doc.items():
        m = [[0] * COLS for _ in range(ROWS)]
        if set(halves or {}) != set(HALVES):
            errors.append(f"{name}: needs exactly 'left' and 'right'")
            continue
        for half, grid in HALVES.items():
            lines = halves[half]
            if not (isinstance(lines, list) and all(isinstance(ln, list) for ln in lines)):
                errors.append(f"{name}.{half}: must be an array of 4 rows")
                continue
            if len(lines) != 4:
                errors.append(f"{name}.{half}: expected 4 lines (3 rows + thumbs), got {len(lines)}")
                continue
            for i, (ln, slots) in enumerate(zip(lines, grid)):
                toks = ln
                pos = [p for p in slots if p]
                if len(toks) != len(pos) or not all(isinstance(t, str) for t in toks):
                    errors.append(f"{name}.{half} row {i + 1}: expected {len(pos)} keycode strings, got {toks}")
                    continue
                for tok, (r, c) in zip(toks, pos):
                    try:
                        m[r][c] = codec.encode(tok)
                    except ValueError as e:
                        errors.append(f"{name}.{half} row {i + 1}: {e}")
        layers[str(name)] = m
    tap_dance = _parse_tap_dances(doc.get("tap_dance", []), codec, errors)
    for name, m in layers.items():
        for r, c in POSITIONS:
            if QK_TAP_DANCE <= m[r][c] < QK_TAP_DANCE + 0x100 and m[r][c] - QK_TAP_DANCE >= len(tap_dance):
                errors.append(f"{name}: {codec.decode(m[r][c])} is used but not defined in [[tap_dance]]")
    if errors:
        raise KeymapError("\n".join(errors))
    return Keymap(layers, dict(doc.get("settings") or {}), tap_dance)


def _parse_tap_dances(entries, codec: Codec, errors: list[str]) -> list[TapDance]:
    if not (isinstance(entries, list) and all(isinstance(e, dict) for e in entries)):
        errors.append("tap_dance: must be an array of tables ([[tap_dance]])")
        return []
    out = []
    for i, e in enumerate(entries):
        if set(e) != set(TD_FIELDS):
            errors.append(f"tap_dance TD({i}): needs exactly {', '.join(TD_FIELDS)}")
            continue
        td = []
        for k in TD_KEYS:
            try:
                if not isinstance(e[k], str):
                    raise ValueError(f"expected a keycode string, got {e[k]!r}")
                td.append(codec.encode(e[k]))
            except ValueError as err:
                errors.append(f"tap_dance TD({i}).{k}: {err}")
                td.append(0)
        term = e["custom_tapping_term"]
        if not (isinstance(term, int) and not isinstance(term, bool) and 0 <= term <= 0xFFFF):
            errors.append(f"tap_dance TD({i}).custom_tapping_term: expected milliseconds (0-65535), got {term!r}")
            term = 0
        out.append((*td, term))
    return out


def load(path: Path) -> Keymap:
    return parse(path.read_text())
