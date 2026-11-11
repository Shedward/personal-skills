# python3 -I board.py <папка задач> <out.html> [группа] [--open=<id>] — канбан-доска задач для plannotator annotate.
# С группой — доска группы, без — беклог и плашки открытых групп. --open — сразу открыть задачу в панели.
import html
import pathlib
import sys
from itertools import count

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import todo_render as ui

flags = [a for a in sys.argv[1:] if a.startswith("--")]
args = [a for a in sys.argv[1:] if not a.startswith("--")]
tasks_dir = pathlib.Path(args[0]).expanduser()
out = pathlib.Path(args[1])
group = args[2] if len(args) > 2 else None
opened = next((f.split("=", 1)[1] for f in flags if f.startswith("--open=")), None)
attachments = ui.Attachments(out, tasks_dir)


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
    meta["body"] = ui.attach_body(body, path.parent, attachments)
    meta["mtime"] = path.stat().st_mtime
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

lanes = ui.lanes_for(tasks + closed)
board = ui.columns(lanes, count(1), open_ids, open_anywhere)
hover_rules = ui.hover_rules(open_ids, tasks + closed)
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
<style>{ui.style()}
{hover_rules}
</style></head><body>
<h1>{heading}</h1>
{groups_strip}
<div class="layout"><div class="board">{board}</div>{"".join(ui.view(t, opened) for t in tasks + closed)}</div>
<div class="general" id="general-comment" onclick="this.classList.add('hint'); setTimeout(() => this.classList.remove('hint'), 2500)">💬 Для общих комментариев</div>
{ui.SCRIPT}
</body></html>
""")
if opened and opened not in {t["id"] for t in tasks + closed}:
    sys.exit(f"{opened}: нет на этой доске — укажи группу задачи")
print(out)
