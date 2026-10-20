# python3 -I board.py <папка задач> <out.html> [группа] — канбан-доска задач для plannotator annotate.
# С группой — доска группы, без — беклог и плашки открытых групп.
import html
import pathlib
import re
import sys

tasks_dir = pathlib.Path(sys.argv[1]).expanduser()
out = pathlib.Path(sys.argv[2])
group = sys.argv[3] if len(sys.argv) > 3 else None
score = {"low": 1, "medium": 2, "high": 3}
grade = {"effort": {"low": "good", "medium": "mid", "high": "bad"},
         "impact": {"low": "bad", "medium": "mid", "high": "good"}}


def parse(path):
    _, front, body = path.read_text().split("---", 2)
    meta, key = {}, None
    for line in front.strip().splitlines():
        if line.startswith("  - ") and key:
            meta.setdefault(key, []).append(line[4:].strip())
        elif ":" in line:
            key, value = (part.strip() for part in line.split(":", 1))
            meta[key] = value or []
    meta["title"] = next((l[2:] for l in body.splitlines() if l.startswith("# ")), path.stem)
    meta["id"] = path.stem
    effort, impact = score.get(meta.get("effort")), score.get(meta.get("impact"))
    meta["value"] = impact - effort if effort and impact else None
    return meta


service_dirs = {"done", "resources"}
is_closed = lambda t: t.get("status") in ("done", "dropped")
groups = sorted(d for d in tasks_dir.iterdir() if d.is_dir() and d.name.lower() not in service_dirs)
done_dir = next((d for d in tasks_dir.iterdir() if d.name.lower() == "done"), tasks_dir / "done")
newest_first = lambda paths: sorted(paths, key=lambda p: -p.stat().st_mtime)

if group:
    scope = [parse(p) for p in sorted((tasks_dir / group).glob("*.md"))]
    tasks = [t for t in scope if not is_closed(t)]
    closed = [parse(p) for p in newest_first((tasks_dir / group).glob("*.md")) if is_closed(parse(p))]
else:
    tasks = [parse(p) for p in sorted(tasks_dir.glob("*.md"))]
    closed = [parse(p) for p in newest_first(done_dir.glob("*.md"))]

open_ids = {t["id"] for t in tasks}
open_anywhere = {p.stem for p in tasks_dir.rglob("*.md")
                 if done_dir not in p.parents and not is_closed(parse(p))}


def level(axis, t):
    value = t.get(axis, "?")
    return f'<span class="cell solid {axis} {grade[axis].get(value, "unknown")}">{value[:1].upper()}</span>'


def chevron(v, tone):
    if v is None:
        marks = ""
    elif v == 0:
        marks = '<line x1="4" y1="8" x2="12" y2="8"/>'
    else:
        top = (16 - (3 + 4 * (abs(v) - 1))) / 2
        edge, tip = (3, 0) if v > 0 else (0, 3)
        marks = "".join(
            f'<polyline points="4,{y + edge} 8,{y + tip} 12,{y + edge}"/>'
            for y in (top + 4 * i for i in range(abs(v))))
    return f'<svg class="chevron solid {tone}" viewBox="0 0 16 16" width="16" height="16">{marks}</svg>'


def worth(t):
    v = t["value"]
    tone = "unknown" if v is None else "good" if v > 0 else "mid" if v == 0 else "bad"
    hint = f'effort {t.get("effort", "?")} · impact {t.get("impact", "?")} · ценность {"?" if v is None else v}'
    return (f'<span class="worth" title="{html.escape(hint)}">{chevron(v, tone)}'
            f'{level("effort", t)}{level("impact", t)}</span>')


def card(t):
    e = html.escape
    title = re.sub(r"`([^`]+)`", r"<code>\1</code>", e(t["title"]))
    rows = [f'<div class="top"><span class="id" title="Нажми, чтобы скопировать" '
            f'onclick="navigator.clipboard.writeText(this.textContent)">{e(t["id"])}</span>'
            f'<span class="type tinted {e(t.get("type", ""))}">{e(t.get("type", "?"))}</span></div>',
            f'<div class="title">{title}</div>']
    if t.get("waiting-for"):
        rows.append(f'<div class="waiting tinted">Ждём: {e(t["waiting-for"])}</div>')
    if t.get("status") in ("done", "dropped"):
        rows.append(f'<div class="resolution tinted {e(t["status"])}">{e(t.get("resolution") or t["status"])}</div>')
        return f'<div class="card closed">{"".join(rows)}</div>'
    deps = [f'<a class="dep" href="#{e(d)}">{e(d)}</a>' if d in open_ids
            else f'<span class="dep elsewhere" title="в другой группе или беклоге">{e(d)}</span>'
            for d in t.get("depends-on") or [] if d in open_anywhere]
    rows.append(f'<div class="bottom">{worth(t)}'
                f'{"<span class=deps>↳ " + " ".join(deps) + "</span>" if deps else ""}</div>')
    return f'<div class="card" id="{e(t["id"])}">{"".join(rows)}</div>'


def column(title, items, folded=False):
    return (f'<section class="column"><input type="checkbox" class="fold" id="fold-{title}"{" checked" if folded else ""}>'
            f'<label class="head" for="fold-{title}"><h2>{title} <span class="count">{len(items)}</span></h2></label>'
            f'<div class="cards">{"".join(map(card, items))}</div></section>')


def by_value(status):
    return sorted((t for t in tasks if t.get("status") == status),
                  key=lambda t: (-(t["value"] if t["value"] is not None else -9),
                                 score.get(t.get("effort"), 9), t["id"]))


board = ("".join(column(s, by_value(s)) for s in ("open", "in-progress", "waiting"))
         + column("closed", closed, folded=True))
hover_rules = "\n".join(
    f'.board:has(a.dep[href="#{i}"]:hover) [id="{i}"] {{ outline: 2px solid var(--ring); outline-offset: 2px; }}'
    for i in sorted(open_ids))
project = html.escape(tasks_dir.parent.name)
heading = f"{html.escape(group)} — {project}" if group else f"Беклог — {project}"


def group_chip(d):
    statuses = [parse(p).get("status") for p in d.glob("*.md")]
    left = sum(s not in ("done", "dropped") for s in statuses)
    ready = '<span class="ready tinted">готово к ревью</span>' if statuses and not left else ""
    return (f'<div class="group"><span class="group-name">{html.escape(d.name)}</span>'
            f'<span class="group-count">{left} открыто · {len(statuses) - left} закрыто</span>{ready}</div>')


groups_strip = "" if group or not groups else f'<div class="groups">{"".join(map(group_chip, groups))}</div>'

out.write_text(f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="plannotator-theme" content="host"><title>{heading}</title>
<style>
:root {{
  --background: oklch(15% .02 260); --foreground: oklch(90% .01 260);
  --card: oklch(22% .02 260); --muted: oklch(26% .02 260); --muted-foreground: oklch(72% .02 260);
  --primary: oklch(75% .18 280); --border: oklch(35% .02 260); --ring: oklch(75% .18 280);
  --destructive: oklch(65% .2 25); --success: oklch(72% .17 150); --warning: oklch(75% .15 85);
  --font-sans: "Inter Variable", "Inter", system-ui, -apple-system, sans-serif;
  --font-mono: "Geist Mono Variable", "Geist Mono", "JetBrains Mono", ui-monospace, monospace;
  --radius: .625rem; --on-solid: #fff; color-scheme: dark;
}}
@media (prefers-color-scheme: light) {{ :root {{
  --background: oklch(97% .005 260); --foreground: oklch(18% .02 260);
  --card: oklch(100% 0 0); --muted: oklch(92% .01 260); --muted-foreground: oklch(40% .02 260);
  --primary: oklch(50% .25 280); --border: oklch(88% .01 260); --ring: oklch(50% .25 280);
  --destructive: oklch(50% .25 25); --success: oklch(45% .2 150); --warning: oklch(55% .18 85);
  color-scheme: light;
}} }}
* {{ box-sizing: border-box; }}
body {{ font: 14px/1.4 var(--font-sans); background: var(--background); color: var(--foreground); margin: 0; padding: 32px; -webkit-font-smoothing: antialiased; }}
h1 {{ font-size: 22px; font-weight: 600; letter-spacing: -.01em; margin: 0 0 24px; }}
.board {{ display: flex; gap: 16px; align-items: flex-start; }}
.column {{ flex: 1; background: color-mix(in oklch, var(--muted) 45%, var(--background)); border: 1px solid color-mix(in oklch, var(--border) 60%, transparent); border-radius: calc(var(--radius) + 4px); padding: 12px; min-width: 260px; }}
.column h2 {{ display: flex; align-items: center; gap: 8px; font-size: 11px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--muted-foreground); margin: 2px 4px 14px; white-space: nowrap; }}
.count {{ min-width: 18px; padding: 0 6px; border-radius: 999px; background: var(--muted); font-size: 11px; line-height: 18px; text-align: center; letter-spacing: 0; }}
.cards {{ display: flex; flex-direction: column; gap: 10px; }}
.fold {{ display: none; }}
.head {{ display: block; cursor: pointer; user-select: none; }}
.head h2::before {{ content: "▾"; }}
.fold:checked ~ .cards {{ display: none; }}
.fold:checked + .head {{ display: flex; justify-content: center; }}
.fold:checked + .head h2 {{ writing-mode: vertical-rl; margin: 0; }}
.fold:checked + .head h2::before {{ content: none; }}
.fold:checked + .head .count {{ background: none; padding: 0; min-width: 0; line-height: inherit; }}
.column:has(.fold:checked) {{ flex: 0 0 40px; min-width: 0; padding: 16px 0; }}
.card {{ background: var(--card); border: 1px solid color-mix(in oklch, var(--border) 70%, transparent); border-radius: var(--radius); padding: 12px 14px 14px; box-shadow: 0 1px 2px rgb(0 0 0 / .06); transition: border-color .15s; }}
.card:hover {{ border-color: var(--border); }}
.card.closed {{ opacity: .8; }}
.top {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 6px; }}
.id {{ font: 10px/16px var(--font-mono); color: color-mix(in oklch, var(--muted-foreground) 80%, transparent); cursor: copy; user-select: all; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.id:hover {{ color: var(--primary); }}
.title {{ font-weight: 600; line-height: 1.35; letter-spacing: -.005em; }}
.title code {{ font: 12.5px var(--font-mono); padding: 0 3px; border-radius: 4px; background: var(--muted); }}
.type {{ flex: none; display: inline-flex; align-items: center; gap: 5px; font-size: 10.5px; font-weight: 500; line-height: 18px; padding: 0 8px 0 7px; border-radius: 999px; }}
.type::before {{ content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; opacity: .85; }}
.waiting, .resolution {{ margin-top: 10px; font-size: 12px; line-height: 1.45; padding: 6px 10px; border-radius: 6px; }}
.resolution.done::before {{ content: "✓ "; }}
.resolution.dropped::before {{ content: "✕ "; }}
.good, .resolution.done {{ --tone: var(--success); }}
.mid, .waiting {{ --tone: var(--warning); --hue-shift: -15; }}
.bad, .type.bug {{ --tone: var(--destructive); }}
.type.decision {{ --tone: var(--primary); }}
.unknown, .type.task, .resolution.dropped {{ --tone: var(--muted-foreground); }}
.solid, .tinted {{ --norm: oklch(from var(--tone) 64% min(c, .14) calc(h + var(--hue-shift, 0))); }}
.solid {{ background: var(--norm); }}
.tinted {{ background: color-mix(in oklab, var(--norm) 16%, var(--card)); color: color-mix(in oklab, var(--norm) 65%, var(--foreground)); }}
.bottom {{ display: flex; align-items: center; gap: 10px; margin-top: 12px; }}
.worth {{ flex: none; display: inline-flex; align-items: center; cursor: help; }}
.chevron {{ fill: none; stroke: var(--on-solid); stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; border-radius: 3px; margin-right: 4px; }}
.cell {{ width: 20px; height: 16px; font: 600 10px/16px var(--font-mono); color: var(--on-solid); text-align: center; }}
.cell.effort {{ clip-path: polygon(0 0, calc(100% - 5px) 0, 100% 50%, calc(100% - 5px) 100%, 0 100%); border-radius: 3px 0 0 3px; padding-right: 5px; }}
.cell.impact {{ clip-path: polygon(0 0, 100% 0, 100% 100%, 0 100%, 5px 50%); border-radius: 0 3px 3px 0; padding-left: 5px; margin-left: -3.5px; }}
.deps {{ font: 10px var(--font-mono); color: var(--muted-foreground); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.dep {{ color: var(--primary); text-decoration: none; }}
.dep:hover {{ text-decoration: underline; }}
.dep.elsewhere {{ color: var(--muted-foreground); text-decoration: none; }}
.groups {{ display: flex; flex-wrap: wrap; gap: 8px; margin: -8px 0 20px; }}
.group {{ display: inline-flex; align-items: center; gap: 10px; padding: 6px 12px; border-radius: 999px; background: var(--card); border: 1px solid color-mix(in oklch, var(--border) 70%, transparent); font-size: 12px; }}
.group-name {{ font: 500 12px var(--font-mono); }}
.group-count {{ color: var(--muted-foreground); }}
.ready {{ --tone: var(--success); padding: 0 8px; border-radius: 999px; font-size: 11px; line-height: 18px; }}
{hover_rules}
</style></head><body>
<h1>{heading}</h1>
{groups_strip}
<div class="board">{board}</div>
</body></html>
""")
print(out)
