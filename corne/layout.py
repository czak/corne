"""keymap.toml format.

Each half is an array of 4 rows, as seen from above:

    left:                                   right:
      outer  5 alphas  inner-extra            inner-extra  5 alphas  outer
      outer  5 alphas  inner-extra            inner-extra  5 alphas  outer
      outer  5 alphas                                      5 alphas  outer
                       3 thumbs                     3 thumbs

Rows have 7, 7, 6 and 3 keys.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import toml_writer
from .keyboard import COLS, HALVES, POSITIONS, ROWS
from .keycodes import Codec

Matrix = list[list[int]]  # [row][col] keycodes


@dataclass
class Keymap:
    layers: dict[str, Matrix]                       # ordered: layer index = position
    settings: dict[str, int | bool] = field(default_factory=dict)

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
    return toml_writer.dumps(doc, comments={
        "settings": "QMK settings (QMK config.h names)",
        f"layers.{km.names[0]}": "Layer order = layer index. Each half: top (7), home (7), bottom (6), thumbs (3);\n"
                                 "left-to-right as seen from above. Keycodes: vial-gui names without KC_.",
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
    if errors:
        raise KeymapError("\n".join(errors))
    return Keymap(layers, dict(doc.get("settings") or {}))


def load(path: Path) -> Keymap:
    return parse(path.read_text())
