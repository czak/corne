"""TOML keymap format, used for backups/, `kb dump` and `kb push`.

Layers are an array of tables; entry n is layer n (``MO(n)``, ``LT(n,kc)``). Each half is an array of 4 rows, as seen from above:

    left:                                   right:
      outer  5 alphas  inner-extra            inner-extra  5 alphas  outer
      outer  5 alphas  inner-extra            inner-extra  5 alphas  outer
      outer  5 alphas                                      5 alphas  outer
                       3 thumbs                     3 thumbs

Rows have 7, 7, 6 and 3 keys.

Tap dances are an array of tables; entry n is ``TD(n)``. Their fields are those of Vial's tap dance entry
(``vial_tap_dance_entry_t``). Slots after the last entry (including any TD(n) used but not listed) are empty.

Combos are an array of tables too: ``keys`` (2-4 trigger keycodes, as they appear in the keymap) and ``output``.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import toml_writer
from .keyboard import COLS, HALVES, ROWS
from .device import Combo, TapDance
from .keycodes import Codec

Matrix = list[list[int]]  # [row][col] keycodes
TD_KEYS = ("on_tap", "on_hold", "on_double_tap", "on_tap_hold")
TD_FIELDS = (*TD_KEYS, "custom_tapping_term")
COMBO_FIELDS = ("keys", "output")


def trim_tap_dances(tds: list[TapDance]) -> list[TapDance]:
    """Drop trailing empty entries (no keycodes set)."""
    tds = [tuple(t) for t in tds]
    while tds and not any(tds[-1][:4]):
        tds.pop()
    return tds


def trim_combos(combos: list[Combo]) -> list[Combo]:
    """Drop trailing empty entries (no keycodes set)."""
    combos = [tuple(c) for c in combos]
    while combos and not any(combos[-1]):
        combos.pop()
    return combos


@dataclass
class Keymap:
    layers: list[Matrix]                                      # entry n = layer n
    settings: dict[str, int | bool] = field(default_factory=dict)
    tap_dance: list[TapDance] = field(default_factory=list)   # entry n = TD(n); trailing empty ones trimmed
    combo: list[Combo] = field(default_factory=list)          # trailing empty ones trimmed

    def raw(self) -> list[Matrix]:
        return self.layers


# ---------------------------------------------------------------- write
def _half_rows(grid, matrix: Matrix, codec: Codec) -> list[list[str]]:
    return [[codec.decode(matrix[p[0]][p[1]]) for p in line if p] for line in grid]


def dump(km: Keymap) -> str:
    codec = Codec()
    doc = {
        "settings": dict(km.settings),
        "layer": [{half: _half_rows(grid, m, codec) for half, grid in HALVES.items()} for m in km.layers],
    }
    if km.tap_dance:
        doc["tap_dance"] = [{**{k: codec.decode(v) for k, v in zip(TD_KEYS, td)}, "custom_tapping_term": td[4]}
                            for td in km.tap_dance]
    if km.combo:
        doc["combo"] = [{"keys": [codec.decode(k) for k in c[:4] if k], "output": codec.decode(c[4])}
                        for c in km.combo]
    return toml_writer.dumps(doc, comments={
        "settings": "QMK settings (QMK config.h names)",
        "layer": "Layers: the n-th [[layer]] is layer n (MO(n), LT(n,kc)). Each half: top (7), home (7), bottom (6),\n"
                 "thumbs (3); left-to-right as seen from above. Keycodes: vial-gui names without KC_.\n"
                 "The firmware has a fixed 8 layers and push needs all of them: keep unused ones as all-NO layers.",
        "tap_dance": "Tap dances: the n-th [[tap_dance]] is TD(n). Fields of Vial's tap dance entry;\n"
                     "custom_tapping_term (ms) is also the double-tap window.",
        "combo": "Combos: pressing all of keys together (within COMBO_TERM ms) sends output.",
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
    layers_doc = doc.get("layer") or []
    if not (isinstance(layers_doc, list) and layers_doc and all(isinstance(x, dict) for x in layers_doc)):
        raise KeymapError("needs a non-empty array of [[layer]] tables")
    codec = Codec()
    layers: list[Matrix] = []
    errors = []
    for li, halves in enumerate(layers_doc):
        name = f"layer {li}"
        m = [[0] * COLS for _ in range(ROWS)]
        layers.append(m)
        if set(halves) != set(HALVES):
            errors.append(f"{name}: needs exactly 'left' and 'right'")
            continue
        for half, grid in HALVES.items():
            lines = halves[half]
            if not (isinstance(lines, list) and all(isinstance(ln, list) for ln in lines)):
                errors.append(f"{name} {half}: must be an array of 4 rows")
                continue
            if len(lines) != 4:
                errors.append(f"{name} {half}: expected 4 lines (3 rows + thumbs), got {len(lines)}")
                continue
            for i, (toks, slots) in enumerate(zip(lines, grid)):
                pos = [p for p in slots if p]
                if len(toks) != len(pos) or not all(isinstance(t, str) for t in toks):
                    errors.append(f"{name} {half} row {i + 1}: expected {len(pos)} keycode strings, got {toks}")
                    continue
                for tok, (r, c) in zip(toks, pos):
                    try:
                        m[r][c] = codec.encode(tok)
                    except ValueError as e:
                        errors.append(f"{name} {half} row {i + 1}: {e}")
    tap_dance = _parse_tap_dances(doc.get("tap_dance", []), codec, errors)
    combo = _parse_combos(doc.get("combo", []), codec, errors)
    if errors:
        raise KeymapError("\n".join(errors))
    return Keymap(layers, dict(doc.get("settings") or {}), tap_dance, combo)


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


def _parse_combos(entries, codec: Codec, errors: list[str]) -> list[Combo]:
    if not (isinstance(entries, list) and all(isinstance(e, dict) for e in entries)):
        errors.append("combo: must be an array of tables ([[combo]])")
        return []
    out = []
    for i, e in enumerate(entries):
        if set(e) != set(COMBO_FIELDS):
            errors.append(f"combo {i}: needs exactly {', '.join(COMBO_FIELDS)}")
            continue
        keys = e["keys"]
        if not (isinstance(keys, list) and 2 <= len(keys) <= 4 and all(isinstance(k, str) for k in keys)):
            errors.append(f"combo {i}.keys: expected 2-4 keycode strings, got {keys!r}")
            continue
        try:
            if not isinstance(e["output"], str):
                raise ValueError(f"expected a keycode string, got {e['output']!r}")
            enc = [codec.encode(k) for k in keys]
            out.append((*enc, *[0] * (4 - len(enc)), codec.encode(e["output"])))
        except ValueError as err:
            errors.append(f"combo {i}: {err}")
    return out


def load(path: Path) -> Keymap:
    return parse(path.read_text())
