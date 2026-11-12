"""python3 -I board.py SNAPSHOT.json BOARD.html [--prs PRS.json]"""

import argparse
from itertools import count
import re
from datetime import datetime
import sys
from html import escape
from pathlib import Path
from urllib.parse import urlsplit


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "todo"))
import todo_render as ui

GROUPS = {
    "open": ("Открыты", "planned", 0),
    "in progress": ("В работе", "active", 1),
    "ready for testing": ("Ждут тестирования", "waiting", 3),
    "closed": ("Закрыты", "complete", 4),
    "done": ("Завершены", "complete", 4),
}

LANE_LABELS = ("Открыты", "В работе", "Ждут", "Закрыты")


def link(label, url):
    if url and urlsplit(url).scheme in {"https", "http"} and urlsplit(url).netloc:
        return f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'
    return escape(label)


def issue_dialog(issue):
    key = escape(issue["key"])
    description = issue.get("description")
    body = ("Описание отсутствует." if description == "" else "Описание недоступно в этом снимке.")
    if description:
        body = description
    body = re.sub(r"(?m)^h[1-6]\. +(.+)$", r"<h3>\1</h3>", escape(body))
    prs = issue.get("prs")
    pr_text = "PR не проверены" if prs is None else "PR не найдены"
    if prs:
        pr_text = " · ".join(link(pr["label"], pr.get("url")) for pr in prs)
    return (f'<dialog class="view" id="issue-{key}" aria-label="{key}"><div class="sheet">'
            f'{ui.CLOSE_BUTTON}'
            f'<div class="issue-meta">{link(issue["key"], issue.get("url"))} · {escape(issue["status"])}</div>'
            f'<h2>{escape(issue["title"])}</h2><div class="jira-description">{body}</div>'
            f'<p class="pr">{pr_text}</p></div></dialog>')


def render(snapshot, output, current, branch_key=None, views=None):
    portfolio, issues = snapshot["portfolio"], snapshot["issues"]
    records = [portfolio, *issues]
    root = Path(snapshot["tasks_root"]).expanduser().resolve() if snapshot.get("tasks_root") else None
    attachments = ui.Attachments(output, root) if root and views is None else None
    cards = [card for record in records for card in record["cards"]]
    card_ids = {c["id"] for c in cards}
    if len(card_ids) != len(cards):
        raise ValueError("В снимке есть карточки с одинаковым ID. Проверь принадлежность карточек группам.")
    open_ids = {c["id"] for c in cards if ui.lane(c) != "closed"}
    dependencies = {dep for c in cards for dep in c.get("depends-on", [])}
    open_anywhere = set(open_ids)
    external = dependencies - card_ids
    if root and root.is_dir() and external:
        from todo_cards import group_dirs, read_card
        for directory in (root, *group_dirs(root)):
            for path in directory.glob("*.md"):
                if path.stem in external and ui.lane(read_card(path, root)) != "closed":
                    open_anywhere.add(path.stem)

    for card in cards:
        path = (root / card["path"]).resolve() if root and card.get("path") else None
        if path and path.is_relative_to(root) and path.is_file():
            card["mtime"] = path.stat().st_mtime
            if views is None:
                card["body"] = ui.card_body(path, attachments)
        else:
            card["body"] = "Файл карточки недоступен."
    lanes = {record["key"]: ui.lanes_for(record["cards"]) for record in records}
    numbers = count(1)
    dialogs = []

    def counters(members):
        cells = []
        for lane, label in zip(ui.LANES, LANE_LABELS):
            items = [card for member in members for card in lanes[member["key"]][lane]]
            cells.append(ui.status_count(items, f"counter c-{lane}", label))
        return '<span class="counters">' + "".join(cells) + "</span>"

    def row(record, tone, parent=False):
        key = escape(record["key"])
        expanded = record["key"] == current
        branch_hint = ' aria-current="true" aria-description="Текущая ветка"' if record["key"] == branch_key else ''
        own = lanes[record["key"]]
        content = ""
        if parent:
            content = f'<h2 class="own">Собственные задачи портфеля · {len(record["cards"])}</h2>'
        if record["cards"]:
            columns = ui.columns(own, numbers, open_ids, open_anywhere, prefix=record["key"] + "-")
            content += f'<div class="board">{columns}</div>'
        elif not parent:
            content = '<p class="empty">Нет локальных карточек</p>'
        if views is None:
            dialogs.append(issue_dialog(record))
            dialogs.extend(ui.view(card) for card in record["cards"])
        else:
            views["issue-" + record["key"]] = record
            views.update(("view-" + card["id"], card) for card in record["cards"])
        return (f'<details class="ticket {tone}" data-key="{key}"{" open" if expanded else ""}>'
                f'<summary class="ticket-head"{branch_hint}><span class="ticket-name">{ui.copy_key(record["key"], "key")}'
                f'<button class="issue-title" type="button" data-view="issue-{key}">{escape(record["title"])}</button>'
                f'</span>{counters(records if parent else [record])}'
                f'<span class="state">{escape(record["status"])}</span><span class="arrow"></span></summary>'
                f'<div class="ticket-body">{content}</div></details>')

    aliases = snapshot.get("status_aliases", {})
    groups = {}
    for issue in issues:
        raw = issue["status"]
        status = aliases.get(raw.strip().casefold(), raw.strip().casefold())
        label, tone, order = GROUPS.get(status, (raw, "neutral", 2))
        groups.setdefault((order, label, tone), []).append(issue)

    legend = "".join(f'<span class="legend-item c-{lane}">{label}</span>'
                     for lane, label in zip(ui.LANES, LANE_LABELS))
    stamp = snapshot.get("jira_updated_at", "")
    if stamp:
        try:
            stamp = datetime.fromisoformat(stamp).strftime("%d.%m.%Y · %H:%M %z")
        except ValueError:
            pass
        stamp = f'<span class="stamp">Снимок Jira · {escape(stamp)}</span>'
    body = (f'<div class="toolbar"><div class="board-info">'
            f'<div class="legend" aria-label="Статусы карточек">{legend}</div>{stamp}</div>'
            '<details class="comment-help"><summary id="general-comment" aria-label="Общий комментарий" '
            'title="Общий комментарий">💬</summary>'
            '<span>В режиме Annotate нажми на 💬, чтобы оставить комментарий ко всей доске.</span>'
            '</details></div>' + row(portfolio, "parent", parent=True))
    if snapshot.get("notice"):
        body += f'<aside>{escape(snapshot["notice"])}</aside>'
    for (_, label, tone), items in sorted(groups.items()):
        expanded = any(i["key"] == current for i in items)
        rows = "".join(row(i, tone) for i in items)
        body += (f'<details class="bucket {tone}" data-key="{escape(label)}"{" open" if expanded else ""}><summary class="bucket-head">'
                 f'<span class="bucket-label"><span class="dot"></span>{escape(label)} '
                 f'<span class="count">{len(items)}</span></span>{counters(items)}'
                 f'<span class="arrow"></span></summary><div class="tickets">{rows}</div></details>')
    css = Path(__file__).with_suffix(".css").read_text(encoding="utf-8")
    title = escape(f'{portfolio["key"]} · {portfolio["title"]}')
    page = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="plannotator-theme" content="host">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>{ui.style()}\n{css}\n{ui.hover_rules(open_ids, cards)}</style></head><body>
<main class="layout"><div class="portfolio">{body}</div>{"".join(dialogs)}</main>
{ui.SCRIPT}</body></html>"""
    if views is not None:
        return page
    output.write_text(page, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Сводная доска портфеля и его тикетов")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("legacy_output", type=Path, nargs="?", help="старый вызов: TASKS SNAPSHOT OUTPUT")
    parser.add_argument("--prs", type=Path, help="проверенные PR по ключу тикета")
    parser.add_argument("--current", help="тикет для раскрытия, если ключ ветки отсутствует в портфеле")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from collect import board_snapshot
    path = args.output if args.legacy_output else args.snapshot
    output = args.legacy_output or args.output
    try:
        snapshot, branch_key = board_snapshot(path, args.snapshot.expanduser() if args.legacy_output else None, args.prs)
    except ValueError as error:
        parser.error(str(error))
    render(snapshot, output, branch_key or args.current, branch_key)


if __name__ == "__main__":
    main()
