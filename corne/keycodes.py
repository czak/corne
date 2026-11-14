"""QMK v6 keycode codec: 16-bit keycodes <-> readable tokens.

Tokens are vial-gui's primary keycode names without the ``KC_`` prefix (``BSPACE``,
``LCTRL``). Aliases such as ``BSPC`` are accepted on input but never produced::

    NO                  KC_NO
    TRNS                KC_TRNS
    A  SPACE  F14       basic keys
    LCTL(Z)  C_S(Z)     modifiers + key
    LGUI_T(A)           mod-tap
    MT(MOD_LCTL|MOD_LALT,A)   mod-tap without a named shorthand
    LT(NAV,SPACE)       layer-tap (layer by name or number)
    LM(NUM,MOD_LGUI|MOD_LSFT) layer + mods
    MO(NAV) TG(NAV) TO(NAV) DF(NAV) TT(NAV) OSL(NAV) PDF(NAV)
    OSM(MOD_LSFT)       one-shot mod
    TD(0) M0 USER00     tap dance / macro / user keycodes
    0x7C77              anything unknown, as hex

MOD_FNS, MODTAP_FNS and KEYCODES were generated from vial-gui (github.com/vial-kb/vial-gui)
keycodes_v6.py + keycodes.py on 2026-11-14.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache

# ----------------------------------------------------------------- keycode families
# Keycodes that take a parameter (a key, a layer, modifiers or an index), computed from a
# base value as in QMK's quantum_keycodes.h (v6):
#   LCTL(kc), MT(mods,kc)   QK_MODS / QK_MOD_TAP | mods << 8 | kc
#   LT(layer,kc)            QK_LAYER_TAP | layer << 8 | kc
#   LM(layer,mods)          QK_LAYER_MOD | layer << 5 | mods
#   OSM(mods)               QK_ONE_SHOT_MOD | mods
#   TD(n), Mn, USERnn       QK_TAP_DANCE / QK_MACRO / QK_KB + n
QK_MODS, QK_MOD_TAP, QK_LAYER_TAP = 0x0100, 0x2000, 0x4000
QK_LAYER_MOD, QK_ONE_SHOT_MOD = 0x5000, 0x52A0
QK_TAP_DANCE, QK_MACRO, QK_KB = 0x5700, 0x7700, 0x7E00

# Layer functions: NAME(layer) = base + layer (layers 0-31)
LAYER_FNS = {"TO": 0x5200, "MO": 0x5220, "DF": 0x5240, "TG": 0x5260, "OSL": 0x5280, "TT": 0x52C0, "PDF": 0x52E0}
MAX_LAYER = 0x1F

# 5-bit modifier masks used by MT, LM and OSM (bit 4 = right-hand modifiers)
MOD_BITS = {"MOD_LCTL": 0x01, "MOD_LSFT": 0x02, "MOD_LALT": 0x04, "MOD_LGUI": 0x08,
            "MOD_RCTL": 0x11, "MOD_RSFT": 0x12, "MOD_RALT": 0x14, "MOD_RGUI": 0x18,
            "MOD_MEH": 0x07, "MOD_HYPR": 0x0F}

# Modifier functions: NAME(kc) = value | kc
MOD_FNS = {
    "C_S": 0x0300,
    "HYPR": 0x0F00,
    "LALT": 0x0400,
    "LCA": 0x0500,
    "LAG": 0x0C00,
    "LCAG": 0x0D00,
    "LCG": 0x0900,
    "LCTL": 0x0100,
    "LGUI": 0x0800,
    "LSA": 0x0600,
    "LSFT": 0x0200,
    "MEH": 0x0700,
    "RALT": 0x1400,
    "RCG": 0x1900,
    "RCTL": 0x1100,
    "RGUI": 0x1800,
    "RSFT": 0x1200,
    "SGUI": 0x0A00,
}

# Mod-tap functions: NAME(kc) = value | kc
MODTAP_FNS = {
    "ALL_T": 0x2F00,
    "C_S_T": 0x2300,
    "LALT_T": 0x2400,
    "LCA_T": 0x2500,
    "LAG_T": 0x2C00,
    "LCAG_T": 0x2D00,
    "LCG_T": 0x2900,
    "LCTL_T": 0x2100,
    "LGUI_T": 0x2800,
    "LSA_T": 0x2600,
    "LSFT_T": 0x2200,
    "MEH_T": 0x2700,
    "RALT_T": 0x3400,
    "RCAG_T": 0x3D00,
    "RCG_T": 0x3900,
    "RCTL_T": 0x3100,
    "RGUI_T": 0x3800,
    "RSFT_T": 0x3200,
    "SGUI_T": 0x2A00,
}


class KeycodeError(ValueError):
    pass


@dataclass(frozen=True)
class Tables:
    by_name: dict[str, int]        # every accepted spelling -> value (exact keycodes)
    canonical: dict[int, str]      # value -> preferred token
    mod_fns: dict[str, int]        # "LCTL" -> 0x0100 (high byte only)
    mod_fns_rev: dict[int, str]
    modtap_fns: dict[str, int]     # "LCTL_T" -> 0x2100
    modtap_fns_rev: dict[int, str]
    labels: dict[int, str]         # value -> vial-gui display label


@cache
def tables() -> Tables:
    by_name: dict[str, int] = {}
    canonical: dict[int, str] = {}
    labels: dict[int, str] = {}
    for value, name, aliases, lab in KEYCODES:
        canonical[value] = name
        for n in [name, *aliases]:
            by_name[n] = value
        if lab is not None:
            labels[value] = lab
    mod_fns, modtap_fns = MOD_FNS, MODTAP_FNS
    return Tables(by_name, canonical,
                  mod_fns, {v: k for k, v in mod_fns.items()},
                  modtap_fns, {v: k for k, v in modtap_fns.items()},
                  labels)


def label(value: int) -> str | None:
    """vial-gui's display label for a basic keycode (may contain newlines)."""
    return tables().labels.get(value)


# ----------------------------------------------------------------- mods
def mods_to_str(m: int) -> str:
    m &= 0x1F
    for name, bits in MOD_BITS.items():
        if bits == m and name in ("MOD_MEH", "MOD_HYPR"):
            return name
    prefix = "MOD_R" if m & 0x10 else "MOD_L"
    parts = [prefix + n for bit, n in ((1, "CTL"), (2, "SFT"), (4, "ALT"), (8, "GUI")) if m & bit]
    return "|".join(parts) or "0"


def parse_mods(s: str) -> int:
    m = 0
    for part in s.split("|"):
        part = part.strip()
        if part in MOD_BITS:
            m |= MOD_BITS[part]
        elif re.fullmatch(r"0x[0-9a-fA-F]+|\d+", part):
            m |= int(part, 0)
        else:
            raise KeycodeError(f"unknown modifier {part!r}")
    return m


# ----------------------------------------------------------------- codec
class Codec:
    def __init__(self, layer_names: list[str] | None = None):
        self.t = tables()
        self.layer_names = list(layer_names or [])

    def layer_str(self, n: int) -> str:
        return self.layer_names[n] if n < len(self.layer_names) else str(n)

    def parse_layer(self, s: str) -> int:
        if s in self.layer_names:
            return self.layer_names.index(s)
        if s.isdigit():
            return int(s)
        raise KeycodeError(f"unknown layer {s!r} (known: {', '.join(self.layer_names)})")

    def decode(self, v: int) -> str:
        t = self.t
        if v in t.canonical:
            return t.canonical[v]
        hi, lo = v & 0xFF00, v & 0xFF
        basic = t.canonical.get(lo)
        if QK_MODS <= v < QK_MOD_TAP and basic and hi in t.mod_fns_rev:
            return f"{t.mod_fns_rev[hi]}({basic})"
        if QK_MOD_TAP <= v < QK_LAYER_TAP and basic:
            if hi in t.modtap_fns_rev:
                return f"{t.modtap_fns_rev[hi]}({basic})"
            return f"MT({mods_to_str(v >> 8)},{basic})"
        if QK_LAYER_TAP <= v < 0x5000 and basic:
            return f"LT({self.layer_str((v >> 8) & 0xF)},{basic})"
        if QK_LAYER_MOD <= v < 0x5200:
            return f"LM({self.layer_str((v >> 5) & 0xF)},{mods_to_str(v)})"
        if QK_ONE_SHOT_MOD <= v < QK_ONE_SHOT_MOD + 0x20:
            return f"OSM({mods_to_str(v)})"
        for fn, base in LAYER_FNS.items():
            if base <= v <= base + MAX_LAYER:
                return f"{fn}({self.layer_str(v - base)})"
        if QK_TAP_DANCE <= v < QK_TAP_DANCE + 0x100:
            return f"TD({v - QK_TAP_DANCE})"
        if QK_MACRO <= v < QK_MACRO + 0x100:
            return f"M{v - QK_MACRO}"
        if QK_KB <= v < QK_KB + 64:
            return f"USER{v - QK_KB:02}"
        return f"0x{v:04X}"

    _CALL = re.compile(r"^([A-Z_][A-Z0-9_]*)\((.*)\)$")

    def basic(self, s: str) -> int:
        v = self.encode(s)
        if v > 0xFF:
            raise KeycodeError(f"{s!r} is not a basic keycode (needed inside a function)")
        return v

    def encode(self, tok: str) -> int:
        s = tok.replace(" ", "")
        t = self.t
        if s.startswith("KC_"):
            s = s[3:]
        if s in t.by_name:
            return t.by_name[s]
        if re.fullmatch(r"0x[0-9a-fA-F]{1,4}", s):
            return int(s, 16)
        if m := re.fullmatch(r"USER(\d\d)", s):
            return QK_KB + int(m[1])
        if m := re.fullmatch(r"M(\d+)", s):
            return QK_MACRO + int(m[1])
        m = self._CALL.match(s)
        if not m:
            raise KeycodeError(f"unknown keycode {tok!r}")
        fn, args = m[1], m[2]
        parts = args.split(",")
        try:
            if fn in t.mod_fns and len(parts) == 1:
                return t.mod_fns[fn] | self.basic(parts[0])
            if fn in t.modtap_fns and len(parts) == 1:
                return t.modtap_fns[fn] | self.basic(parts[0])
            if fn == "MT" and len(parts) == 2:
                return QK_MOD_TAP | (parse_mods(parts[0]) & 0x1F) << 8 | self.basic(parts[1])
            if fn == "LT" and len(parts) == 2:
                layer = self.parse_layer(parts[0])
                if layer > 15:
                    raise KeycodeError("LT supports layers 0-15")
                return QK_LAYER_TAP | layer << 8 | self.basic(parts[1])
            if fn == "LM" and len(parts) == 2:
                return QK_LAYER_MOD | (self.parse_layer(parts[0]) & 0xF) << 5 | parse_mods(parts[1]) & 0x1F
            if fn == "OSM" and len(parts) == 1:
                return QK_ONE_SHOT_MOD | parse_mods(parts[0]) & 0x1F
            if fn in LAYER_FNS and len(parts) == 1:
                return LAYER_FNS[fn] + (self.parse_layer(parts[0]) & MAX_LAYER)
            if fn == "TD" and len(parts) == 1:
                return QK_TAP_DANCE + int(parts[0])
        except KeycodeError as e:
            raise KeycodeError(f"{tok!r}: {e}") from None
        raise KeycodeError(f"unknown keycode function {tok!r}")


# ----------------------------------------------------------------- fixed keycodes
# All named keycodes: (value, name, aliases, label).
#   name    - the spelling keymap.toml uses (vial-gui's primary name without KC_)
#   aliases - other accepted spellings; a KC_ prefix is accepted on any name
#   label   - vial-gui's display label, used by the visualization
KEYCODES = [
    (0x0000, "NO", [], ""),
    (0x0001, "TRNS", ["TRANSPARENT"], "▽"),
    (0x0004, "A", [], "A"),
    (0x0005, "B", ["QMK_LM_SHIFT"], "B"),
    (0x0006, "C", [], "C"),
    (0x0007, "D", [], "D"),
    (0x0008, "E", [], "E"),
    (0x0009, "F", [], "F"),
    (0x000A, "G", [], "G"),
    (0x000B, "H", [], "H"),
    (0x000C, "I", [], "I"),
    (0x000D, "J", [], "J"),
    (0x000E, "K", [], "K"),
    (0x000F, "L", [], "L"),
    (0x0010, "M", [], "M"),
    (0x0011, "N", [], "N"),
    (0x0012, "O", [], "O"),
    (0x0013, "P", [], "P"),
    (0x0014, "Q", [], "Q"),
    (0x0015, "R", [], "R"),
    (0x0016, "S", [], "S"),
    (0x0017, "T", [], "T"),
    (0x0018, "U", [], "U"),
    (0x0019, "V", [], "V"),
    (0x001A, "W", [], "W"),
    (0x001B, "X", [], "X"),
    (0x001C, "Y", [], "Y"),
    (0x001D, "Z", [], "Z"),
    (0x001E, "1", [], "!\n1"),
    (0x001F, "2", ["QMK_LM_MASK"], "@\n2"),
    (0x0020, "3", [], "#\n3"),
    (0x0021, "4", [], "$\n4"),
    (0x0022, "5", [], "%\n5"),
    (0x0023, "6", [], "^\n6"),
    (0x0024, "7", [], "&\n7"),
    (0x0025, "8", [], "*\n8"),
    (0x0026, "9", [], "(\n9"),
    (0x0027, "0", [], ")\n0"),
    (0x0028, "ENTER", ["ENT"], "Enter"),
    (0x0029, "ESCAPE", ["ESC"], "Esc"),
    (0x002A, "BSPACE", ["BSPC"], "Bksp"),
    (0x002B, "TAB", [], "Tab"),
    (0x002C, "SPACE", ["SPC"], "Space"),
    (0x002D, "MINUS", ["MINS"], "_\n-"),
    (0x002E, "EQUAL", ["EQL"], "+\n="),
    (0x002F, "LBRACKET", ["LBRC"], "{\n["),
    (0x0030, "RBRACKET", ["RBRC"], "}\n]"),
    (0x0031, "BSLASH", ["BSLS"], "|\n\\"),
    (0x0032, "NONUS_HASH", ["NUHS"], "~\n#"),
    (0x0033, "SCOLON", ["SCLN"], ":\n;"),
    (0x0034, "QUOTE", ["QUOT"], "\"\n'"),
    (0x0035, "GRAVE", ["GRV", "ZKHK"], "~\n`"),
    (0x0036, "COMMA", ["COMM"], "<\n,"),
    (0x0037, "DOT", [], ">\n."),
    (0x0038, "SLASH", ["SLSH"], "?\n/"),
    (0x0039, "CAPSLOCK", ["CLCK", "CAPS"], "Caps\nLock"),
    (0x003A, "F1", [], "F1"),
    (0x003B, "F2", [], "F2"),
    (0x003C, "F3", [], "F3"),
    (0x003D, "F4", [], "F4"),
    (0x003E, "F5", [], "F5"),
    (0x003F, "F6", [], "F6"),
    (0x0040, "F7", [], "F7"),
    (0x0041, "F8", [], "F8"),
    (0x0042, "F9", [], "F9"),
    (0x0043, "F10", [], "F10"),
    (0x0044, "F11", [], "F11"),
    (0x0045, "F12", [], "F12"),
    (0x0046, "PSCREEN", ["PSCR"], "Print\nScreen"),
    (0x0047, "SCROLLLOCK", ["SLCK", "BRMD"], "Scroll\nLock"),
    (0x0048, "PAUSE", ["PAUS", "BRK", "BRMU"], "Pause"),
    (0x0049, "INSERT", ["INS"], "Insert"),
    (0x004A, "HOME", [], "Home"),
    (0x004B, "PGUP", [], "Page\nUp"),
    (0x004C, "DELETE", ["DEL"], "Del"),
    (0x004D, "END", [], "End"),
    (0x004E, "PGDOWN", ["PGDN"], "Page\nDown"),
    (0x004F, "RIGHT", ["RGHT"], "Right"),
    (0x0050, "LEFT", [], "Left"),
    (0x0051, "DOWN", [], "Down"),
    (0x0052, "UP", [], "Up"),
    (0x0053, "NUMLOCK", ["NLCK"], "Num\nLock"),
    (0x0054, "KP_SLASH", ["PSLS"], "/"),
    (0x0055, "KP_ASTERISK", ["PAST"], "*"),
    (0x0056, "KP_MINUS", ["PMNS"], "-"),
    (0x0057, "KP_PLUS", ["PPLS"], "+"),
    (0x0058, "KP_ENTER", ["PENT"], "Num\nEnter"),
    (0x0059, "KP_1", ["P1"], "1"),
    (0x005A, "KP_2", ["P2"], "2"),
    (0x005B, "KP_3", ["P3"], "3"),
    (0x005C, "KP_4", ["P4"], "4"),
    (0x005D, "KP_5", ["P5"], "5"),
    (0x005E, "KP_6", ["P6"], "6"),
    (0x005F, "KP_7", ["P7"], "7"),
    (0x0060, "KP_8", ["P8"], "8"),
    (0x0061, "KP_9", ["P9"], "9"),
    (0x0062, "KP_0", ["P0"], "0"),
    (0x0063, "KP_DOT", ["PDOT"], "."),
    (0x0064, "NONUS_BSLASH", ["NUBS"], "|\n\\"),
    (0x0065, "APPLICATION", ["APP"], "Menu"),
    (0x0067, "KP_EQUAL", ["PEQL"], "="),
    (0x0068, "F13", [], "F13"),
    (0x0069, "F14", [], "F14"),
    (0x006A, "F15", [], "F15"),
    (0x006B, "F16", [], "F16"),
    (0x006C, "F17", [], "F17"),
    (0x006D, "F18", [], "F18"),
    (0x006E, "F19", [], "F19"),
    (0x006F, "F20", [], "F20"),
    (0x0070, "F21", [], "F21"),
    (0x0071, "F22", [], "F22"),
    (0x0072, "F23", [], "F23"),
    (0x0073, "F24", [], "F24"),
    (0x0074, "EXEC", ["EXECUTE"], "Exec"),
    (0x0075, "HELP", [], "Help"),
    (0x0077, "SLCT", ["SELECT"], "Select"),
    (0x0078, "STOP", [], "Stop"),
    (0x0079, "AGIN", ["AGAIN"], "Again"),
    (0x007A, "UNDO", [], "Undo"),
    (0x007B, "CUT", [], "Cut"),
    (0x007C, "COPY", [], "Copy"),
    (0x007D, "PSTE", ["PASTE"], "Paste"),
    (0x007E, "FIND", [], "Find"),
    (0x0080, "_VOLUP", [], "Vol +\nAlt"),
    (0x0081, "_VOLDOWN", [], "Vol -\nAlt"),
    (0x0082, "LCAP", ["LOCKING_CAPS"], "Locking\nCaps"),
    (0x0083, "LNUM", ["LOCKING_NUM"], "Locking\nNum"),
    (0x0084, "LSCR", ["LOCKING_SCROLL"], "Locking\nScroll"),
    (0x0085, "KP_COMMA", ["PCMM"], ","),
    (0x0087, "RO", ["INT1"], "_\n\\"),
    (0x0088, "KANA", ["INT2"], "カタカナ\nひらがな"),
    (0x0089, "JYEN", ["INT3"], "|\n¥"),
    (0x008A, "HENK", ["INT4"], "変換"),
    (0x008B, "MHEN", ["INT5"], "無変換"),
    (0x0090, "LANG1", ["HAEN"], "한영\nかな"),
    (0x0091, "LANG2", ["HANJ"], "漢字\n英数"),
    (0x00A5, "PWR", ["SYSTEM_POWER"], "Power"),
    (0x00A6, "SLEP", ["SYSTEM_SLEEP"], "Sleep"),
    (0x00A7, "WAKE", ["SYSTEM_WAKE"], "Wake"),
    (0x00A8, "MUTE", ["AUDIO_MUTE"], "Mute"),
    (0x00A9, "VOLU", ["AUDIO_VOL_UP"], "Vol +"),
    (0x00AA, "VOLD", ["AUDIO_VOL_DOWN"], "Vol -"),
    (0x00AB, "MNXT", ["MEDIA_NEXT_TRACK"], "Media\nNext"),
    (0x00AC, "MPRV", ["MEDIA_PREV_TRACK"], "Media\nPrev"),
    (0x00AD, "MSTP", ["MEDIA_STOP"], "Media\nStop"),
    (0x00AE, "MPLY", ["MEDIA_PLAY_PAUSE"], "Media\nPlay"),
    (0x00AF, "MSEL", ["MEDIA_SELECT"], "Media\nPlayer"),
    (0x00B0, "EJCT", ["MEDIA_EJECT"], "Eject"),
    (0x00B1, "MAIL", [], "Mail"),
    (0x00B2, "CALC", ["CALCULATOR"], "Calc"),
    (0x00B3, "MYCM", ["MY_COMPUTER"], "My\nPC"),
    (0x00B4, "WSCH", ["WWW_SEARCH"], "Browser\nSearch"),
    (0x00B5, "WHOM", ["WWW_HOME"], "Browser\nHome"),
    (0x00B6, "WBAK", ["WWW_BACK"], "Browser\nBack"),
    (0x00B7, "WFWD", ["WWW_FORWARD"], "Browser\nForward"),
    (0x00B8, "WSTP", ["WWW_STOP"], "Browser\nStop"),
    (0x00B9, "WREF", ["WWW_REFRESH"], "Browser\nRefresh"),
    (0x00BA, "WFAV", ["WWW_FAVORITES"], "Browser\nFav."),
    (0x00BB, "MFFD", ["MEDIA_FAST_FORWARD"], "Next\nTrack\n(macOS)"),
    (0x00BC, "MRWD", ["MEDIA_REWIND"], "Prev\nTrack\n(macOS)"),
    (0x00BD, "BRIU", ["BRIGHTNESS_UP"], "Bright.\nUp"),
    (0x00BE, "BRID", ["BRIGHTNESS_DOWN"], "Bright.\nDown"),
    (0x00CD, "MS_U", ["MS_UP"], "Mouse\nUp"),
    (0x00CE, "MS_D", ["MS_DOWN"], "Mouse\nDown"),
    (0x00CF, "MS_L", ["MS_LEFT"], "Mouse\nLeft"),
    (0x00D0, "MS_R", ["MS_RIGHT"], "Mouse\nRight"),
    (0x00D1, "BTN1", ["MS_BTN1"], "Mouse\n1"),
    (0x00D2, "BTN2", ["MS_BTN2"], "Mouse\n2"),
    (0x00D3, "BTN3", ["MS_BTN3"], "Mouse\n3"),
    (0x00D4, "BTN4", ["MS_BTN4"], "Mouse\n4"),
    (0x00D5, "BTN5", ["MS_BTN5"], "Mouse\n5"),
    (0x00D9, "WH_U", ["MS_WH_UP"], "Mouse\nWheel\nUp"),
    (0x00DA, "WH_D", ["MS_WH_DOWN"], "Mouse\nWheel\nDown"),
    (0x00DB, "WH_L", ["MS_WH_LEFT"], "Mouse\nWheel\nLeft"),
    (0x00DC, "WH_R", ["MS_WH_RIGHT"], "Mouse\nWheel\nRight"),
    (0x00DD, "ACL0", ["MS_ACCEL0"], "Mouse\nAccel\n0"),
    (0x00DE, "ACL1", ["MS_ACCEL1"], "Mouse\nAccel\n1"),
    (0x00DF, "ACL2", ["MS_ACCEL2"], "Mouse\nAccel\n2"),
    (0x00E0, "LCTRL", ["LCTL"], "LCtrl"),
    (0x00E1, "LSHIFT", ["LSFT"], "LShift"),
    (0x00E2, "LALT", ["LOPT"], "LAlt"),
    (0x00E3, "LGUI", ["LCMD", "LWIN"], "LGui"),
    (0x00E4, "RCTRL", ["RCTL"], "RCtrl"),
    (0x00E5, "RSHIFT", ["RSFT"], "RShift"),
    (0x00E6, "RALT", ["ALGR", "ROPT"], "RAlt"),
    (0x00E7, "RGUI", ["RCMD", "RWIN"], "RGui"),
    (0x021E, "EXLM", [], "!"),
    (0x021F, "AT", [], "@"),
    (0x0220, "HASH", [], "#"),
    (0x0221, "DLR", [], "$"),
    (0x0222, "PERC", [], "%"),
    (0x0223, "CIRC", [], "^"),
    (0x0224, "AMPR", [], "&"),
    (0x0225, "ASTR", [], "*"),
    (0x0226, "LPRN", [], "("),
    (0x0227, "RPRN", [], ")"),
    (0x022D, "UNDS", [], "_"),
    (0x022E, "PLUS", [], "+"),
    (0x022F, "LCBR", [], "{"),
    (0x0230, "RCBR", [], "}"),
    (0x0231, "PIPE", [], "|"),
    (0x0233, "COLN", [], ":"),
    (0x0234, "DQUO", [], "\""),
    (0x0235, "TILD", [], "~"),
    (0x0236, "LT", [], "<"),
    (0x0237, "GT", [], ">"),
    (0x0238, "QUES", [], "?"),
    (0x52A1, "OSM(MOD_LCTL)", [], "OSM\nLCtl"),
    (0x52A2, "OSM(MOD_LSFT)", [], "OSM\nLSft"),
    (0x52A3, "OSM(MOD_LCTL|MOD_LSFT)", [], "OSM\nCS"),
    (0x52A4, "OSM(MOD_LALT)", [], "OSM\nLAlt"),
    (0x52A5, "OSM(MOD_LCTL|MOD_LALT)", [], "OSM\nCA"),
    (0x52A6, "OSM(MOD_LSFT|MOD_LALT)", [], "OSM\nSA"),
    (0x52A7, "OSM(MOD_MEH)", [], "OSM\nMeh"),
    (0x52A8, "OSM(MOD_LGUI)", [], "OSM\nLGUI"),
    (0x52A9, "OSM(MOD_LCTL|MOD_LGUI)", [], "OSM\nCG"),
    (0x52AA, "OSM(MOD_LSFT|MOD_LGUI)", [], "OSM\nSG"),
    (0x52AB, "OSM(MOD_LCTL|MOD_LSFT|MOD_LGUI)", [], "OSM\nCSG"),
    (0x52AC, "OSM(MOD_LALT|MOD_LGUI)", [], "OSM\nAG"),
    (0x52AD, "OSM(MOD_LCTL|MOD_LALT|MOD_LGUI)", [], "OSM\nCAG"),
    (0x52AE, "OSM(MOD_LSFT|MOD_LALT|MOD_LGUI)", [], "OSM\nSAG"),
    (0x52AF, "OSM(MOD_HYPR)", [], "OSM\nHyper"),
    (0x52B1, "OSM(MOD_RCTL)", [], "OSM\nRCtl"),
    (0x52B2, "OSM(MOD_RSFT)", [], "OSM\nRSft"),
    (0x52B3, "OSM(MOD_RCTL|MOD_RSFT)", [], "OSM\nRCS"),
    (0x52B4, "OSM(MOD_RALT)", [], "OSM\nRAlt"),
    (0x52B5, "OSM(MOD_RCTL|MOD_RALT)", [], "OSM\nRCA"),
    (0x52B6, "OSM(MOD_RSFT|MOD_RALT)", [], "OSM\nRSA"),
    (0x52B7, "OSM(MOD_RCTL|MOD_RSFT|MOD_RALT)", [], "OSM\nRMeh"),
    (0x52B8, "OSM(MOD_RGUI)", [], "OSM\nRGUI"),
    (0x52B9, "OSM(MOD_RCTL|MOD_RGUI)", [], "OSM\nRCG"),
    (0x52BA, "OSM(MOD_RSFT|MOD_RGUI)", [], "OSM\nRSG"),
    (0x52BB, "OSM(MOD_RCTL|MOD_RSFT|MOD_RGUI)", [], "OSM\nRCSG"),
    (0x52BC, "OSM(MOD_RALT|MOD_RGUI)", [], "OSM\nRAG"),
    (0x52BD, "OSM(MOD_RCTL|MOD_RALT|MOD_RGUI)", [], "OSM\nRCAG"),
    (0x52BE, "OSM(MOD_RSFT|MOD_RALT|MOD_RGUI)", [], "OSM\nRSAG"),
    (0x52BF, "OSM(MOD_RCTL|MOD_RSFT|MOD_RALT|MOD_RGUI)", [], "OSM\nRHyp"),
    (0x7000, "MAGIC_SWAP_CONTROL_CAPSLOCK", ["CL_SWAP"], "Swap\nCtrl\nCaps"),
    (0x7001, "MAGIC_UNSWAP_CONTROL_CAPSLOCK", ["CL_NORM"], "Unswap\nCtrl\nCaps"),
    (0x7003, "MAGIC_UNCAPSLOCK_TO_CONTROL", ["CL_CAPS"], "Caps\nnot to\nCtrl"),
    (0x7004, "MAGIC_CAPSLOCK_TO_CONTROL", ["CL_CTRL"], "Caps\nto\nCtrl"),
    (0x7005, "MAGIC_SWAP_LALT_LGUI", ["LAG_SWP"], "Swap\nLAlt\nLGui"),
    (0x7006, "MAGIC_UNSWAP_LALT_LGUI", ["LAG_NRM"], "Unswap\nLAlt\nLGui"),
    (0x7007, "MAGIC_SWAP_RALT_RGUI", ["RAG_SWP"], "Swap\nRAlt\nRGui"),
    (0x7008, "MAGIC_UNSWAP_RALT_RGUI", ["RAG_NRM"], "Unswap\nRAlt\nRGui"),
    (0x7009, "MAGIC_UNNO_GUI", ["GUI_ON"], "GUI\nOn"),
    (0x700A, "MAGIC_NO_GUI", ["GUI_OFF"], "GUI\nOff"),
    (0x700B, "MAGIC_TOGGLE_GUI", ["GUI_TOGG"], "GUI\nToggle"),
    (0x700C, "MAGIC_SWAP_GRAVE_ESC", ["GE_SWAP"], "Swap\n`\nEsc"),
    (0x700D, "MAGIC_UNSWAP_GRAVE_ESC", ["GE_NORM"], "Unswap\n`\nEsc"),
    (0x700E, "MAGIC_SWAP_BACKSLASH_BACKSPACE", ["BS_SWAP"], "Swap\n\\\nBS"),
    (0x700F, "MAGIC_UNSWAP_BACKSLASH_BACKSPACE", ["BS_NORM"], "Unswap\n\\\nBS"),
    (0x7011, "MAGIC_HOST_NKRO", ["NK_ON"], "NKRO\nOn"),
    (0x7012, "MAGIC_UNHOST_NKRO", ["NK_OFF"], "NKRO\nOff"),
    (0x7013, "MAGIC_TOGGLE_NKRO", ["NK_TOGG"], "NKRO\nToggle"),
    (0x7014, "MAGIC_SWAP_ALT_GUI", ["AG_SWAP"], "Swap\nAlt\nGui"),
    (0x7015, "MAGIC_UNSWAP_ALT_GUI", ["AG_NORM"], "Unswap\nAlt\nGui"),
    (0x7016, "MAGIC_TOGGLE_ALT_GUI", ["AG_TOGG"], "Toggle\nAlt\nGui"),
    (0x7017, "MAGIC_SWAP_LCTL_LGUI", ["LCG_SWP"], "Swap\nLCtl\nLGui"),
    (0x7018, "MAGIC_UNSWAP_LCTL_LGUI", ["LCG_NRM"], "Unswap\nLCtl\nLGui"),
    (0x7019, "MAGIC_SWAP_RCTL_RGUI", ["RCG_SWP"], "Swap\nRCtl\nRGui"),
    (0x701A, "MAGIC_UNSWAP_RCTL_RGUI", ["RCG_NRM"], "Unswap\nRCtl\nRGui"),
    (0x701B, "MAGIC_SWAP_CTL_GUI", ["CG_SWAP"], "Swap\nCtl\nGui"),
    (0x701C, "MAGIC_UNSWAP_CTL_GUI", ["CG_NORM"], "Unswap\nCtl\nGui"),
    (0x701D, "MAGIC_TOGGLE_CTL_GUI", ["CG_TOGG"], "Toggle\nCtl\nGui"),
    (0x701E, "MAGIC_EE_HANDS_LEFT", ["EH_LEFT"], "EEH\nLeft"),
    (0x701F, "MAGIC_EE_HANDS_RIGHT", ["EH_RGHT"], "EEH\nRight"),
    (0x7103, "MI_C", [], "ᴹᴵᴰᴵ\nC"),
    (0x7104, "MI_Cs", ["MI_Db"], "ᴹᴵᴰᴵ\nC#/Dᵇ"),
    (0x7105, "MI_D", [], "ᴹᴵᴰᴵ\nD"),
    (0x7106, "MI_Ds", ["MI_Eb"], "ᴹᴵᴰᴵ\nD#/Eᵇ"),
    (0x7107, "MI_E", [], "ᴹᴵᴰᴵ\nE"),
    (0x7108, "MI_F", [], "ᴹᴵᴰᴵ\nF"),
    (0x7109, "MI_Fs", ["MI_Gb"], "ᴹᴵᴰᴵ\nF#/Gᵇ"),
    (0x710A, "MI_G", [], "ᴹᴵᴰᴵ\nG"),
    (0x710B, "MI_Gs", ["MI_Ab"], "ᴹᴵᴰᴵ\nG#/Aᵇ"),
    (0x710C, "MI_A", [], "ᴹᴵᴰᴵ\nA"),
    (0x710D, "MI_As", ["MI_Bb"], "ᴹᴵᴰᴵ\nA#/Bᵇ"),
    (0x710E, "MI_B", [], "ᴹᴵᴰᴵ\nB"),
    (0x710F, "MI_C_1", [], "ᴹᴵᴰᴵ\nC₁"),
    (0x7110, "MI_Cs_1", ["MI_Db_1"], "ᴹᴵᴰᴵ\nC#₁/Dᵇ₁"),
    (0x7111, "MI_D_1", [], "ᴹᴵᴰᴵ\nD₁"),
    (0x7112, "MI_Ds_1", ["MI_Eb_1"], "ᴹᴵᴰᴵ\nD#₁/Eᵇ₁"),
    (0x7113, "MI_E_1", [], "ᴹᴵᴰᴵ\nE₁"),
    (0x7114, "MI_F_1", [], "ᴹᴵᴰᴵ\nF₁"),
    (0x7115, "MI_Fs_1", ["MI_Gb_1"], "ᴹᴵᴰᴵ\nF#₁/Gᵇ₁"),
    (0x7116, "MI_G_1", [], "ᴹᴵᴰᴵ\nG₁"),
    (0x7117, "MI_Gs_1", ["MI_Ab_1"], "ᴹᴵᴰᴵ\nG#₁/Aᵇ₁"),
    (0x7118, "MI_A_1", [], "ᴹᴵᴰᴵ\nA₁"),
    (0x7119, "MI_As_1", ["MI_Bb_1"], "ᴹᴵᴰᴵ\nA#₁/Bᵇ₁"),
    (0x711A, "MI_B_1", [], "ᴹᴵᴰᴵ\nB₁"),
    (0x711B, "MI_C_2", [], "ᴹᴵᴰᴵ\nC₂"),
    (0x711C, "MI_Cs_2", ["MI_Db_2"], "ᴹᴵᴰᴵ\nC#₂/Dᵇ₂"),
    (0x711D, "MI_D_2", [], "ᴹᴵᴰᴵ\nD₂"),
    (0x711E, "MI_Ds_2", ["MI_Eb_2"], "ᴹᴵᴰᴵ\nD#₂/Eᵇ₂"),
    (0x711F, "MI_E_2", [], "ᴹᴵᴰᴵ\nE₂"),
    (0x7120, "MI_F_2", [], "ᴹᴵᴰᴵ\nF₂"),
    (0x7121, "MI_Fs_2", ["MI_Gb_2"], "ᴹᴵᴰᴵ\nF#₂/Gᵇ₂"),
    (0x7122, "MI_G_2", [], "ᴹᴵᴰᴵ\nG₂"),
    (0x7123, "MI_Gs_2", ["MI_Ab_2"], "ᴹᴵᴰᴵ\nG#₂/Aᵇ₂"),
    (0x7124, "MI_A_2", [], "ᴹᴵᴰᴵ\nA₂"),
    (0x7125, "MI_As_2", ["MI_Bb_2"], "ᴹᴵᴰᴵ\nA#₂/Bᵇ₂"),
    (0x7126, "MI_B_2", [], "ᴹᴵᴰᴵ\nB₂"),
    (0x7127, "MI_C_3", [], "ᴹᴵᴰᴵ\nC₃"),
    (0x7128, "MI_Cs_3", ["MI_Db_3"], "ᴹᴵᴰᴵ\nC#₃/Dᵇ₃"),
    (0x7129, "MI_D_3", [], "ᴹᴵᴰᴵ\nD₃"),
    (0x712A, "MI_Ds_3", ["MI_Eb_3"], "ᴹᴵᴰᴵ\nD#₃/Eᵇ₃"),
    (0x712B, "MI_E_3", [], "ᴹᴵᴰᴵ\nE₃"),
    (0x712C, "MI_F_3", [], "ᴹᴵᴰᴵ\nF₃"),
    (0x712D, "MI_Fs_3", ["MI_Gb_3"], "ᴹᴵᴰᴵ\nF#₃/Gᵇ₃"),
    (0x712E, "MI_G_3", [], "ᴹᴵᴰᴵ\nG₃"),
    (0x712F, "MI_Gs_3", ["MI_Ab_3"], "ᴹᴵᴰᴵ\nG#₃/Aᵇ₃"),
    (0x7130, "MI_A_3", [], "ᴹᴵᴰᴵ\nA₃"),
    (0x7131, "MI_As_3", ["MI_Bb_3"], "ᴹᴵᴰᴵ\nA#₃/Bᵇ₃"),
    (0x7132, "MI_B_3", [], "ᴹᴵᴰᴵ\nB₃"),
    (0x7133, "MI_C_4", [], "ᴹᴵᴰᴵ\nC₄"),
    (0x7134, "MI_Cs_4", ["MI_Db_4"], "ᴹᴵᴰᴵ\nC#₄/Dᵇ₄"),
    (0x7135, "MI_D_4", [], "ᴹᴵᴰᴵ\nD₄"),
    (0x7136, "MI_Ds_4", ["MI_Eb_4"], "ᴹᴵᴰᴵ\nD#₄/Eᵇ₄"),
    (0x7137, "MI_E_4", [], "ᴹᴵᴰᴵ\nE₄"),
    (0x7138, "MI_F_4", [], "ᴹᴵᴰᴵ\nF₄"),
    (0x7139, "MI_Fs_4", ["MI_Gb_4"], "ᴹᴵᴰᴵ\nF#₄/Gᵇ₄"),
    (0x713A, "MI_G_4", [], "ᴹᴵᴰᴵ\nG₄"),
    (0x713B, "MI_Gs_4", ["MI_Ab_4"], "ᴹᴵᴰᴵ\nG#₄/Aᵇ₄"),
    (0x713C, "MI_A_4", [], "ᴹᴵᴰᴵ\nA₄"),
    (0x713D, "MI_As_4", ["MI_Bb_4"], "ᴹᴵᴰᴵ\nA#₄/Bᵇ₄"),
    (0x713E, "MI_B_4", [], "ᴹᴵᴰᴵ\nB₄"),
    (0x713F, "MI_C_5", [], "ᴹᴵᴰᴵ\nC₅"),
    (0x7140, "MI_Cs_5", ["MI_Db_5"], "ᴹᴵᴰᴵ\nC#₅/Dᵇ₅"),
    (0x7141, "MI_D_5", [], "ᴹᴵᴰᴵ\nD₅"),
    (0x7142, "MI_Ds_5", ["MI_Eb_5"], "ᴹᴵᴰᴵ\nD#₅/Eᵇ₅"),
    (0x7143, "MI_E_5", [], "ᴹᴵᴰᴵ\nE₅"),
    (0x7144, "MI_F_5", [], "ᴹᴵᴰᴵ\nF₅"),
    (0x7145, "MI_Fs_5", ["MI_Gb_5"], "ᴹᴵᴰᴵ\nF#₅/Gᵇ₅"),
    (0x7146, "MI_G_5", [], "ᴹᴵᴰᴵ\nG₅"),
    (0x7147, "MI_Gs_5", ["MI_Ab_5"], "ᴹᴵᴰᴵ\nG#₅/Aᵇ₅"),
    (0x7148, "MI_A_5", [], "ᴹᴵᴰᴵ\nA₅"),
    (0x7149, "MI_As_5", ["MI_Bb_5"], "ᴹᴵᴰᴵ\nA#₅/Bᵇ₅"),
    (0x714A, "MI_B_5", [], "ᴹᴵᴰᴵ\nB₅"),
    (0x714B, "MI_OCT_N2", [], "ᴹᴵᴰᴵ\nOct₋₂"),
    (0x714C, "MI_OCT_N1", [], "ᴹᴵᴰᴵ\nOct₋₁"),
    (0x714D, "MI_OCT_0", [], "ᴹᴵᴰᴵ\nOct₀"),
    (0x714E, "MI_OCT_1", [], "ᴹᴵᴰᴵ\nOct₊₁"),
    (0x714F, "MI_OCT_2", [], "ᴹᴵᴰᴵ\nOct₊₂"),
    (0x7150, "MI_OCT_3", [], "ᴹᴵᴰᴵ\nOct₊₃"),
    (0x7151, "MI_OCT_4", [], "ᴹᴵᴰᴵ\nOct₊₄"),
    (0x7152, "MI_OCT_5", [], "ᴹᴵᴰᴵ\nOct₊₅"),
    (0x7153, "MI_OCT_6", [], "ᴹᴵᴰᴵ\nOct₊₆"),
    (0x7154, "MI_OCT_7", [], "ᴹᴵᴰᴵ\nOct₊₇"),
    (0x7155, "MI_OCTD", [], "ᴹᴵᴰᴵ\nOctᴰᴺ"),
    (0x7156, "MI_OCTU", [], "ᴹᴵᴰᴵ\nOctᵁᴾ"),
    (0x7157, "MI_TRNS_N6", [], "ᴹᴵᴰᴵ\nTrans₋₆"),
    (0x7158, "MI_TRNS_N5", [], "ᴹᴵᴰᴵ\nTrans₋₅"),
    (0x7159, "MI_TRNS_N4", [], "ᴹᴵᴰᴵ\nTrans₋₄"),
    (0x715A, "MI_TRNS_N3", [], "ᴹᴵᴰᴵ\nTrans₋₃"),
    (0x715B, "MI_TRNS_N2", [], "ᴹᴵᴰᴵ\nTrans₋₂"),
    (0x715C, "MI_TRNS_N1", [], "ᴹᴵᴰᴵ\nTrans₋₁"),
    (0x715D, "MI_TRNS_0", [], "ᴹᴵᴰᴵ\nTrans₀"),
    (0x715E, "MI_TRNS_1", [], "ᴹᴵᴰᴵ\nTrans₊₁"),
    (0x715F, "MI_TRNS_2", [], "ᴹᴵᴰᴵ\nTrans₊₂"),
    (0x7160, "MI_TRNS_3", [], "ᴹᴵᴰᴵ\nTrans₊₃"),
    (0x7161, "MI_TRNS_4", [], "ᴹᴵᴰᴵ\nTrans₊₄"),
    (0x7162, "MI_TRNS_5", [], "ᴹᴵᴰᴵ\nTrans₊₅"),
    (0x7163, "MI_TRNS_6", [], "ᴹᴵᴰᴵ\nTrans₊₆"),
    (0x7164, "MI_TRNSD", [], "ᴹᴵᴰᴵ\nTransᴰᴺ"),
    (0x7165, "MI_TRNSU", [], "ᴹᴵᴰᴵ\nTransᵁᴾ"),
    (0x7167, "MI_VEL_1", ["MI_VEL_0"], "ᴹᴵᴰᴵ\nVel₁"),
    (0x7168, "MI_VEL_2", [], "ᴹᴵᴰᴵ\nVel₂"),
    (0x7169, "MI_VEL_3", [], "ᴹᴵᴰᴵ\nVel₃"),
    (0x716A, "MI_VEL_4", [], "ᴹᴵᴰᴵ\nVel₄"),
    (0x716B, "MI_VEL_5", [], "ᴹᴵᴰᴵ\nVel₅"),
    (0x716C, "MI_VEL_6", [], "ᴹᴵᴰᴵ\nVel₆"),
    (0x716D, "MI_VEL_7", [], "ᴹᴵᴰᴵ\nVel₇"),
    (0x716E, "MI_VEL_8", [], "ᴹᴵᴰᴵ\nVel₈"),
    (0x716F, "MI_VEL_9", [], "ᴹᴵᴰᴵ\nVel₉"),
    (0x7170, "MI_VEL_10", [], "ᴹᴵᴰᴵ\nVel₁₀"),
    (0x7171, "MI_VELD", [], "ᴹᴵᴰᴵ\nVelᴰᴺ"),
    (0x7172, "MI_VELU", [], "ᴹᴵᴰᴵ\nVelᵁᴾ"),
    (0x7173, "MI_CH1", [], "ᴹᴵᴰᴵ\nCH₁"),
    (0x7174, "MI_CH2", [], "ᴹᴵᴰᴵ\nCH₂"),
    (0x7175, "MI_CH3", [], "ᴹᴵᴰᴵ\nCH₃"),
    (0x7176, "MI_CH4", [], "ᴹᴵᴰᴵ\nCH₄"),
    (0x7177, "MI_CH5", [], "ᴹᴵᴰᴵ\nCH₅"),
    (0x7178, "MI_CH6", [], "ᴹᴵᴰᴵ\nCH₆"),
    (0x7179, "MI_CH7", [], "ᴹᴵᴰᴵ\nCH₇"),
    (0x717A, "MI_CH8", [], "ᴹᴵᴰᴵ\nCH₈"),
    (0x717B, "MI_CH9", [], "ᴹᴵᴰᴵ\nCH₉"),
    (0x717C, "MI_CH10", [], "ᴹᴵᴰᴵ\nCH₁₀"),
    (0x717D, "MI_CH11", [], "ᴹᴵᴰᴵ\nCH₁₁"),
    (0x717E, "MI_CH12", [], "ᴹᴵᴰᴵ\nCH₁₂"),
    (0x717F, "MI_CH13", [], "ᴹᴵᴰᴵ\nCH₁₃"),
    (0x7180, "MI_CH14", [], "ᴹᴵᴰᴵ\nCH₁₄"),
    (0x7181, "MI_CH15", [], "ᴹᴵᴰᴵ\nCH₁₅"),
    (0x7182, "MI_CH16", [], "ᴹᴵᴰᴵ\nCH₁₆"),
    (0x7183, "MI_CHD", [], "ᴹᴵᴰᴵ\nCHᴰᴺ"),
    (0x7184, "MI_CHU", [], "ᴹᴵᴰᴵ\nCHᵁᴾ"),
    (0x7185, "MI_ALLOFF", [], "ᴹᴵᴰᴵ\nNotesᵒᶠᶠ"),
    (0x7186, "MI_SUS", [], "ᴹᴵᴰᴵ\nSust"),
    (0x7187, "MI_PORT", [], "ᴹᴵᴰᴵ\nPort"),
    (0x7188, "MI_SOST", [], "ᴹᴵᴰᴵ\nSost"),
    (0x7189, "MI_SOFT", [], "ᴹᴵᴰᴵ\nSPedal"),
    (0x718A, "MI_LEG", [], "ᴹᴵᴰᴵ\nLegat"),
    (0x718B, "MI_MOD", [], "ᴹᴵᴰᴵ\nModul"),
    (0x718C, "MI_MODSD", [], "ᴹᴵᴰᴵ\nModulᴰᴺ"),
    (0x718D, "MI_MODSU", [], "ᴹᴵᴰᴵ\nModulᵁᴾ"),
    (0x718E, "MI_BENDD", [], "ᴹᴵᴰᴵ\nBendᴰᴺ"),
    (0x718F, "MI_BENDU", [], "ᴹᴵᴰᴵ\nBendᵁᴾ"),
    (0x7480, "AU_ON", [], "Audio\nON"),
    (0x7481, "AU_OFF", [], "Audio\nOFF"),
    (0x7482, "AU_TOG", [], "Audio\nToggle"),
    (0x748A, "CLICKY_TOGGLE", ["CK_TOGG"], "Clicky\nToggle"),
    (0x748D, "CLICKY_UP", ["CK_UP"], "Clicky\nUp"),
    (0x748E, "CLICKY_DOWN", ["CK_DOWN"], "Clicky\nDown"),
    (0x748F, "CLICKY_RESET", ["CK_RST"], "Clicky\nReset"),
    (0x7490, "MU_ON", [], "Music\nOn"),
    (0x7491, "MU_OFF", [], "Music\nOff"),
    (0x7492, "MU_TOG", [], "Music\nToggle"),
    (0x7493, "MU_MOD", [], "Music\nCycle"),
    (0x7800, "BL_ON", [], "BL On"),
    (0x7801, "BL_OFF", [], "BL Off"),
    (0x7802, "BL_TOGG", [], "BL\nToggle"),
    (0x7803, "BL_DEC", [], "BL - "),
    (0x7804, "BL_INC", [], "BL +"),
    (0x7805, "BL_STEP", [], "BL\nCycle"),
    (0x7806, "BL_BRTG", [], "BL\nBreath"),
    (0x7820, "RGB_TOG", [], "RGB\nToggle"),
    (0x7821, "RGB_MOD", [], "RGB\nMode +"),
    (0x7822, "RGB_RMOD", [], "RGB\nMode -"),
    (0x7823, "RGB_HUI", [], "Hue +"),
    (0x7824, "RGB_HUD", [], "Hue -"),
    (0x7825, "RGB_SAI", [], "Sat +"),
    (0x7826, "RGB_SAD", [], "Sat -"),
    (0x7827, "RGB_VAI", [], "Bright +"),
    (0x7828, "RGB_VAD", [], "Bright -"),
    (0x7829, "RGB_SPI", [], "Effect +"),
    (0x782A, "RGB_SPD", [], "Effect -"),
    (0x782B, "RGB_M_P", [], "RGB\nMode P"),
    (0x782C, "RGB_M_B", [], "RGB\nMode B"),
    (0x782D, "RGB_M_R", [], "RGB\nMode R"),
    (0x782E, "RGB_M_SW", [], "RGB\nMode SW"),
    (0x782F, "RGB_M_SN", [], "RGB\nMode SN"),
    (0x7830, "RGB_M_K", [], "RGB\nMode K"),
    (0x7831, "RGB_M_X", [], "RGB\nMode X"),
    (0x7832, "RGB_M_G", [], "RGB\nMode G"),
    (0x7833, "RGB_M_T", [], "RGB\nMode T"),
    (0x7840, "RM_ON", [], "RGBM\nOn"),
    (0x7841, "RM_OFF", [], "RGBM\nOff"),
    (0x7842, "RM_TOGG", [], "RGBM\nTogg"),
    (0x7843, "RM_NEXT", [], "RGBM\nNext"),
    (0x7844, "RM_PREV", [], "RGBM\nPrev"),
    (0x7845, "RM_HUEU", [], "RGBM\nHue +"),
    (0x7846, "RM_HUED", [], "RGBM\nHue -"),
    (0x7847, "RM_SATU", [], "RGBM\nSat +"),
    (0x7848, "RM_SATD", [], "RGBM\nSat -"),
    (0x7849, "RM_VALU", [], "RGBM\nBright +"),
    (0x784A, "RM_VALD", [], "RGBM\nBright -"),
    (0x784B, "RM_SPDU", [], "RGBM\nSpeed +"),
    (0x784C, "RM_SPDD", [], "RGBM\nSpeed -"),
    (0x7C00, "QK_BOOT", ["RESET"], "Boot-\nloader"),
    (0x7C01, "QK_REBOOT", [], "Reboot"),
    (0x7C03, "QK_CLEAR_EEPROM", ["EE_CLR"], "Clear\nEEPROM"),
    (0x7C10, "ASDN", [], "Auto-\nshift\nDown"),
    (0x7C11, "ASUP", [], "Auto-\nshift\nUp"),
    (0x7C12, "ASRP", [], "Auto-\nshift\nReport"),
    (0x7C13, "ASON", [], "Auto-\nshift\nOn"),
    (0x7C14, "ASOFF", [], "Auto-\nshift\nOff"),
    (0x7C15, "ASTG", [], "Auto-\nshift\nToggle"),
    (0x7C16, "GESC", [], "~\nEsc"),
    (0x7C18, "LCPO", [], "LC\n("),
    (0x7C19, "RCPC", [], "RC\n)"),
    (0x7C1A, "LSPO", [], "LS\n("),
    (0x7C1B, "RSPC", [], "RS\n)"),
    (0x7C1C, "LAPO", [], "LA\n("),
    (0x7C1D, "RAPC", [], "RA\n)"),
    (0x7C1E, "SFTENT", [], "RS\nEnter"),
    (0x7C40, "HPT_ON", [], "Haptic\nOn"),
    (0x7C41, "HPT_OFF", [], "Haptic\nOff"),
    (0x7C42, "HPT_TOG", [], "Haptic\nToggle"),
    (0x7C43, "HPT_RST", [], "Haptic\nReset"),
    (0x7C44, "HPT_FBK", [], "Haptic\nFeed\nback"),
    (0x7C45, "HPT_BUZ", [], "Haptic\nBuzz"),
    (0x7C46, "HPT_MODI", [], "Haptic\nNext"),
    (0x7C47, "HPT_MODD", [], "Haptic\nPrev"),
    (0x7C48, "HPT_CONT", [], "Haptic\nCont."),
    (0x7C49, "HPT_CONI", [], "Haptic\n+"),
    (0x7C4A, "HPT_COND", [], "Haptic\n-"),
    (0x7C4B, "HPT_DWLI", [], "Haptic\nDwell+"),
    (0x7C4C, "HPT_DWLD", [], "Haptic\nDwell-"),
    (0x7C50, "CMB_ON", [], "Combo\nOn"),
    (0x7C51, "CMB_OFF", [], "Combo\nOff"),
    (0x7C52, "CMB_TOG", [], "Combo\nToggle"),
    (0x7C53, "DYN_REC_START1", ["DM_REC1"], "DM1\nRec"),
    (0x7C54, "DYN_REC_START2", ["DM_REC2"], "DM2\nRec"),
    (0x7C55, "DYN_REC_STOP", ["DM_RSTP"], "DM Rec\nStop"),
    (0x7C56, "DYN_MACRO_PLAY1", ["DM_PLY1"], "DM1\nPlay"),
    (0x7C57, "DYN_MACRO_PLAY2", ["DM_PLY2"], "DM2\nPlay"),
    (0x7C73, "QK_CAPS_WORD_TOGGLE", ["CW_TOGG"], "Caps\nWord"),
    (0x7C77, "FN_MO13", [], None),
    (0x7C78, "FN_MO23", [], None),
    (0x7C79, "QK_REPEAT_KEY", ["QK_REP"], "Repeat"),
    (0x7C7A, "QK_ALT_REPEAT_KEY", ["QK_AREP"], "Alt\nRepeat"),
    (0x7C7B, "QK_LAYER_LOCK", [], None),
    (0x7E00, "QK_KB", [], None),
]
