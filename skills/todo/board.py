# python3 -I board.py <папка задач> <out.html> [группа] [--open=<id>] — канбан-доска задач для plannotator annotate.
# С группой — доска группы, без — беклог и плашки открытых групп. --open — сразу открыть задачу в панели.
import html
import pathlib
import re
import shutil
import sys
import zlib

flags = [a for a in sys.argv[1:] if a.startswith("--")]
args = [a for a in sys.argv[1:] if not a.startswith("--")]
tasks_dir = pathlib.Path(args[0]).expanduser()
out = pathlib.Path(args[1])
group = args[2] if len(args) > 2 else None
opened = next((f.split("=", 1)[1] for f in flags if f.startswith("--open=")), None)
score = {"low": 1, "medium": 2, "high": 3}
grade = {"effort": {"low": "good", "medium": "mid", "high": "bad"},
         "impact": {"low": "bad", "medium": "mid", "high": "good"}}


def attach(image):
    # Plannotator отдаёт странице файлы только из её папки — копируем вложения туда
    assets = out.parent / "board-assets"
    assets.mkdir(exist_ok=True)
    if image.is_file():
        shutil.copy2(image, assets / image.name)
    return f"board-assets/{image.name}"


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
    meta["body"] = re.sub(r"(!\[[^\]]*\]\()([^)]+)\)", lambda m: m[1] + attach(path.parent / m[2]) + ")", body)
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


telegram_hues = (25, 60, 300, 145, 200, 255, 350)


def blocker(t):
    actor, _, need = str(t.get("next") or "").partition(":")
    return actor.strip(), need.strip()


def card(t):
    e = html.escape
    title = re.sub(r"`([^`]+)`", r"<code>\1</code>", e(t["title"]))
    rows = [f'<div class="top"><span class="ref"><span class="n">[{t["n"]}]</span>'
            f'<span class="id" title="Нажми, чтобы скопировать" '
            f'onclick="navigator.clipboard.writeText(this.textContent)">{e(t["id"])}</span></span>'
            f'<span class="type tinted {e(t.get("type", ""))}">{e(t.get("type", "?"))}</span></div>',
            f'<span class="title" onclick="openView(\'{e(t["id"])}\')">{title}</span>']
    if t.get("status") in ("done", "dropped"):
        rows.append(f'<div class="resolution tinted {e(t["status"])}">{e(t.get("resolution") or t["status"])}</div>')
        return f'<div class="card closed" id="{e(t["id"])}">{"".join(rows)}</div>'
    deps = [f'<a class="dep" href="#{e(d)}">{e(d)}</a>' if d in open_ids
            else f'<span class="dep elsewhere" title="в другой группе или беклоге">{e(d)}</span>'
            for d in t.get("depends-on") or [] if d in open_anywhere]
    actor, need = blocker(t)
    mover = actor or "agent"
    hue = f'style="--hue: {telegram_hues[zlib.crc32(mover.encode()) % len(telegram_hues)]}"'
    if actor:
        rows.append(f'<div class="blocker tinted" {hue}>{labels.get(actor) or "Ждём " + e(actor)}: {e(need)}</div>')
    avatars = (f'<span class="avatar" title="{e(mover)}" {hue}>'
               f'{e("".join(w[0] for w in mover.split("-")[:2]) if "-" in mover else mover[:2]).upper()}</span>'
               if t.get("status") == "in-progress" else "")
    if deps:
        rows.append(f'<div class="deps">{"".join(f"<span>↳ {d}</span>" for d in deps)}</div>')
    rows.append(f'<div class="bottom">{worth(t)}'
                f'{"<span class=needs>" + avatars + "</span>" if avatars else ""}</div>')
    return f'<div class="card" id="{e(t["id"])}">{"".join(rows)}</div>'


def inline(s):
    s = html.escape(s)
    s = re.sub(r"!\[([^\]]*)\]\(([^)]*)\)", r'<figure><img src="\2" alt="\1" loading="lazy"><figcaption>\1</figcaption></figure>', s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank">\1</a>', s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)


# ponytail: минимальный markdown (заголовки, абзацы, плоские списки, код, картинки)
def markdown(text):
    out, para, items, code = [], [], [], None

    def flush():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>")
            items.clear()

    for line in text.splitlines():
        heading = re.match(r"(#+) (.*)", line)
        item = re.match(r"\s*(?:[-*]|\d+\.) (.*)", line)
        if line.startswith("```"):
            if code is None:
                flush()
                code = []
            else:
                out.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
                code = None
        elif code is not None:
            code.append(line)
        elif heading:
            flush()
            if len(heading[1]) > 1:
                out.append(f"<h{len(heading[1]) + 1}>{inline(heading[2])}</h{len(heading[1]) + 1}>")
        elif item:
            if para:
                flush()
            items.append(item[1])
        elif items and line.startswith("  ") and line.strip():
            items[-1] += " " + line.strip()
        elif not line.strip():
            flush()
        else:
            if items:
                flush()
            para.append(line.strip())
    flush()
    return "".join(out)


def view(t):
    title = re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(t["title"]))
    return (f'<dialog class="view" id="view-{html.escape(t["id"])}"{" open" if t["id"] == opened else ""}>'
            f'<div class="sheet"><form method="dialog"><button class="close" aria-label="Закрыть">×</button></form>'
            f'<h2><span class="n">[{t["n"]}]</span> {title}</h2>{markdown(t["body"])}</div></dialog>')


def column(title, items, folded=False):
    return (f'<section class="column"><input type="checkbox" class="fold" id="fold-{title}"{" checked" if folded else ""}>'
            f'<label class="head" for="fold-{title}"><h2>{title} <span class="count">{len(items)}</span></h2></label>'
            f'<div class="cards">{"".join(map(card, items))}</div></section>')


labels = {"user": "От тебя", "agent": "Агент"}


def lane(t):
    return "waiting" if blocker(t)[0] not in ("", *labels) else t.get("status")


def by_value(status):
    return sorted((t for t in tasks if lane(t) == status),
                  key=lambda t: (-(t["value"] if t["value"] is not None else -9),
                                 score.get(t.get("effort"), 9), t["id"]))


lanes = [(s, by_value(s)) for s in ("open", "in-progress", "waiting")] + [("closed", closed)]
for n, t in enumerate((t for _, items in lanes for t in items), 1):
    t["n"] = n
board = "".join(column(s, items, folded=s == "closed") for s, items in lanes)
hover_rules = "\n".join(
    f'.board:has(a.dep[href="#{i}"]:hover) [id="{i}"] {{ outline: 2px solid var(--ring); outline-offset: 2px; }}'
    for i in sorted(open_ids)) + "\n" + "\n".join(
    f'.layout:has([id="view-{t["id"]}"][open]) [id="{t["id"]}"] {{ border-color: var(--ring); }}'
    for t in tasks + closed)
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
.board {{ flex: 1; min-width: 0; overflow-x: auto; display: flex; gap: 16px; align-items: flex-start; }}
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
.ref {{ display: flex; gap: 6px; min-width: 0; }}
.n {{ flex: none; font: 600 10px/16px var(--font-mono); color: var(--muted-foreground); }}
.view h2 .n {{ font-size: inherit; line-height: inherit; }}
.title {{ display: block; font-weight: 600; line-height: 1.35; letter-spacing: -.005em; cursor: pointer; }}
.title:hover {{ text-decoration: underline; text-decoration-color: color-mix(in oklab, var(--foreground) 35%, transparent); text-underline-offset: 3px; }}
.title code {{ font: 12.5px var(--font-mono); padding: 0 3px; border-radius: 4px; background: var(--muted); }}
.type {{ flex: none; font-size: 8.5px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; line-height: 14px; padding: 0 6px; border-radius: 999px; }}
.blocker, .resolution {{ margin-top: 10px; font-size: 12px; line-height: 1.45; padding: 6px 10px; border-radius: 6px; }}
.blocker {{ --tone: oklch(64% .14 var(--hue)); border-radius: 11px; }}
.resolution.done::before {{ content: "✓ "; }}
.resolution.dropped::before {{ content: "✕ "; }}
.good, .resolution.done {{ --tone: var(--success); }}
.mid {{ --tone: var(--warning); --hue-shift: -15; }}
.bad, .type.fix {{ --tone: var(--destructive); }}
.type.decide {{ --tone: var(--primary); }}
.type.check {{ --tone: var(--success); --hue-shift: 60; }}
.unknown, .type.make, .resolution.dropped {{ --tone: var(--muted-foreground); }}
.solid, .tinted {{ --norm: oklch(from var(--tone) 64% min(c, .14) calc(h + var(--hue-shift, 0))); }}
.solid {{ background: var(--norm); }}
.tinted {{ background: color-mix(in oklab, var(--norm) 16%, var(--card)); color: color-mix(in oklab, var(--norm) 65%, var(--foreground)); }}
.bottom {{ display: flex; align-items: center; gap: 10px; margin-top: 12px; }}
.worth {{ flex: none; display: inline-flex; align-items: center; cursor: help; }}
.chevron {{ fill: none; stroke: var(--on-solid); stroke-width: 1.4; stroke-linecap: round; stroke-linejoin: round; border-radius: 3px; margin-right: 2px; }}
.cell {{ width: 20px; height: 16px; font: 600 10px/16px var(--font-mono); color: var(--on-solid); text-align: center; }}
.cell.effort {{ clip-path: polygon(0 0, calc(100% - 5px) 0, 100% 50%, calc(100% - 5px) 100%, 0 100%); border-radius: 3px 0 0 3px; padding-right: 5px; }}
.cell.impact {{ clip-path: polygon(0 0, 100% 0, 100% 100%, 0 100%, 5px 50%); border-radius: 0 3px 3px 0; padding-left: 5px; margin-left: -3.5px; }}
.needs {{ flex: none; display: inline-flex; margin-left: auto; }}
.avatar {{ width: 22px; height: 22px; border-radius: 50%; background: oklch(64% .14 var(--hue)); color: #fff; font: 600 9px/22px var(--font-mono); text-align: center; box-shadow: 0 0 0 2px var(--card); cursor: help; }}
.avatar + .avatar {{ margin-left: -5px; }}
.deps {{ display: flex; flex-direction: column; gap: 2px; margin-top: 10px; font: 10px/16px var(--font-mono); color: var(--muted-foreground); }}
.deps span {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.dep {{ color: var(--primary); text-decoration: none; }}
.dep:hover {{ text-decoration: underline; }}
.dep.elsewhere {{ color: var(--muted-foreground); text-decoration: none; }}
.groups {{ display: flex; flex-wrap: wrap; gap: 8px; margin: -8px 0 20px; }}
.group {{ display: inline-flex; align-items: center; gap: 10px; padding: 6px 12px; border-radius: 999px; background: var(--card); border: 1px solid color-mix(in oklch, var(--border) 70%, transparent); font-size: 12px; }}
.group-name {{ font: 500 12px var(--font-mono); }}
.group-count {{ color: var(--muted-foreground); }}
.ready {{ --tone: var(--success); padding: 0 8px; border-radius: 999px; font-size: 11px; line-height: 18px; }}
.layout {{ display: flex; gap: 16px; align-items: flex-start; }}
.view {{ position: sticky; top: 16px; flex: 0 0 min(520px, 42vw); margin: 0; padding: 0; border: 1px solid var(--border); border-radius: calc(var(--radius) + 4px); background: var(--card); color: var(--foreground); box-shadow: 0 8px 32px rgb(0 0 0 / .18); }}
.sheet {{ padding: 28px 32px 32px; line-height: 1.6; }}
.sheet h2 {{ font-size: 18px; line-height: 1.35; letter-spacing: -.01em; margin: 0 32px 16px 0; }}
.sheet h3 {{ font-size: 11px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--muted-foreground); margin: 28px 0 8px; }}
.sheet h4 {{ font-size: 14px; margin: 20px 0 6px; }}
.sheet p {{ margin: 0 0 12px; }}
.sheet ul {{ margin: 0 0 12px; padding-left: 20px; }}
.sheet li + li {{ margin-top: 6px; }}
.sheet code {{ font: 12.5px var(--font-mono); padding: 1px 4px; border-radius: 4px; background: var(--muted); }}
.sheet pre {{ margin: 0 0 12px; padding: 12px 14px; border-radius: 8px; background: var(--muted); overflow: auto; }}
.sheet pre code {{ padding: 0; background: none; }}
.sheet a {{ color: var(--primary); }}
.sheet figure {{ margin: 8px 0 16px; }}
.sheet img {{ display: block; max-width: 100%; max-height: 60vh; border: 1px solid var(--border); border-radius: 8px; }}
.sheet figcaption {{ margin-top: 6px; font-size: 12px; color: var(--muted-foreground); }}
.close {{ float: right; margin: -10px -14px 0 0; width: 32px; height: 32px; border: 0; border-radius: 8px; background: none; color: var(--muted-foreground); font-size: 20px; cursor: pointer; }}
.close:hover {{ background: var(--muted); color: var(--foreground); }}
.general {{ position: fixed; right: 16px; top: 16px; z-index: 10; padding: 8px 14px; border-radius: 999px; background: var(--card); border: 1px solid var(--border); box-shadow: 0 4px 16px rgb(0 0 0 / .15); font-size: 13px; cursor: pointer; }}
.general::after {{ content: "Паркуй общий комментарий аннотацией на этом элементе"; position: absolute; right: 0; top: calc(100% + 8px); width: max-content; padding: 6px 10px; border-radius: 8px; background: var(--muted); color: var(--muted-foreground); font-size: 12px; opacity: 0; transform: translateY(-4px); transition: opacity .2s, transform .2s; pointer-events: none; }}
.general.hint::after {{ opacity: 1; transform: none; }}
{hover_rules}
</style></head><body>
<h1>{heading}</h1>
{groups_strip}
<div class="layout"><div class="board">{board}</div>{"".join(map(view, tasks + closed))}</div>
<div class="general" id="general-comment" onclick="this.classList.add('hint'); setTimeout(() => this.classList.remove('hint'), 2500)">💬 Для общих комментариев</div>
<script>
const closeViews = () => document.querySelectorAll(".view[open]").forEach(d => d.close());
function openView(id) {{ closeViews(); document.getElementById("view-" + id).show(); }}
document.addEventListener("keydown", e => e.key === "Escape" && closeViews());
</script>
</body></html>
""")
if opened and opened not in {t["id"] for t in tasks + closed}:
    sys.exit(f"{opened}: нет на этой доске — укажи группу задачи")
print(out)
