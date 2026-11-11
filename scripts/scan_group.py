"""Разобрать карточки одной активной группы todo. Печатает JSON, работает только на чтение."""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "todo"))
from todo_cards import CLOSED, active_worker, blocker, read_card, score


def dependency_info(dep, paths, root):
    if len(paths) != 1:
        return {"id": dep, "status": "ambiguous" if paths else "missing",
                "paths": sorted(str(p.relative_to(root)) for p in paths)}
    card = read_card(paths[0], root)
    return {k: card[k] for k in ("id", "path", "status", "next", "resolution") if k in card}


def classify(card, dependencies):
    status = card["status"]
    actor, step = blocker(card)
    if status not in ("open", "in-progress") or (status == "open" and actor):
        return "review", "Проверить сочетание status и next."
    if actor and not step:
        return "review", "В next указан неполный следующий шаг."
    if actor == "user":
        return "waiting", f"Нужен ответ разработчика: {step}."
    if actor and actor != "agent":
        return "waiting", f"Ждём {actor}: {step}."

    unclear = [d for d in dependencies if d["status"] not in ("done", "open", "in-progress")]
    if unclear:
        return "review", "Уточнить результат зависимости: " + ", ".join(
            f"{d['id']} ({d['status']})" for d in unclear)
    pending = [d["id"] for d in dependencies if d["status"] != "done"]
    if pending:
        if status == "in-progress":
            return "review", "Проверить, можно ли продолжить текущий шаг независимо от " + ", ".join(pending)
        return "waiting", "Нужен результат: " + ", ".join(pending)
    if card.get("impact") not in score or card.get("effort") not in score:
        return "review", "Оценить effort и impact перед отбором."
    if status == "in-progress":
        reason = f"Следующий шаг агента: {step}" if step else "Уже в работе, следующий ход за агентом."
    else:
        reason = "Открыта, все зависимости закрыты." if dependencies else "Открыта, зависимостей нет."
    if dependencies:
        reason += " Перед выдачей сверить доступность результата зависимостей."
    return "candidates", reason


def scan(root, key, running=()):
    folders = sorted(p for p in root.iterdir() if p.is_dir() and p.name.casefold() != "resources")
    groups = [p for p in folders if p.name.casefold() != "done"]
    matches = [g for g in groups if g.name == key or g.name.endswith("-" + key)]
    if len(matches) != 1:
        names = ", ".join(g.name for g in matches) or "нет совпадений"
        raise ValueError(f"Нужна одна активная группа для {key!r}: {names}")
    group = matches[0]

    paths = defaultdict(list)
    locations = [root, *folders]
    for archive in (p for p in folders if p.name.casefold() == "done"):
        locations.extend(p for p in archive.iterdir() if p.is_dir() and p.name.casefold() != "resources")
    for directory in locations:
        for path in directory.glob("*.md"):
            paths[path.stem].append(path)

    rows = {"candidates": [], "running": [], "waiting": [], "review": []}
    closed = 0
    for path in sorted(group.glob("*.md")):
        card = read_card(path, root)
        if card["status"] in CLOSED:
            closed += 1
            continue
        deps = [dependency_info(dep, paths[dep], root) for dep in card.pop("depends-on", [])]
        bucket, reason = classify(card, deps)
        if len(paths[card["id"]]) > 1:
            bucket, reason = "review", "Один ID встречается у нескольких карточек проекта."
        elif bucket == "candidates" and card["id"] in running:
            bucket, reason = "running", "На этот шаг уже выдано живое поручение."
        elif bucket == "candidates" and (worker := active_worker(card)):
            bucket, reason = "review", f"Сверить живое поручение {worker} перед повторной выдачей."
        rows[bucket].append({**card, "dependencies": deps, "reason": reason})

    def priority(card):
        effort = score[card["effort"]]
        return (effort - score[card["impact"]], effort, card["id"])

    rows["candidates"].sort(key=priority)
    return {"group": group.name, "tasks_root": str(root), "total": closed + sum(map(len, rows.values())),
            "closed": closed, **rows}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("group", help="полное имя группы или ключ тикета")
    cli.add_argument("--tasks", required=True, type=Path, help="корень локальных карточек todo")
    cli.add_argument("--running", action="append", default=[], metavar="ID",
                     help="ID карточки с живым исполнителем на текущем шаге; можно повторять")
    args = cli.parse_args()
    try:
        report = scan(args.tasks.expanduser().resolve(), args.group, set(args.running))
    except (ValueError, OSError) as error:
        cli.exit(1, f"{error}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
