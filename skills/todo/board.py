from itertools import count
import html
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import todo_render as ui
from todo_cards import group_dirs, read_card


def render(tasks_dir, output, group=None, opened=None, views=None):
    groups = group_dirs(tasks_dir)
    done_dir = next((d for d in tasks_dir.iterdir() if d.name.lower() == "done"), tasks_dir / "done")
    by_dir = {d: [read_card(p, tasks_dir) for p in sorted(d.glob("*.md"))] for d in [tasks_dir, *groups]}
    if group:
        directory = tasks_dir / group
        if directory.parent == done_dir and directory.name.casefold() != "resources":
            scope = [read_card(p, tasks_dir) for p in sorted(directory.glob("*.md"))]
        else:
            scope = by_dir.get(directory, [])
    else:
        scope = by_dir[tasks_dir] + [read_card(p, tasks_dir) for p in done_dir.glob("*.md")]

    open_anywhere = {t["id"] for cards in by_dir.values() for t in cards if ui.lane(t) != "closed"}
    open_ids = {t["id"] for t in scope if ui.lane(t) != "closed"}
    attachments = ui.Attachments(output, tasks_dir) if views is None else None
    for t in scope:
        path = tasks_dir / t["path"]
        t["mtime"] = path.stat().st_mtime
        if views is None:
            t["body"] = ui.card_body(path, attachments)
    if len({t["id"] for t in scope}) != len(scope):
        raise ValueError("В группе есть карточки с одинаковым ID")
    board = ui.columns(ui.lanes_for(scope), count(1), open_ids, open_anywhere)
    if opened and opened not in {t["id"] for t in scope}:
        raise ValueError(f"{opened}: нет на этой доске — укажи группу задачи")
    dialogs = ""
    if views is None:
        dialogs = "".join(ui.view(t, opened) for t in scope)
    else:
        views.update(("view-" + t["id"], t) for t in scope)

    def group_chip(d):
        members = by_dir[d]
        left = [t for t in members if ui.lane(t) != "closed"]
        ready = '<span class="ready tinted">готово к ревью</span>' if members and not left else ""
        return (f'<div class="group"><span class="group-name">{html.escape(d.name)}</span>'
                f'<span class="group-count">{ui.status_count(left, "open-total", "Открыто")} открыто · '
                f'{len(members) - len(left)} закрыто</span>{ready}</div>')

    groups_strip = "" if group or not groups else f'<div class="groups">{"".join(map(group_chip, groups))}</div>'
    heading = f"{html.escape(group or 'Беклог')} — {html.escape(tasks_dir.parent.name)}"
    page = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="plannotator-theme" content="host"><title>{heading}</title>
<style>{ui.style()}
{ui.hover_rules(open_ids, scope)}
</style></head><body>
<h1>{heading}</h1>
{groups_strip}
<div class="layout"><div class="board">{board}</div>{dialogs}</div>
<div class="general" id="general-comment" onclick="this.classList.add('hint'); setTimeout(() => this.classList.remove('hint'), 2500)">💬 Для общих комментариев</div>
{ui.SCRIPT}
</body></html>
"""
    if views is not None:
        return page
    output.write_text(page, encoding="utf-8")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Канбан-доска todo")
    parser.add_argument("tasks", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("group", nargs="?")
    parser.add_argument("--open")
    args = parser.parse_args()
    try:
        render(args.tasks.expanduser(), args.output, args.group, args.open)
    except ValueError as error:
        parser.exit(1, f"{error}\n")
    print(args.output)
