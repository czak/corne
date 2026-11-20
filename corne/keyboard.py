"""Everything specific to the PandaKB W-Corne v4.1 (46 keys, Vial firmware)."""
from __future__ import annotations

# USB IDs of the 2.4G dongle
VID, PID = 0x55D4, 0x0461

# Switch matrix size
ROWS, COLS = 4, 12

Pos = tuple[int, int]  # (matrix row, matrix col)
_ = None

# Physical rows of each half, as seen from above, left to right: top, home, bottom, thumbs.
# This defines the shape of the row arrays in the TOML files (backups, kb dump). None = no key in that slot.
LEFT: list[list[Pos | None]] = [
    [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (0, 5), (3, 0)],
    [(1, 0), (1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (3, 1)],
    [(2, 0), (2, 1), (2, 2), (2, 3), (2, 4), (2, 5), _],
    [_, _, _, (3, 3), (3, 4), (3, 5), _],
]
RIGHT: list[list[Pos | None]] = [
    [(0, 6), (0, 7), (0, 8), (0, 9), (0, 10), (0, 11), (3, 9)],
    [(1, 6), (1, 7), (1, 8), (1, 9), (1, 10), (1, 11), (3, 10)],
    [_, (2, 7), (2, 8), (2, 9), (2, 10), (2, 11), (3, 11)],
    [_, (3, 6), (3, 7), (3, 8), _, _, _],
]
HALVES = {"left": LEFT, "right": RIGHT}
POSITIONS: list[Pos] = [p for g in (LEFT, RIGHT) for line in g for p in line if p]
assert len(POSITIONS) == 46 and len(set(POSITIONS)) == 46

# Key shapes for drawing, in key units (1 = one key width), from the keyboard's Vial definition:
# pos: (x, y, width, height[, rotation degrees, rotation center x, rotation center y])
GEOMETRY: dict[Pos, tuple[float, ...]] = {
    (0, 0):   (0.5, 1.375, 1, 1),
    (0, 1):   (1.5, 1.375, 1, 1),
    (0, 2):   (2.5, 1.125, 1, 1),
    (0, 3):   (3.5, 1, 1, 1),
    (0, 4):   (4.5, 1.125, 1, 1),
    (0, 5):   (5.5, 1.25, 1, 1),
    (3, 0):   (6.5, 1.75, 1, 1),
    (1, 0):   (0.5, 2.375, 1, 1),
    (1, 1):   (1.5, 2.375, 1, 1),
    (1, 2):   (2.5, 2.125, 1, 1),
    (1, 3):   (3.5, 2, 1, 1),
    (1, 4):   (4.5, 2.125, 1, 1),
    (1, 5):   (5.5, 2.25, 1, 1),
    (3, 1):   (6.5, 2.75, 1, 1),
    (2, 0):   (0.5, 3.375, 1, 1),
    (2, 1):   (1.5, 3.375, 1, 1),
    (2, 2):   (2.5, 3.125, 1, 1),
    (2, 3):   (3.5, 3, 1, 1),
    (2, 4):   (4.5, 3.125, 1, 1),
    (2, 5):   (5.5, 3.25, 1, 1),
    (3, 3):   (4, 4.25, 1, 1),
    (3, 4):   (4, 4.25, 1, 1, 15, 4.5, 9.1),
    (3, 5):   (4, 4.25, 1, 1.5, 30, 5.4, 9.3),
    (0, 6):   (9, 1.75, 1, 1),
    (0, 7):   (10, 1.25, 1, 1),
    (0, 8):   (11, 1.125, 1, 1),
    (0, 9):   (12, 1, 1, 1),
    (0, 10):  (13, 1.125, 1, 1),
    (0, 11):  (14, 1.375, 1, 1),
    (3, 9):   (15, 1.375, 1, 1),
    (1, 6):   (9, 2.75, 1, 1),
    (1, 7):   (10, 2.25, 1, 1),
    (1, 8):   (11, 2.125, 1, 1),
    (1, 9):   (12, 2, 1, 1),
    (1, 10):  (13, 2.125, 1, 1),
    (1, 11):  (14, 2.375, 1, 1),
    (3, 10):  (15, 2.375, 1, 1),
    (2, 7):   (10, 3.25, 1, 1),
    (2, 8):   (11, 3.125, 1, 1),
    (2, 9):   (12, 3, 1, 1),
    (2, 10):  (13, 3.125, 1, 1),
    (2, 11):  (14, 3.375, 1, 1),
    (3, 11):  (15, 3.375, 1, 1),
    (3, 6):   (11.5, 4.25, 1, 1.5, -30, 11.1, 9.3),
    (3, 7):   (11.5, 4.25, 1, 1, -15, 12, 9.1),
    (3, 8):   (11.5, 4.25, 1, 1),
}
assert set(GEOMETRY) == set(POSITIONS)
