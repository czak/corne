"""Talk to a Vial keyboard over Linux hidraw (VIA + Vial raw-HID protocol)."""
from __future__ import annotations

import os
import select
import struct
from pathlib import Path

from .keyboard import COLS, PID, ROWS, VID

MSG_LEN = 32

# VIA commands
ID_GET_PROTOCOL_VERSION = 0x01
ID_DYNAMIC_KEYMAP_SET_KEYCODE = 0x05
ID_DYNAMIC_KEYMAP_GET_LAYER_COUNT = 0x11
ID_DYNAMIC_KEYMAP_GET_BUFFER = 0x12
# Vial commands (prefixed with 0xFE)
VIAL = 0xFE
VIAL_QMK_SETTINGS_QUERY = 0x09
VIAL_QMK_SETTINGS_GET = 0x0A
VIAL_QMK_SETTINGS_SET = 0x0B
VIAL_DYNAMIC_ENTRY_OP = 0x0D
# Vial dynamic entry sub-commands
DYNAMIC_VIAL_GET_NUMBER_OF_ENTRIES = 0x00
DYNAMIC_VIAL_TAP_DANCE_GET = 0x01
DYNAMIC_VIAL_TAP_DANCE_SET = 0x02
DYNAMIC_VIAL_COMBO_GET = 0x03
DYNAMIC_VIAL_COMBO_SET = 0x04

TapDance = tuple[int, int, int, int, int]  # on_tap, on_hold, on_double_tap, on_tap_hold, custom_tapping_term
Combo = tuple[int, int, int, int, int]     # 4 trigger keys (unused ones KC_NO), output


class DeviceError(RuntimeError):
    pass


def find_hidraw(vid: int = VID, pid: int = PID) -> str:
    """Return the /dev/hidrawN of the raw-HID interface (usage page 0xFF60)."""
    want = f"{vid:08X}:{pid:08X}"
    for d in sorted(Path("/sys/class/hidraw").glob("hidraw*")):
        uevent = (d / "device" / "uevent").read_text()
        if want not in uevent.upper():
            continue
        desc = (d / "device" / "report_descriptor").read_bytes()
        if desc.startswith(b"\x06\x60\xff"):
            return f"/dev/{d.name}"
    raise DeviceError(f"keyboard {vid:04x}:{pid:04x} not found (is the 2.4G dongle plugged in?)")


class Keyboard:
    def __init__(self, path: str | None = None, rows: int = ROWS, cols: int = COLS):
        self.path = path or find_hidraw()
        self.rows, self.cols = rows, cols
        self.fd = os.open(self.path, os.O_RDWR)
        self._drain()

    def close(self):
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _drain(self):
        while select.select([self.fd], [], [], 0)[0]:
            os.read(self.fd, 64)

    def xfer(self, *payload: int | bytes, retries: int = 3) -> bytes:
        msg = b"".join(bytes([p]) if isinstance(p, int) else p for p in payload)
        msg = msg.ljust(MSG_LEN, b"\x00")
        for _ in range(retries):
            os.write(self.fd, b"\x00" + msg)  # report id 0
            if select.select([self.fd], [], [], 1.0)[0]:
                return os.read(self.fd, 64)
        raise DeviceError(f"no response to command 0x{msg[0]:02x} (keyboard asleep or out of range?)")

    # ---- info
    def via_protocol(self) -> int:
        r = self.xfer(ID_GET_PROTOCOL_VERSION)
        return struct.unpack(">H", r[1:3])[0]

    def layer_count(self) -> int:
        return self.xfer(ID_DYNAMIC_KEYMAP_GET_LAYER_COUNT)[1]

    # ---- keymap
    def read_keymap(self) -> list[list[list[int]]]:
        layers = self.layer_count()
        size = layers * self.rows * self.cols * 2
        buf = bytearray()
        while len(buf) < size:
            n = min(28, size - len(buf))
            off = len(buf)
            r = self.xfer(ID_DYNAMIC_KEYMAP_GET_BUFFER, off >> 8, off & 0xFF, n)
            buf += r[4:4 + n]
        flat = struct.unpack(f">{size // 2}H", bytes(buf))
        rc = self.rows * self.cols
        return [[list(flat[l * rc + r * self.cols:l * rc + (r + 1) * self.cols])
                 for r in range(self.rows)] for l in range(layers)]

    def set_keycode(self, layer: int, row: int, col: int, kc: int):
        r = self.xfer(ID_DYNAMIC_KEYMAP_SET_KEYCODE, layer, row, col, kc >> 8, kc & 0xFF)
        if r[0] != ID_DYNAMIC_KEYMAP_SET_KEYCODE:
            raise DeviceError(f"set_keycode({layer},{row},{col}) rejected: {r[:6].hex()}")

    # ---- QMK settings (Vial)
    def settings_supported(self) -> list[int]:
        qsids: list[int] = []
        cur = 0
        while True:
            r = self.xfer(VIAL, VIAL_QMK_SETTINGS_QUERY, struct.pack("<H", cur))
            ids = struct.unpack("<16H", r[:32])
            for q in ids:
                if q == 0xFFFF:
                    return qsids
                if q >= cur:
                    qsids.append(q)
            cur = max(ids) + 1

    def setting_get(self, qsid: int, width: int) -> int:
        r = self.xfer(VIAL, VIAL_QMK_SETTINGS_GET, struct.pack("<H", qsid))
        if r[0] != 0:
            raise DeviceError(f"setting {qsid}: get failed (status {r[0]})")
        return int.from_bytes(r[1:1 + width], "little")

    def setting_set(self, qsid: int, width: int, value: int):
        r = self.xfer(VIAL, VIAL_QMK_SETTINGS_SET, struct.pack("<H", qsid), value.to_bytes(width, "little"))
        if r[0] != 0:
            raise DeviceError(f"setting {qsid}: set failed (status {r[0]})")

    # ---- tap dance (Vial dynamic entries)
    def tap_dance_count(self) -> int:
        return self.xfer(VIAL, VIAL_DYNAMIC_ENTRY_OP, DYNAMIC_VIAL_GET_NUMBER_OF_ENTRIES)[0]

    def tap_dance_get(self, i: int) -> TapDance:
        r = self.xfer(VIAL, VIAL_DYNAMIC_ENTRY_OP, DYNAMIC_VIAL_TAP_DANCE_GET, i)
        if r[0] != 0:
            raise DeviceError(f"tap dance {i}: get failed (status {r[0]})")
        return struct.unpack("<5H", r[1:11])

    def tap_dance_set(self, i: int, td: TapDance):
        r = self.xfer(VIAL, VIAL_DYNAMIC_ENTRY_OP, DYNAMIC_VIAL_TAP_DANCE_SET, i, struct.pack("<5H", *td))
        if r[0] != 0:
            raise DeviceError(f"tap dance {i}: set failed (status {r[0]})")

    # ---- combos (Vial dynamic entries)
    def combo_count(self) -> int:
        return self.xfer(VIAL, VIAL_DYNAMIC_ENTRY_OP, DYNAMIC_VIAL_GET_NUMBER_OF_ENTRIES)[1]

    def combo_get(self, i: int) -> Combo:
        r = self.xfer(VIAL, VIAL_DYNAMIC_ENTRY_OP, DYNAMIC_VIAL_COMBO_GET, i)
        if r[0] != 0:
            raise DeviceError(f"combo {i}: get failed (status {r[0]})")
        return struct.unpack("<5H", r[1:11])

    def combo_set(self, i: int, combo: Combo):
        r = self.xfer(VIAL, VIAL_DYNAMIC_ENTRY_OP, DYNAMIC_VIAL_COMBO_SET, i, struct.pack("<5H", *combo))
        if r[0] != 0:
            raise DeviceError(f"combo {i}: set failed (status {r[0]})")
