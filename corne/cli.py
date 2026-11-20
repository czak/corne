"""kb.py — read and change the keyboard's keymap. The keyboard is the source of truth: every command reads it live.

    kb render [--from FILE]       keyboard (or a saved FILE) -> docs/*.svg, docs/index.html, docs/tutor/keymap.js, README.md
    kb dump   [FILE]              keyboard -> TOML (stdout, or FILE), e.g. to edit and push back
    kb diff   FILE                keyboard vs FILE
    kb check  FILE                validate FILE (no keyboard needed)
    kb push   FILE                FILE -> keyboard (e.g. a backup)
    kb set    LAYER POSITION KEYCODE    one key, e.g. kb set 0 "right top 1" F14
    kb td     N [TAP [HOLD [DOUBLE [TAP_HOLD]]]] [--term MS] | N --clear
    kb combo  N KEY KEY.. --output KEYCODE | N --clear
    kb setting NAME VALUE

Every change backs up the keyboard to backups/ first, then verifies by reading it back.
"""
from __future__ import annotations

import argparse
import copy
import re
import sys
import time
from pathlib import Path

from . import layout, settings
from .device import DeviceError, Keyboard
from .keycodes import Codec
from .keyboard import HALVES, POSITIONS
from .layout import TD_FIELDS, Keymap, KeymapError, trim_combos, trim_tap_dances

ROOT = Path(__file__).resolve().parents[1]
BACKUPS = ROOT / "backups"
DOCS = ROOT / "docs"
TUTOR = DOCS / "tutor"
README = ROOT / "README.md"

LINE_NAMES = ["top", "home", "bottom", "thumb"]


def _describe() -> dict[tuple[int, int], str]:
    out = {}
    for half, grid in HALVES.items():
        for i, line in enumerate(grid):
            for k, p in enumerate([p for p in line if p], 1):
                out[p] = f"{half} {LINE_NAMES[i]} #{k}"
    return out


DESC = _describe()


# ---------------------------------------------------------------- keyboard state
def read_device(kb: Keyboard) -> tuple[Keymap, list[settings.Field], dict[int, int], list, list]:
    raw = kb.read_keymap()
    fields = settings.fields_for(kb.settings_supported())
    w = settings.widths(fields)
    raw_settings = {q: kb.setting_get(q, n) for q, n in sorted(w.items())}
    tds = [kb.tap_dance_get(i) for i in range(kb.tap_dance_count())]
    combos = [kb.combo_get(i) for i in range(kb.combo_count())]
    km = Keymap(raw, settings.decode(fields, raw_settings), trim_tap_dances(tds),
                trim_combos(combos))
    return km, fields, raw_settings, tds, combos


def snapshot(km: Keymap) -> dict:
    return {"keys": [[m[r][c] for r, c in POSITIONS] for m in km.raw()], "settings": km.settings,
            "tap_dance": [list(t) for t in trim_tap_dances(km.tap_dance)],
            "combo": [list(c) for c in trim_combos(km.combo)]}


def tap_dance_changes(old: Keymap, new: Keymap):
    """[(index, field, old value, new value)] for differing tap dance fields (missing entries count as empty)."""
    a, b = trim_tap_dances(old.tap_dance), trim_tap_dances(new.tap_dance)
    out = []
    for i in range(max(len(a), len(b))):
        ea = a[i] if i < len(a) else (0, 0, 0, 0, b[i][4])
        eb = b[i] if i < len(b) else (0, 0, 0, 0, a[i][4])
        out += [(i, f, x, y) for f, x, y in zip(TD_FIELDS, ea, eb) if x != y]
    return out


def combo_changes(old: Keymap, new: Keymap):
    """[(index, old combo, new combo)] for differing combos (missing entries count as empty)."""
    a, b = trim_combos(old.combo), trim_combos(new.combo)
    empty = (0,) * 5
    return [(i, x, y) for i in range(max(len(a), len(b)))
            if (x := a[i] if i < len(a) else empty) != (y := b[i] if i < len(b) else empty)]


def key_changes(old: Keymap, new: Keymap):
    """[(layer index, (row, col), old kc, new kc)] for differing keys."""
    out = []
    for li, (mo, mn) in enumerate(zip(old.raw(), new.raw())):
        for r, c in POSITIONS:
            if mo[r][c] != mn[r][c]:
                out.append((li, (r, c), mo[r][c], mn[r][c]))
    return out


def setting_changes(old: Keymap, new: Keymap):
    return [(k, old.settings.get(k), v) for k, v in new.settings.items() if old.settings.get(k) != v]


def print_diff(device: Keymap, target: Keymap, codec: Codec, left="keyboard", right="keymap") -> int:
    kc = key_changes(device, target)
    sc = setting_changes(device, target)
    tc = tap_dance_changes(device, target)
    cc = combo_changes(device, target)
    for li, pos, a, b in kc:
        print(f"  {f'layer {li}':<8} {DESC[pos]:<16} {codec.decode(a):>18}  ->  {codec.decode(b)}")
    for k, a, b in sc:
        print(f"  setting  {k:<28} {a!s:>8}  ->  {b}")
    for i, f, a, b in tc:
        fmt = str if f == "custom_tapping_term" else codec.decode
        print(f"  {f'TD({i})':<8} {f:<19} {fmt(a):>15}  ->  {fmt(b)}")
    def combo_str(c):
        return "NO" if not any(c) else "+".join(codec.decode(k) for k in c[:4] if k) + " = " + codec.decode(c[4])
    for i, a, b in cc:
        print(f"  {f'combo {i}':<8} {combo_str(a):>36}  ->  {combo_str(b)}")
    if not kc and not sc and not tc and not cc:
        print(f"  {left} and {right} are identical")
    return len(kc) + len(sc) + len(tc) + len(cc)


def load_keymap(path: Path) -> Keymap:
    try:
        return layout.load(path)
    except (KeymapError, ValueError, OSError) as e:
        sys.exit(f"{path.name}: invalid\n{e}")


def parse_position(s: str) -> tuple[int, int]:
    """'right top 1' / 'right top #1' -> matrix position."""
    want = re.sub(r"\s+", " ", s.replace("#", "")).strip().lower()
    for pos, desc in DESC.items():
        if desc.replace("#", "") == want:
            return pos
    sys.exit(f"unknown position {s!r} (expected e.g. 'left home 2': half, top|home|bottom|thumb, "
             f"number counted left to right as seen from above)")


def write_backup(km: Keymap) -> Path:
    BACKUPS.mkdir(exist_ok=True)
    stamp, i = time.strftime("%Y%m%d-%H%M%S"), 0
    while (backup := BACKUPS / f"{stamp}{f'-{i}' if i else ''}.toml").exists():
        i += 1
    layout.save(km, backup)
    return backup


def apply(kb: Keyboard, state, target: Keymap):
    """Write target to the keyboard (only what differs from ``state`` = read_device()), then verify."""
    device, fields, raw_settings, raw_tds, raw_combos = state
    if len(target.layers) != len(device.layers):
        sys.exit(f"keyboard has {len(device.layers)} layers, target has {len(target.layers)}")
    if len(target.tap_dance) > len(raw_tds):
        sys.exit(f"keyboard has {len(raw_tds)} tap dances, target has {len(target.tap_dance)}")
    if len(target.combo) > len(raw_combos):
        sys.exit(f"keyboard has {len(raw_combos)} combos, target has {len(target.combo)}")
    codec = Codec()
    n = print_diff(device, target, codec, "keyboard", "target")
    if n == 0:
        return
    backup = write_backup(device)
    for li, (r, c), _, new in key_changes(device, target):
        kb.set_keycode(li, r, c, new)
    new_raw = settings.encode(fields, target.settings, raw_settings)
    w = settings.widths(fields)
    for q, v in new_raw.items():
        if raw_settings[q] != v:
            kb.setting_set(q, w[q], v)
    for i, old in enumerate(raw_tds):
        new = target.tap_dance[i] if i < len(target.tap_dance) else (0, 0, 0, 0, old[4])
        if tuple(old) != tuple(new):
            kb.tap_dance_set(i, new)
    for i, old in enumerate(raw_combos):
        new = target.combo[i] if i < len(target.combo) else (0,) * 5
        if tuple(old) != tuple(new):
            kb.combo_set(i, new)
    after, *_ = read_device(kb)
    expected = Keymap(target.layers, {**device.settings, **target.settings}, target.tap_dance, target.combo)
    if snapshot(after) != snapshot(expected):
        print("VERIFY FAILED — keyboard now differs from target:")
        print_diff(after, expected, codec, "keyboard", "target")
        sys.exit(f"previous state saved in {backup.relative_to(ROOT)}")
    print(f"wrote {n} change(s), verified. backup: {backup.relative_to(ROOT)}")


def edit(change):
    """Read the keyboard, let ``change(target, codec, fields)`` modify a copy, write the difference."""
    with Keyboard() as kb:
        state = read_device(kb)
        target = copy.deepcopy(state[0])
        try:
            change(target, Codec(), state[1])
        except ValueError as e:
            sys.exit(str(e))
        apply(kb, state, target)


# ---------------------------------------------------------------- commands
def cmd_check(args):
    km = load_keymap(args.file)
    print(f"{args.file.name}: OK — {len(km.layers)} layers, {len(km.settings)} settings, "
          f"{len(km.tap_dance)} tap dances, {len(km.combo)} combos")


def cmd_dump(args):
    with Keyboard() as kb:
        device, *_ = read_device(kb)
    if args.file:
        layout.save(device, args.file)
        print(f"wrote {args.file}")
    else:
        sys.stdout.write(layout.dump(device))


def cmd_diff(args):
    target = load_keymap(args.file)
    with Keyboard() as kb:
        device, *_ = read_device(kb)
    print_diff(device, target, Codec(), "keyboard", args.file.name)


def cmd_push(args):
    target = load_keymap(args.file)
    with Keyboard() as kb:
        apply(kb, read_device(kb), target)


def cmd_set(args):
    def change(km, codec, _):
        if not 0 <= args.layer < len(km.layers):
            raise ValueError(f"no layer {args.layer} (layers: 0-{len(km.layers) - 1})")
        r, c = parse_position(args.position)
        km.layers[args.layer][r][c] = codec.encode(args.keycode)
    edit(change)


def cmd_td(args):
    def change(km, codec, _):
        tds = list(km.tap_dance)
        while len(tds) <= args.n:
            tds.append((0, 0, 0, 0, 200))
        if args.clear:
            tds[args.n] = (0, 0, 0, 0, tds[args.n][4])
        else:
            if not args.actions:
                raise ValueError("give at least TAP (or --clear)")
            if len(args.actions) > 4:
                raise ValueError("at most 4 actions: TAP HOLD DOUBLE TAP_HOLD")
            acts = [codec.encode(a) for a in args.actions] + [0] * (4 - len(args.actions))
            tds[args.n] = (*acts, args.term if args.term is not None else tds[args.n][4])
        km.tap_dance = trim_tap_dances(tds)
    edit(change)


def cmd_combo(args):
    def change(km, codec, _):
        combos = list(km.combo)
        while len(combos) <= args.n:
            combos.append((0,) * 5)
        if args.clear:
            combos[args.n] = (0,) * 5
        else:
            if not (2 <= len(args.keys) <= 4) or not args.output:
                raise ValueError("give 2-4 KEYs and --output (or --clear)")
            keys = [codec.encode(k) for k in args.keys]
            combos[args.n] = (*keys, *[0] * (4 - len(keys)), codec.encode(args.output))
        km.combo = trim_combos(combos)
    edit(change)


def cmd_setting(args):
    def change(km, _, fields):
        f = {f.name: f for f in fields}.get(args.name)
        if f is None:
            raise ValueError(f"unknown setting {args.name!r} (see `kb dump`)")
        v = args.value.lower()
        if f.boolean:
            if v not in ("true", "false", "1", "0", "on", "off"):
                raise ValueError(f"{f.name} is a boolean (true/false)")
            km.settings[f.name] = v in ("true", "1", "on")
        else:
            km.settings[f.name] = int(v, 0)
    edit(change)


def cmd_render(args):
    from .render import render_html, render_svgs, update_readme
    from .typing import render_data
    if args.source:
        km = load_keymap(args.source)
    else:
        with Keyboard() as kb:
            km, *_ = read_device(kb)
    DOCS.mkdir(exist_ok=True)
    svgs = render_svgs(km)
    for old in DOCS.glob("*.svg"):
        if old.name not in svgs:
            old.unlink()
    for name, text in svgs.items():
        (DOCS / name).write_text(text)
    (DOCS / "index.html").write_text(render_html(km))
    (TUTOR / "keymap.js").write_text(render_data(km))
    README.write_text(update_readme(README.read_text(), km))
    print(f"rendered {args.source or 'the keyboard'}: "
          f"{len(svgs)} SVGs + index.html in docs/, docs/tutor/keymap.js, updated README.md")


def main(argv=None):
    p = argparse.ArgumentParser(prog="kb", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("render", help="keyboard -> docs/*.svg + index.html + docs/tutor/keymap.js + README")
    s.add_argument("--from", dest="source", type=Path, help="render a saved TOML (e.g. a backup) instead")
    s.set_defaults(fn=cmd_render)
    s = sub.add_parser("dump", help="keyboard -> TOML")
    s.add_argument("file", nargs="?", type=Path)
    s.set_defaults(fn=cmd_dump)
    for name, fn, help_ in (("diff", cmd_diff, "keyboard vs FILE"), ("check", cmd_check, "validate FILE"),
                            ("push", cmd_push, "FILE -> keyboard")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("file", type=Path)
        s.set_defaults(fn=fn)
    s = sub.add_parser("set", help="set one key")
    s.add_argument("layer", type=int)
    s.add_argument("position", help="e.g. 'right top 1': half, top|home|bottom|thumb, n-th key from the left")
    s.add_argument("keycode")
    s.set_defaults(fn=cmd_set)
    s = sub.add_parser("td", help="set or clear tap dance TD(N)")
    s.add_argument("n", type=int)
    s.add_argument("actions", nargs="*", metavar="ACTION", help="TAP [HOLD [DOUBLE [TAP_HOLD]]]")
    s.add_argument("--term", type=int, help="custom tapping term, ms")
    s.add_argument("--clear", action="store_true")
    s.set_defaults(fn=cmd_td)
    s = sub.add_parser("combo", help="set or clear combo N")
    s.add_argument("n", type=int)
    s.add_argument("keys", nargs="*", metavar="KEY")
    s.add_argument("-o", "--output")
    s.add_argument("--clear", action="store_true")
    s.set_defaults(fn=cmd_combo)
    s = sub.add_parser("setting", help="set a QMK setting")
    s.add_argument("name")
    s.add_argument("value")
    s.set_defaults(fn=cmd_setting)
    args = p.parse_args(argv)
    try:
        args.fn(args)
    except DeviceError as e:
        sys.exit(f"keyboard: {e}")


if __name__ == "__main__":
    main()
