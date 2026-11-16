// Sample texts for the typing tutor's dropdown.
// Texts are typed exactly as written: every space is a keystroke, every line break is Enter.
const SAMPLES = [
  // ------------------------------------------------------------------ English
  { group: "English", title: "Pangrams", text: `The quick brown fox jumps over the lazy dog.
Pack my box with five dozen liquor jugs.
How vexingly quick daft zebras jump!
Sphinx of black quartz, judge my vow.
The five boxing wizards jump quickly.` },
  { group: "English", title: "Morning routine", text: `Every morning I make a pot of coffee, open the window, and spend ten minutes doing nothing at all. It's the only part of the day that doesn't belong to anyone else. By the time the kettle clicks off, the street below has started to wake up: a bus sighs at the stop, someone drags a bin to the curb, and the bakery on the corner props its door open with a brick.` },
  { group: "English", title: "Slack message", text: `Heads up: #4821 broke staging again. \`main\` is red because \`test_retry_backoff\` is flaky (passes locally, fails in CI ~1 in 3 runs)

What I found so far:
- \`retry()\` sleeps for \`2 ** attempt\` ms but the mock clock never advances
- the fixture in \`conftest.py\` is shared between workers, so order matters
- reverting #4807 "fixes" it, but I don't think that's the real cause

Can someone take a look before standup? I'll push a \`skip\` marker as a stopgap in #4822` },
  { group: "English", title: "Keyboards", text: `A split keyboard lets each hand rest at its own natural angle. With fewer keys, every key has to work harder: a single thumb key might be Space when tapped and a whole layer of numbers when held. It feels strange for a week or two. Then one day you reach for a symbol without thinking, and the old keyboard starts to look enormous.` },
  { group: "English", title: "Numbers and dates", text: `The meeting moved from 9:15 to 10:45 on 3 March 2027. Tickets cost $24.50 each, or $89 for a pack of four (save 9%). Flight LO 281 departs at 06:40 from gate B12; boarding closes 20 minutes earlier. Call +48 600 123 456 or write to orders@example.com before 31/12.` },
  { group: "English", title: "Recipe", text: `Pancakes (makes 8)

- 200 g flour
- 2 eggs
- 300 ml milk
- 1 tbsp melted butter, plus extra for the pan
- a pinch of salt

Whisk everything into a smooth batter and let it rest for 15 minutes. Heat a pan over medium heat, pour in about 1/4 cup of batter, and cook for 1-2 minutes per side until golden.` },
  // ------------------------------------------------------------------ Polski
  { group: "Polski", title: "Pangramy", text: `Zażółć gęślą jaźń.
Pchnąć w tę łódź jeża lub ośm skrzyń fig.
Jeżu klątw, spłódź Finom część gry hańb!
Stróż pchnął kość w quiz gędźb vel fax myjń.` },
  { group: "Polski", title: "Poranek", text: `Rano zawsze zaczynam od kawy. Siadam przy oknie, patrzę na podwórko i przez kilka minut nie robię nic. Sąsiad wyprowadza psa, ktoś trzaska drzwiami od klatki, a na parapecie gołębie kłócą się o okruchy. Dopiero kiedy kubek jest pusty, otwieram laptopa i sprawdzam, co przyniósł nowy dzień.` },
  { group: "Polski", title: "Wiadomość na Slacku", text: `Uwaga: #4821 znowu wywaliło staging. \`main\` jest czerwony, bo \`test_retry_backoff\` jest flaky (lokalnie przechodzi, w CI pada co trzeci raz)

Co udało mi się ustalić:
- \`retry()\` czeka \`2 ** attempt\` ms, ale zegar w mocku nigdy się nie przesuwa
- fixture w \`conftest.py\` jest współdzielony między workerami, więc kolejność ma znaczenie
- revert #4807 "naprawia" problem, ale to chyba nie jest prawdziwa przyczyna

Może ktoś zerknąć przed dailym? w #4822 wrzucę tymczasowo \`skip\`` },
  { group: "Polski", title: "Klawiatura", text: `Dzielona klawiatura pozwala trzymać dłonie szerzej i bardziej naturalnie. Ma mniej klawiszy, więc każdy z nich pełni kilka funkcji: krótkie wciśnięcie daje spację, a przytrzymanie przełącza na warstwę z cyframi. Pierwsze dni są trudne, ale po tygodniu palce same zaczynają pamiętać, gdzie szukać nawiasów.` },
  { group: "Polski", title: "Przepis", text: `Placki ziemniaczane

Zetrzyj 1 kg ziemniaków i jedną cebulę na tarce o drobnych oczkach. Odlej nadmiar wody, dodaj 2 jajka, 3 łyżki mąki, sól i pieprz. Smaż na rozgrzanym oleju z obu stron, aż będą złociste i chrupiące. Podawaj ze śmietaną albo z gulaszem.` },
  // ------------------------------------------------------------------ Code
  { group: "Code", title: "Python: word count", text: `from collections import Counter
from pathlib import Path


def top_words(path: Path, n: int = 10) -> list[tuple[str, int]]:
    words = Path(path).read_text().lower().split()
    counts = Counter(w.strip(".,!?;:\\"'()") for w in words)
    return counts.most_common(n)


if __name__ == "__main__":
    for word, count in top_words("notes.txt"):
        print(f"{word:>12} {count}")` },
  { group: "Code", title: "Python: dataclass", text: `@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def __add__(self, other: "Point") -> "Point":
        return Point(self.x + other.x, self.y + other.y)

    def dist(self, other: "Point") -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5` },
  { group: "Code", title: "JavaScript: fetch", text: `async function loadUsers(page = 1) {
  const res = await fetch(\`/api/users?page=\${page}&limit=20\`);
  if (!res.ok) throw new Error(\`HTTP \${res.status}\`);
  const { items, total } = await res.json();
  return items.filter(u => u.active && !u.deleted).map(u => ({ id: u.id, name: u.name }));
}` },
  { group: "Code", title: "TypeScript: types", text: `type Result<T, E = Error> = { ok: true; value: T } | { ok: false; error: E };

interface Config {
  host: string;
  port?: number;
  tags: Record<string, string[]>;
}

export const parse = (raw: string): Result<Config> => {
  try { return { ok: true, value: JSON.parse(raw) as Config }; }
  catch (e) { return { ok: false, error: e as Error }; }
};` },
  { group: "Code", title: "Rust: match", text: `fn classify(n: i32) -> &'static str {
    match n {
        i32::MIN..=-1 => "negative",
        0 => "zero",
        1..=9 => "small",
        _ if n % 2 == 0 => "big & even",
        _ => "big & odd",
    }
}

let v: Vec<_> = (0..20).filter(|x| x % 3 != 0).map(|x| x * x).collect();` },
  { group: "Code", title: "Go: HTTP handler", text: `func handler(w http.ResponseWriter, r *http.Request) {
	name := r.URL.Query().Get("name")
	if name == "" {
		http.Error(w, "missing name", http.StatusBadRequest)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"hello": name})
}` },
  { group: "Code", title: "C: pointers", text: `#include <stdio.h>

int sum(const int *a, size_t n) {
    int s = 0;
    for (size_t i = 0; i < n; ++i)
        s += a[i];
    return s;
}

int main(void) {
    int xs[] = {3, 1, 4, 1, 5, 9, 2, 6};
    printf("sum = %d\\n", sum(xs, sizeof xs / sizeof *xs));
    return 0;
}` },
  { group: "Code", title: "SQL: report", text: `SELECT c.name, COUNT(o.id) AS orders, SUM(o.total) AS revenue
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id AND o.created_at >= '2026-01-01'
WHERE c.country IN ('PL', 'DE', 'CZ')
GROUP BY c.name
HAVING SUM(o.total) > 1000
ORDER BY revenue DESC
LIMIT 25;` },
  { group: "Code", title: "Regex & one-liners", text: `^[a-z0-9._%+-]+@[a-z0-9.-]+\\.[a-z]{2,}$
\\b(\\d{4})-(\\d{2})-(\\d{2})\\b
s/^\\s+|\\s+$//g
[x for x in range(100) if x % 7 == 0 or '7' in str(x)]
a ^= b; b ^= a; a ^= b;
flags = (flags & ~MASK) | (value << SHIFT);` },
  // ------------------------------------------------------------------ Shell
  { group: "Shell", title: "git workflow", text: `git status
git switch -c fix/typo-in-readme
git add -p README.md
git commit -m "Fix typo in install section"
git fetch origin && git rebase origin/main
git push -u origin HEAD
git log --oneline --graph -10
git stash push -m "wip: half-done refactor"
git diff HEAD~3 -- src/*.py` },
  { group: "Shell", title: "Finding things", text: `find . -name '*.log' -mtime +7 -delete
grep -rn --include='*.py' 'TODO' src/ | wc -l
du -sh ~/Downloads/* | sort -h | tail -5
ls -la /etc | grep -v '^d'
fd -e toml -x wc -l {}
rg -i 'error|warn' /var/log/syslog | less` },
  { group: "Shell", title: "Pipes and loops", text: `cat access.log | awk '{print $1}' | sort | uniq -c | sort -rn | head
for f in *.jpg; do convert "$f" -resize 50% "small_\${f%.jpg}.png"; done
seq 1 10 | xargs -I{} echo "item {}"
export PATH="$HOME/.local/bin:$PATH"
[ -f ~/.zshrc ] && source ~/.zshrc || echo "no zshrc" >&2
echo $(( (17 + 25) * 3 / 2 ))` },
  { group: "Shell", title: "Docker and systemd", text: `docker ps -a --format '{{.Names}}\\t{{.Status}}'
docker run --rm -it -v "$PWD":/app -p 8080:80 nginx:alpine
docker compose up -d && docker compose logs -f web
sudo systemctl restart nginx.service
journalctl -u nginx --since "1 hour ago" -p err
systemctl --user enable --now syncthing` },
  { group: "Shell", title: "Network and remote", text: `ssh -L 5432:localhost:5432 deploy@10.0.1.17
scp -r ./dist/ user@example.com:/var/www/site/
curl -sSL -H 'Accept: application/json' https://api.example.com/v1/items?limit=5 | jq '.[0]'
rsync -avz --delete --exclude='.git/' ./ backup:/srv/projects/
ping -c 4 1.1.1.1
ip -br addr show` },
  { group: "Shell", title: "Vim commands", text: `:%s/foo/bar/gc
:g/^$/d
:set nu rnu
:vsp ~/.config/nvim/init.lua
:wq!
ciw"+p
dt)
>>
:norm A;` },
  // ------------------------------------------------------------------ Config & markup
  { group: "Config & markup", title: "TOML", text: `[package]
name = "corne-tools"
version = "0.3.1"
authors = ["Łukasz <me@example.com>"]

[settings]
TAPPING_TERM = 200
PERMISSIVE_HOLD = true
layers = ["BASE", "NUM", "SYM", "NAV"]` },
  { group: "Config & markup", title: "YAML", text: `services:
  web:
    image: "nginx:1.27"
    ports: ["8080:80"]
    environment:
      - TZ=Europe/Warsaw
      - LOG_LEVEL=debug
    depends_on: [db]
  db:
    image: postgres:17
    volumes:
      - ./data:/var/lib/postgresql/data  # persist` },
  { group: "Config & markup", title: "JSON", text: `{
  "name": "typing-tutor",
  "version": "1.0.0",
  "scripts": { "build": "esbuild src/main.ts --bundle --outfile=dist/app.js", "test": "vitest" },
  "tags": ["keyboard", "corne", "qmk"],
  "enabled": true,
  "retries": 3,
  "ratio": 0.75,
  "owner": null
}` },
  { group: "Config & markup", title: "HTML", text: `<!doctype html>
<html lang="pl">
<head><meta charset="utf-8"><title>Test</title></head>
<body>
  <nav class="top"><a href="/">Home</a> | <a href="/about?ref=nav#team">About</a></nav>
  <img src="logo.svg" alt="Logo" width="120">
  <p>Price: <strong>&euro;19.99</strong> &mdash; <em>limited offer!</em></p>
</body>
</html>` },
  { group: "Config & markup", title: "Markdown", text: `# Release notes (v2.4)

- **New:** \`kb.py diff --json\` prints machine-readable output
- *Fixed:* layer names with dashes, e.g. \`NAV-2\`
- See [the docs](https://example.com/docs#layers) for details

> Note: run \`pip install -U tool\` first.

| Key | Tap | Hold |
|-----|-----|------|
| A   | a   | Gui  |` },
  // ------------------------------------------------------------------ Drills
  { group: "Drills", title: "Brackets & operators", text: `() [] {} <> () [] {} <>
a[i] f(x) {k: v} <T> x->y
== != <= >= && || ++ -- += -= *= /= %=
=> -> :: ... ?? ?. |> <- <<= >>=
!x ~y a^b a&b a|b a%b @dec #tag $var` },
  { group: "Drills", title: "Numbers", text: `1234 5678 9012 3456 7890
10 20 30 40 50 60 70 80 90 100
3.14159 2.71828 1.41421 0.57721
192.168.0.1 255.255.255.0 127.0.0.1:8080
2026-11-15 23:59:59 +01:00
0x1F 0xFF 0b1010 0o755 1e-9 -42` },
  { group: "Drills", title: "Shifted symbols", text: `!@#$%^&*()_+ !@#$%^&*()_+
~ ! @ # $ % ^ & * ( ) _ + { } | : " < > ?
"quoted" 'single' \`back\` ~/home $HOME %PATH% #!/bin/sh
a_b_c A+B=C {x: "y"} <a|b> 50% off! @user #42` },
];
