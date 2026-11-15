"""Minimal TOML writer (the standard library's tomllib can only read).

Supports exactly what keymap.toml needs:
  - nested dicts -> [tables] / [dotted.tables]
  - str, int, bool scalars
  - list of lists -> one inner list per line
  - list of dicts -> [[array.of.tables]]
Comments can be attached to tables via ``comments={"path.to.table": "text"}``.
"""
from __future__ import annotations

import json
import re

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def _key(k: str) -> str:
    return k if _BARE_KEY.match(k) else json.dumps(k)


def _scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)  # JSON string escapes are valid TOML basic strings
    raise TypeError(f"unsupported TOML value: {v!r}")


def _grid(rows: list[list]) -> str:
    return "[\n" + "".join("  [" + ", ".join(_scalar(c) for c in row) + "],\n" for row in rows) + "]"


def _value(v) -> str:
    if isinstance(v, list):
        if v and all(isinstance(x, list) for x in v):
            return _grid(v)
        return "[" + ", ".join(_scalar(x) for x in v) + "]"
    return _scalar(v)


def dumps(doc: dict, comments: dict[str, str] | None = None) -> str:
    comments = comments or {}
    out: list[str] = []

    def is_aot(v) -> bool:
        return isinstance(v, list) and bool(v) and all(isinstance(x, dict) for x in v)

    def header(path: list[str], brackets: str, comment: bool = True):
        if out:
            out.append("")
        name = ".".join(path)
        if comment and name in comments:
            out.extend("# " + ln for ln in comments[name].splitlines())
        half = len(brackets) // 2
        out.append(brackets[:half] + ".".join(_key(p) for p in path) + brackets[half:])

    def table(path: list[str], d: dict, brackets: str | None = "[]", comment: bool = True):
        scalars = {k: v for k, v in d.items() if not isinstance(v, dict) and not is_aot(v)}
        subtables = {k: v for k, v in d.items() if isinstance(v, dict) or is_aot(v)}
        if path and brackets and (scalars or not subtables or brackets == "[[]]"):
            header(path, brackets, comment)
        for k, v in scalars.items():
            out.append(f"{_key(k)} = {_value(v)}")
        for k, v in subtables.items():
            if isinstance(v, dict):
                table(path + [k], v)
            else:
                for i, item in enumerate(v):
                    table(path + [k], item, "[[]]", comment=i == 0)

    table([], doc)
    return "\n".join(out) + "\n"
