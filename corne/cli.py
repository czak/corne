"""kb.py — sync keymap.toml with the keyboard.

    kb pull   [--force] [--names A,B,..]  keyboard -> keymap.toml
    kb diff                    show keyboard vs keymap.toml
    kb check                   validate keymap.toml (no keyboard needed)
    kb push   [FILE] [--force] keymap.toml (or FILE, e.g. a backup) -> keyboard
    kb render [FILE]           keymap.toml -> docs/*.svg, docs/keymap.html, tutor/keymap.js, README.md
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import layout, settings
from .device import DeviceError, Keyboard
from .keycodes import Codec
from .keyboard import HALVES, POSITIONS
from .layout import Keymap, KeymapError

ROOT = Path(__file__).resolve().parents[1]
KEYMAP = ROOT / "keymap.toml"
BACKUPS = ROOT / "backups"
STATE = ROOT / ".kb-state.json"
DOCS = ROOT / "docs"
TUTOR = ROOT / "tutor"
README = ROOT / "README.md"   # last state kb wrote to / read from the keyboard

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
def read_device(kb: Keyboard, names: list[str]) -> tuple[Keymap, list[settings.Field], dict[int, int]]:
    raw = kb.read_keymap()
    if len(names) != len(raw):
        names = [f"L{i}" for i in range(len(raw))]
    fields = settings.fields_for(kb.settings_supported())
    w = settings.widths(fields)
    raw_settings = {q: kb.setting_get(q, n) for q, n in sorted(w.items())}
    km = Keymap(dict(zip(names, raw)), settings.decode(fields, raw_settings))
    return km, fields, raw_settings


def snapshot(km: Keymap) -> dict:
    return {"keys": [[m[r][c] for r, c in POSITIONS] for m in km.raw()], "settings": km.settings}


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
    names = target.names
    for li, pos, a, b in kc:
        print(f"  {names[li]:<8} {DESC[pos]:<16} {codec.decode(a):>18}  ->  {codec.decode(b)}")
    for k, a, b in sc:
        print(f"  setting  {k:<28} {a!s:>8}  ->  {b}")
    if not kc and not sc:
        print(f"  {left} and {right} are identical")
    return len(kc) + len(sc)


def load_keymap(path: Path) -> Keymap:
    try:
        return layout.load(path)
    except (KeymapError, ValueError) as e:
        sys.exit(f"{path.name}: invalid\n{e}")


# ---------------------------------------------------------------- commands
def cmd_check(args):
    km = load_keymap(args.file)
    print(f"{args.file.name}: OK — {len(km.layers)} layers ({', '.join(km.names)}), {len(km.settings)} settings")


def cmd_pull(args):
    names = args.names.split(",") if args.names else (layout.load(KEYMAP).names if KEYMAP.exists() else [])
    with Keyboard() as kb:
        device, _, _ = read_device(kb, names)
    codec = Codec(device.names)
    if KEYMAP.exists() and not args.force:
        current = load_keymap(KEYMAP)
        if snapshot(current) != snapshot(device):
            print("keymap.toml differs from the keyboard:")
            print_diff(device, current, codec)
            sys.exit("refusing to overwrite keymap.toml (use --force)")
    layout.save(device, KEYMAP)
    STATE.write_text(json.dumps(snapshot(device)))
    print(f"wrote {KEYMAP.name}: {len(device.layers)} layers, {len(device.settings)} settings")


def cmd_diff(args):
    target = load_keymap(args.file)
    with Keyboard() as kb:
        device, _, _ = read_device(kb, target.names)
    print_diff(device, target, Codec(target.names))


def cmd_push(args):
    target = load_keymap(args.file)
    with Keyboard() as kb:
        device, fields, raw_settings = read_device(kb, target.names)
        if len(target.layers) != len(device.layers):
            sys.exit(f"keyboard has {len(device.layers)} layers, {args.file.name} has {len(target.layers)}")
        codec = Codec(target.names)

        # Drift: keyboard changed since kb last saw it (e.g. edited in Vial)?
        if STATE.exists() and not args.force:
            last = json.loads(STATE.read_text())
            now = snapshot(device)
            if now != last and now != snapshot(target):
                sys.exit("keyboard was changed outside kb since the last pull/push "
                         "(run `kb diff` / `kb pull`, or push with --force)")

        print(f"{args.file.name} -> keyboard ({kb.path}):")
        n = print_diff(device, target, codec)
        if n == 0:
            STATE.write_text(json.dumps(snapshot(device)))
            return

        BACKUPS.mkdir(exist_ok=True)
        stamp, i = time.strftime("%Y%m%d-%H%M%S"), 0
        while (backup := BACKUPS / f"{stamp}{f'-{i}' if i else ''}.toml").exists():
            i += 1
        layout.save(device, backup)

        for li, (r, c), _, new in key_changes(device, target):
            kb.set_keycode(li, r, c, new)
        new_raw = settings.encode(fields, target.settings, raw_settings)
        w = settings.widths(fields)
        for q, v in new_raw.items():
            if raw_settings[q] != v:
                kb.setting_set(q, w[q], v)

        after, _, _ = read_device(kb, target.names)
    expected = Keymap(target.layers, {**device.settings, **target.settings})
    if snapshot(after) != snapshot(expected):
        print("VERIFY FAILED — keyboard now differs from target:")
        print_diff(after, expected, codec, "keyboard", "target")
        sys.exit(f"previous state saved in {backup.relative_to(ROOT)}")
    STATE.write_text(json.dumps(snapshot(after)))
    print(f"pushed {n} change(s), verified. backup: {backup.relative_to(ROOT)}")


def cmd_render(args):
    from .render import render_html, render_svgs, update_readme
    from .typing import render_data
    km = load_keymap(args.file)
    DOCS.mkdir(exist_ok=True)
    svgs = render_svgs(km)
    for old in DOCS.glob("*.svg"):
        if old.name not in svgs:
            old.unlink()
    for name, text in svgs.items():
        (DOCS / name).write_text(text)
    (DOCS / "keymap.html").write_text(render_html(km))
    (TUTOR / "keymap.js").write_text(render_data(km))
    README.write_text(update_readme(README.read_text(), km))
    print(f"wrote {len(svgs)} SVGs + keymap.html in docs/, tutor/keymap.js, updated README.md")


def main(argv=None):
    p = argparse.ArgumentParser(prog="kb", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("pull", help="keyboard -> keymap.toml")
    s.add_argument("--force", action="store_true", help="overwrite keymap.toml even if it has unpushed changes")
    s.add_argument("--names", help="comma-separated layer names (default: keep those in keymap.toml)")
    s.set_defaults(fn=cmd_pull)
    for name, fn, help_ in (("diff", cmd_diff, "keyboard vs keymap"), ("check", cmd_check, "validate keymap"),
                            ("render", cmd_render, "keymap -> docs/*.svg + keymap.html + tutor/keymap.js + README")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("file", nargs="?", type=Path, default=KEYMAP)
        s.set_defaults(fn=fn)
    s = sub.add_parser("push", help="keymap -> keyboard")
    s.add_argument("file", nargs="?", type=Path, default=KEYMAP)
    s.add_argument("--force", action="store_true", help="push even if the keyboard changed outside kb")
    s.set_defaults(fn=cmd_push)
    args = p.parse_args(argv)
    try:
        args.fn(args)
    except DeviceError as e:
        sys.exit(f"keyboard: {e}")


if __name__ == "__main__":
    main()
