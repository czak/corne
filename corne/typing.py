"""Typing tutor page (docs/typing.html): paste a text, then type it with the chord for each character highlighted
on the combined keymap.

For every character the keymap can produce, ``chords`` finds the cheapest way to type it: a key to tap, plus the
keys to hold first (a base-layer key that activates the layer, and a shift key on that layer). Holds prefer the hand
opposite the tapped key, as home-row mods require.
"""
from __future__ import annotations

import html
import json

from .keycodes import QK_LAYER_TAP, QK_MOD_TAP, QK_MODS, Codec, label
from .keyboard import POSITIONS
from .layout import Keymap
from .render import Svg, activators, combined_svg, legend, load_geometry

SHIFT_MODS = (0x02, 0x12)          # MOD_LSFT, MOD_RSFT
SHIFT_KEYS = (0xE1, 0xE5)          # LSHIFT, RSHIFT
WHITESPACE = {0x2C: " ", 0x28: "\n", 0x2B: "\t"}   # SPACE, ENTER, TAB


def _chars(basic: int) -> tuple[str | None, str | None]:
    """(unshifted, shifted) character a basic keycode types on a US layout."""
    if 0x04 <= basic <= 0x1D:
        c = chr(ord("a") + basic - 0x04)
        return c, c.upper()
    if basic in WHITESPACE:
        return WHITESPACE[basic], None
    lab = label(basic)
    if lab:
        parts = lab.split("\n")
        if len(parts) == 2 and all(len(p) == 1 for p in parts):
            return parts[1], parts[0]
    return None, None


def _tap(v: int) -> tuple[int, bool] | None:
    """(basic keycode, shift included) sent when ``v`` is tapped, or None if it types no character."""
    if v <= 0xFF:
        return v, False
    if QK_MODS <= v < QK_MOD_TAP:
        return (v & 0xFF, True) if (v >> 8) & 0x1F in SHIFT_MODS else None
    if QK_MOD_TAP <= v < 0x5000:      # mod-tap and layer-tap: the tap is the basic keycode
        return v & 0xFF, False
    return None


def _is_shift(v: int) -> bool:
    return v in SHIFT_KEYS or (QK_MOD_TAP <= v < QK_LAYER_TAP and (v >> 8) & 0x1F in SHIFT_MODS)


def _left(pos: tuple[int, int]) -> bool:
    return pos[1] < 6


def _pick(cands, tap):
    """Prefer a hold key on the other hand from ``tap``."""
    cands = sorted(cands, key=lambda p: (_left(p) == _left(tap), POSITIONS.index(p)))
    return cands[0] if cands else None


def chords(km: Keymap) -> dict[str, dict]:
    """char -> {"tap": "r,c", "hold": ["r,c", ...], "layer": name | None, "shift": bool}."""
    layers = km.raw()
    acts = activators(km)
    best: dict[str, tuple] = {}
    for li, m in enumerate(layers):
        if li and li not in acts:
            continue                       # not reachable from the base layer
        eff = {p: (layers[0] if m[p[0]][p[1]] == 1 else m)[p[0]][p[1]] for p in POSITIONS}   # TRNS falls through
        shifts = [p for p in POSITIONS if _is_shift(eff[p])]
        for pos in POSITIONS:
            if li and pos in acts[li]:
                continue                   # held to reach this layer
            t = _tap(eff[pos])
            if not t:
                continue
            plain, shifted = _chars(t[0])
            act = _pick(acts.get(li, ()), pos) if li else None
            options = [(shifted, False)] if t[1] else [(plain, False), (shifted, True)]
            for ch, need_shift in options:
                if not ch:
                    continue
                hold = [act] if act else []
                if need_shift:
                    sh = _pick([p for p in shifts if p != pos and p != act], pos)
                    if not sh:
                        continue
                    hold.append(sh)
                cost = (len(hold), li)
                if ch not in best or cost < best[ch][0]:
                    best[ch] = (cost, pos, hold, li, need_shift)
    return {ch: {"tap": f"{pos[0]},{pos[1]}", "hold": [f"{r},{c}" for r, c in hold],
                 "layer": km.names[li] if li else None, "shift": need_shift}
            for ch, (_, pos, hold, li, need_shift) in sorted(best.items())}


def _names(km: Keymap) -> dict[str, str]:
    """"r,c" -> short base-layer name of the key, for the hint line."""
    codec = Codec(km.names)
    out = {}
    for r, c in POSITIONS:
        lg = legend(km.raw()[0][r][c], codec)
        out[f"{r},{c}"] = " ".join(lg.tap) or lg.hold or ""
    return out


def render_typing(km: Keymap) -> str:
    svg = combined_svg(km, Svg(load_geometry()), pos_attrs=True, layer_labels=True)
    svg = svg.split("\n", 1)[1] if svg.startswith("<?xml") else svg
    data = json.dumps({"chords": chords(km), "names": _names(km), "layers": km.names}, separators=(",", ":"), ensure_ascii=False)
    return (PAGE.replace("{{SVG}}", svg.strip())
                .replace("{{DATA}}", data.replace("</", "<\\/"))
                .replace("{{FOCUS_CSS}}", _focus_css(len(km.layers)))
                .replace("{{TITLE}}", html.escape("Corne typing tutor")))



def _focus_css(n: int) -> str:
    """Focus mode, layer i active: show that layer's legends and its hold label, fade keys that do nothing there."""
    return "\n".join(f"#kbd.focus.on-l{i} .lay.l{i}, #kbd.focus.on-l{i} .hold.l{i} {{ display: inline; }}"
                     for i in range(1, n))


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
:root { color-scheme: light dark;
  --pg-bg:#f6f6f4; --pg-fg:#222; --pg-muted:#76766f; --pg-faint:#b4b4ad; --pg-panel:#fff; --pg-line:#e2e2dc;
  --pg-ok:#2f8f4e; --pg-bad:#d2392f; --pg-bad-bg:#fbe3e0; --pg-cur-bg:#fff4c9; --pg-accent:#3b6fd8;
  --hl-tap-cap:#ffd23f; --hl-tap-skirt:#e6a900; --hl-tap-edge:#9c7200;
  --hl-hold-cap:#9cc3ff; --hl-hold-skirt:#5b8fe0; --hl-hold-edge:#2f5fae;
  --hl-bad-cap:#ff9d93; --hl-bad-skirt:#e0574b; --hl-bad-edge:#a12a20; }
@media (prefers-color-scheme: dark) { :root {
  --pg-bg:#17181a; --pg-fg:#e8e8e6; --pg-muted:#9a9a96; --pg-faint:#55575b; --pg-panel:#202226; --pg-line:#303236;
  --pg-ok:#6fcf8b; --pg-bad:#ff7a6e; --pg-bad-bg:#4a2422; --pg-cur-bg:#4a4020; --pg-accent:#7aa2ff;
  --hl-tap-cap:#c79a12; --hl-tap-skirt:#8a6a06; --hl-tap-edge:#3f3002;
  --hl-hold-cap:#3d6bb8; --hl-hold-skirt:#284b85; --hl-hold-edge:#10203d;
  --hl-bad-cap:#b8433a; --hl-bad-skirt:#7d2620; --hl-bad-edge:#3b100d; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--pg-bg); color: var(--pg-fg); font: 15px/1.45 system-ui, sans-serif; }
main { max-width: 1100px; margin: 0 auto; padding: 20px 16px 48px; }
h1 { font-size: 20px; margin: 0 0 12px; }
button { font: inherit; padding: 7px 16px; border-radius: 8px; border: 1px solid var(--pg-line);
  background: var(--pg-panel); color: var(--pg-fg); cursor: pointer; }
button.primary { background: var(--pg-accent); border-color: var(--pg-accent); color: #fff; }
button:focus-visible { outline: 2px solid var(--pg-accent); outline-offset: 2px; }
.mono { font-family: ui-monospace, "JetBrains Mono", Menlo, Consolas, monospace; }
.hidden { display: none !important; }
.muted { color: var(--pg-muted); }

/* setup */
textarea { width: 100%; min-height: 220px; padding: 12px; border-radius: 10px; border: 1px solid var(--pg-line);
  background: var(--pg-panel); color: var(--pg-fg); font: 15px/1.5 ui-monospace, Menlo, Consolas, monospace; resize: vertical; }
.row { display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: center; margin: 12px 0; }
label { display: inline-flex; gap: 6px; align-items: center; }
#warn { color: var(--pg-bad); }

/* practice */
.stats { display: flex; gap: 22px; flex-wrap: wrap; align-items: baseline; }
.stat b { font-size: 22px; font-variant-numeric: tabular-nums; } .stat span { color: var(--pg-muted); margin-left: 4px; }
.bar { height: 4px; background: var(--pg-line); border-radius: 2px; margin: 10px 0 0; overflow: hidden; }
.bar i { display: block; height: 100%; width: 0; background: var(--pg-accent); transition: width .15s; }
.stage { display: flex; justify-content: center; align-items: center; height: 170px; overflow: hidden; margin-top: 8px;
  white-space: pre; user-select: none; }
.strip { display: flex; align-items: center; font-size: 30px; }
.strip .past { flex: 1 1 0; display: flex; justify-content: flex-end; overflow: hidden; color: var(--pg-ok); min-width: 0; }
.strip .next { flex: 1 1 0; display: flex; overflow: hidden; color: var(--pg-muted); min-width: 0; }
.strip .err { color: var(--pg-bad); text-decoration: underline; }
.strip .ws { color: var(--pg-faint); }
.strip .skip { color: var(--pg-faint); text-decoration: line-through; }
.cur { flex: none; min-width: 1.1em; padding: 0 .12em; margin: 0 .2em; font-size: 108px; line-height: 150px; text-align: center;
  background: var(--pg-cur-bg); border-radius: 14px; }
.cur.ws { color: var(--pg-muted); }
.cur.shake { animation: shake .22s; background: var(--pg-bad-bg); }
@keyframes shake { 25% { transform: translateX(-6px); } 75% { transform: translateX(6px); } }
.hint { min-height: 30px; text-align: center; font-size: 15px; }
.chip { display: inline-block; padding: 2px 10px; margin: 0 3px; border-radius: 999px; font-weight: 600; }
.chip.hold { background: var(--hl-hold-cap); color: #0d1f3f; }
.chip.tap { background: var(--hl-tap-cap); color: #3a2a00; }
@media (prefers-color-scheme: dark) { .chip.hold, .chip.tap { color: #fff; } }
.kbd { margin-top: 10px; }
.kbd svg { width: 100%; height: auto; display: block; }
.toolbar { display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap; margin-top: 8px; }

/* highlights on the embedded keymap (id selector outranks the per-layer key colors) */
#kbd .key.hl-hold { --k-cap: var(--hl-hold-cap); --k-skirt: var(--hl-hold-skirt); --k-edge: var(--hl-hold-edge); --k-dash: none; }
#kbd .key.hl-tap { --k-cap: var(--hl-tap-cap); --k-skirt: var(--hl-tap-skirt); --k-edge: var(--hl-tap-edge); --k-dash: none; }
#kbd .key.hl-bad { --k-cap: var(--hl-bad-cap); --k-skirt: var(--hl-bad-skirt); --k-edge: var(--hl-bad-edge); }
#kbd .key.hl-tap .skirt, #kbd .key.hl-hold .skirt { stroke-width: 2; }
#kbd .key.hl-tap { animation: pulse 1s ease-in-out infinite; transform-box: fill-box; }
@keyframes pulse { 50% { opacity: .72; } }
/* focus mode: only the labels of the layer the current character needs */
#kbd .lay { display: none; fill: var(--fg); font-weight: 600; }
#kbd.focus .sub { display: none; }
#kbd.focus:not(.on-l0) .tap, #kbd.focus:not(.on-l0) .hold { display: none; }
{{FOCUS_CSS}}
#kbd.focus .key.off:not(.hl-tap):not(.hl-hold):not(.hl-bad) { opacity: .3; }

/* results */
.result { text-align: center; padding: 30px 0 10px; }
.result .big { font-size: 46px; font-weight: 700; font-variant-numeric: tabular-nums; }
.missed span { display: inline-block; margin: 3px; padding: 2px 8px; border-radius: 6px; background: var(--pg-bad-bg); }
@media (max-width: 640px) { .cur { font-size: 72px; line-height: 104px; } .stage { height: 120px; } .strip { font-size: 20px; } }
</style>
</head>
<body>
<main>
<h1>Corne typing tutor</h1>

<section id="setup">
  <textarea id="src" spellcheck="false" placeholder="Paste some text here…"></textarea>
  <div class="row">
    <label><input type="checkbox" id="opt-newlines" checked> Line breaks as Enter</label>
    <label><input type="checkbox" id="opt-typo" checked> Plain ASCII punctuation (“ ” – … → " " - ...)</label>
    <span id="warn"></span>
  </div>
  <div class="row"><button class="primary" id="start">Start typing</button>
    <span class="muted">Esc stops. Mistakes don't advance: type the right key to move on.</span></div>
</section>

<section id="play" class="hidden">
  <div class="stats">
    <div class="stat"><b id="s-wpm">0</b><span>wpm</span></div>
    <div class="stat"><b id="s-acc">100</b><span>% accuracy</span></div>
    <div class="stat"><b id="s-err">0</b><span>mistakes</span></div>
    <div class="stat"><b id="s-pos">0</b><span id="s-len">/ 0</span></div>
  </div>
  <div class="bar"><i id="bar"></i></div>
  <div class="stage mono"><div class="strip" id="strip"></div></div>
  <div class="hint" id="hint"></div>
</section>

<section id="done" class="hidden">
  <div class="result">
    <div class="big" id="r-wpm"></div>
    <div class="muted" id="r-line"></div>
    <p class="missed" id="r-missed"></p>
    <div class="row" style="justify-content:center">
      <button class="primary" id="again">Again</button><button id="new">New text</button></div>
  </div>
</section>

<div class="kbd" id="kbdwrap">
{{SVG}}
</div>
<div class="toolbar"><button id="toggle-focus">Show all labels</button><button id="toggle-kbd">Hide keyboard</button></div>
</main>

<script>
const DATA = {{DATA}};
const CH = DATA.chords, NAMES = DATA.names;
const $ = id => document.getElementById(id);
const kbd = document.querySelector("#kbdwrap svg");
kbd.id = "kbd";
const keyEls = {};
kbd.querySelectorAll(".key[data-pos]").forEach(el => keyEls[el.dataset.pos] = el);

const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
};

const TYPO = [[/[‘’‚′]/g, "'"], [/[“”„″]/g, '"'], [/[–—−]/g, "-"],
  [/…/g, "..."], [/[   ]/g, " "], [/•/g, "*"]];

function prepare(raw) {
  let t = raw.replace(/\r\n?/g, "\n");
  if ($("opt-typo").checked) for (const [re, s] of TYPO) t = t.replace(re, s);
  t = t.split("\n").map(l => l.replace(/[ \t]+$/, "")).join("\n").replace(/\n{3,}/g, "\n\n").trim();
  if (!$("opt-newlines").checked) t = t.replace(/\s*\n\s*/g, " ");
  return t;
}

function shown(c) { return c === " " ? "␣" : c === "\n" ? "↵" : c === "\t" ? "⇥" : c; }
function isWs(c) { return c === " " || c === "\n" || c === "\t"; }

// ---------------------------------------------------------------- highlighting
function clearKeys(cls) { kbd.querySelectorAll("." + cls).forEach(el => el.classList.remove(cls)); }
let focusOn = store.get("corne-typing-focus") !== "0";
function setLayer(li) {   // li: active layer index, or null for the full combined view
  kbd.classList.forEach(c => c.startsWith("on-l") && kbd.classList.remove(c));
  kbd.classList.toggle("focus", focusOn && li !== null);
  clearKeys("off");
  if (li === null) return;
  kbd.classList.add("on-l" + li);
  if (li) for (const el of Object.values(keyEls)) if (!el.querySelector(".lay.l" + li)) el.classList.add("off");
}
function highlight(ch) {
  clearKeys("hl-tap"); clearKeys("hl-hold");
  const c = CH[ch];
  setLayer(c ? (c.layer ? DATA.layers.indexOf(c.layer) : 0) : null);
  if (!c) return;
  for (const p of c.hold) keyEls[p]?.classList.add("hl-hold");
  keyEls[c.tap]?.classList.add("hl-tap");
}
let badTimer;
function flashBad(ch) {
  clearTimeout(badTimer); clearKeys("hl-bad");
  const c = CH[ch];
  if (c && !keyEls[c.tap].classList.contains("hl-tap")) keyEls[c.tap].classList.add("hl-bad");
  badTimer = setTimeout(() => clearKeys("hl-bad"), 350);
}
function hintFor(ch) {
  const c = CH[ch];
  if (!c) return '<span class="muted">not on the keymap — skipped</span>';
  const parts = [];
  if (c.layer) parts.push(`hold <span class="chip hold">${esc(c.layer)}</span> (${esc(NAMES[c.hold[0]])} thumb)`);
  if (c.shift) parts.push(`hold <span class="chip hold">Shift</span> (${esc(NAMES[c.hold[c.hold.length - 1]])})`);
  parts.push(`tap <span class="chip tap">${esc(shown(ch))}</span>`);
  return parts.join(" + ");
}
function esc(s) { return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]); }

// ---------------------------------------------------------------- game
let text = "", pos = 0, marks = [], errors = 0, strokes = 0, t0 = 0, missed = {}, running = false, timer;

function start(t) {
  text = t; pos = 0; marks = new Array(text.length).fill(0); errors = 0; strokes = 0; t0 = 0; missed = {};
  running = true;
  show("play"); skipUntypeable(); draw();
  clearInterval(timer); timer = setInterval(stats, 500);
}
function show(id) { for (const s of ["setup", "play", "done"]) $(s).classList.toggle("hidden", s !== id); }
function skipUntypeable() { while (pos < text.length && !CH[text[pos]]) { marks[pos] = 2; pos++; } }

function draw() {
  if (pos >= text.length) return finish();
  const ch = text[pos];
  const span = (c, i) => {
    const cls = [marks[i] === 1 ? "err" : "", marks[i] === 2 ? "skip" : "", isWs(c) ? "ws" : ""].filter(Boolean).join(" ");
    return `<span${cls ? ` class="${cls}"` : ""}>${esc(shown(c))}</span>`;
  };
  let past = "", next = "";
  for (let i = Math.max(0, pos - 24); i < pos; i++) past += span(text[i], i);
  for (let i = pos + 1; i < Math.min(text.length, pos + 30); i++) next += span(text[i], i);
  $("strip").innerHTML = `<div class="past">${past}</div><div class="cur${isWs(ch) ? " ws" : ""}" id="cur">${esc(shown(ch))}</div><div class="next">${next}</div>`;
  $("hint").innerHTML = hintFor(ch);
  highlight(ch);
  stats();
}

function stats() {
  const mins = t0 ? (performance.now() - t0) / 60000 : 0;
  const good = marks.slice(0, pos).filter(m => m !== 2).length;
  $("s-wpm").textContent = mins > 0.05 ? Math.round(good / 5 / mins) : 0;
  $("s-acc").textContent = strokes ? Math.round(100 * (strokes - errors) / strokes) : 100;
  $("s-err").textContent = errors;
  $("s-pos").textContent = pos; $("s-len").textContent = "/ " + text.length;
  $("bar").style.width = (text.length ? 100 * pos / text.length : 0) + "%";
}

function finish() {
  running = false; clearInterval(timer);
  clearKeys("hl-tap"); clearKeys("hl-hold"); setLayer(null);
  const mins = t0 ? (performance.now() - t0) / 60000 : 0;
  const good = marks.filter(m => m !== 2).length;
  const wpm = mins ? Math.round(good / 5 / mins) : 0;
  const acc = strokes ? Math.round(100 * (strokes - errors) / strokes) : 100;
  $("r-wpm").textContent = `${wpm} wpm`;
  const secs = Math.round(mins * 60);
  $("r-line").textContent = `${acc}% accuracy · ${errors} mistake${errors === 1 ? "" : "s"} · ${good} characters in ${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
  const top = Object.entries(missed).sort((a, b) => b[1] - a[1]).slice(0, 12);
  $("r-missed").innerHTML = top.length ? "Most missed: " + top.map(([c, n]) => `<span class="mono">${esc(shown(c))} ×${n}</span>`).join("") : "No mistakes!";
  show("done");
  $("again").focus();
}

function stop() { running = false; clearInterval(timer); clearKeys("hl-tap"); clearKeys("hl-hold"); setLayer(null); show("setup"); $("src").focus(); }

document.addEventListener("keydown", e => {
  if (!running) return;
  if (e.key === "Escape") { e.preventDefault(); return stop(); }
  if (e.ctrlKey || e.metaKey || (e.altKey && !e.getModifierState("AltGraph"))) return;
  let k = e.key;
  if (k === "Enter") k = "\n"; else if (k === "Tab") k = "\t";
  if (k.length !== 1) return;                 // Shift, CapsLock, arrows, dead keys…
  e.preventDefault();
  if (!t0) t0 = performance.now();
  strokes++;
  const want = text[pos];
  if (k === want) {
    pos++; skipUntypeable(); draw();
  } else {
    errors++; marks[pos] = 1; missed[want] = (missed[want] || 0) + 1;
    flashBad(k);
    const cur = $("cur"); cur.classList.remove("shake"); void cur.offsetWidth; cur.classList.add("shake");
    draw();
  }
});

$("start").onclick = () => {
  const t = prepare($("src").value);
  if (!t) { $("warn").textContent = "Paste some text first."; return; }
  store.set("corne-typing-text", $("src").value);
  start(t);
};
$("again").onclick = () => start(text);
$("new").onclick = () => { show("setup"); $("src").focus(); };
$("src").addEventListener("input", checkText);
for (const id of ["opt-newlines", "opt-typo"]) $(id).addEventListener("change", checkText);
function checkText() {
  const bad = [...new Set([...prepare($("src").value)].filter(c => !CH[c]))];
  $("warn").textContent = bad.length ? `Not on the keymap (will be skipped): ${bad.slice(0, 20).map(shown).join(" ")}` : "";
}
$("toggle-kbd").onclick = () => {
  const h = $("kbdwrap").classList.toggle("hidden");
  $("toggle-kbd").textContent = h ? "Show keyboard" : "Hide keyboard";
  store.set("corne-typing-kbd", h ? "0" : "1");
};
if (store.get("corne-typing-kbd") === "0") $("toggle-kbd").click();
function focusLabel() { $("toggle-focus").textContent = focusOn ? "Show all labels" : "Show current layer only"; }
$("toggle-focus").onclick = () => {
  focusOn = !focusOn; focusLabel(); store.set("corne-typing-focus", focusOn ? "1" : "0");
  if (running) highlight(text[pos]);
};
focusLabel();
$("src").value = store.get("corne-typing-text") ||
  "The quick brown fox jumps over the lazy dog.\nif (x[0] == 42) { return \"ok\"; } // 100% sure: a+b=c & d|e ~ f^g!";
checkText();
$("src").focus();
</script>
</body>
</html>
"""
