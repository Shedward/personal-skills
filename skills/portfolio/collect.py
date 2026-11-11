"""Собрать снимок портфеля из Jira MCP и локальных карточек todo."""

import argparse
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


CLOSED = {"done", "dropped"}


def read_card(path, tasks):
    card = {"id": path.stem, "path": str(path.relative_to(tasks))}
    with path.open(encoding="utf-8-sig") as stream:
        if next(stream, "").strip() != "---":
            raise ValueError(f"Отсутствует frontmatter: {path}")
        name = ""
        for line in stream:
            value = line.strip()
            if value == "---":
                break
            if name == "depends-on" and value.startswith("- "):
                card[name].append(value[2:].strip().strip("\"'"))
                continue
            name, _, value = line.partition(":")
            if name == "depends-on":
                card[name] = [item.strip().strip("\"'") for item in
                              value.strip().strip("[]").split(",") if item.strip()]
            elif name in {"type", "status", "next", "resolution", "effort", "impact"}:
                card[name] = value.strip().strip("\"'")
        else:
            raise ValueError(f"Не закрыт frontmatter: {path}")
        card["title"] = next((line[2:].strip() for line in stream if line.startswith("# ")), path.stem)
    if not card.get("status"):
        raise ValueError(f"Нет статуса карточки: {path}")
    return card


def local_cards(tasks, keys):
    cards = {key: [] for key in keys}
    if tasks.exists():
        groups = []
        for entry in tasks.iterdir():
            if entry.is_dir() and entry.name.casefold() == "done":
                groups.extend(path for path in entry.iterdir() if path.is_dir())
            elif entry.is_dir() and entry.name.casefold() != "resources":
                groups.append(entry)
        for group in sorted(groups):
            for key in cards:
                if group.name == key or group.name.endswith("-" + key):
                    cards[key].extend(read_card(path, tasks) for path in sorted(group.glob("*.md")))
    return cards


def issue_record(raw, jira_url):
    fields = raw["fields"]
    status = fields["status"]
    key = raw["key"]
    record = {"key": key, "title": fields["summary"], "description": fields.get("description"),
              "status": status["name"] if isinstance(status, dict) else status}
    if jira_url:
        record["url"] = f"{jira_url.rstrip('/')}/browse/{key}"
    return record


def select_issues(parents, key, selection):
    portfolio = issue_record(parents[key], selection["jira_url"])
    issues = {}
    children = set()
    for parent_key in [key, *selection["via"]]:
        if parent_key != key and parent_key not in children:
            raise ValueError(f"{parent_key} не входит в {key} по связи includes")
        for link in parents[parent_key]["fields"]["issuelinks"]:
            if not link.get("outwardIssue") or link["type"]["outward"].casefold() != "includes":
                continue
            child = link["outwardIssue"]
            child_key = child["key"]
            children.add(child_key)
            if child_key in selection["via"] or child_key == key:
                continue
            if selection["child_project"] and child_key.split("-", 1)[0] != selection["child_project"]:
                if parent_key == key:
                    portfolio.setdefault("other_inclusions", {})[child_key] = child["fields"]["summary"]
                continue
            issues[child_key] = issue_record(child, selection["jira_url"])
    return portfolio, [issues[k] for k in sorted(issues)]


def jira_issues(key, selection):
    command = ["uv", "run", "--script", str(Path(__file__).with_name("jira.py")), key, *selection["via"]]
    if selection["child_project"]:
        command.extend(["--child-project", selection["child_project"]])
    if selection["jira_url"]:
        command.extend(["--jira-url", selection["jira_url"]])
    proc = subprocess.run(command, stdout=subprocess.PIPE, text=True, timeout=120)
    if proc.returncode:
        raise ValueError(f"Jira MCP завершился с кодом {proc.returncode}")
    result = json.loads(proc.stdout)
    return result["portfolio"], result["issues"]


def git_value(*args):
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def update(args, path, tasks, defaults):
    cached = json.loads(path.read_text()) if path.exists() else {}
    if cached and cached["portfolio"]["key"] != args.key:
        raise ValueError(f"Снимок {path} принадлежит другому портфелю")
    selection = {"via": [], "child_project": defaults.get("child_project"), "jira_url": defaults.get("jira_url")}
    selection.update(cached.get("selection", {}))
    for name in ("via", "child_project", "jira_url"):
        if getattr(args, name) is not None:
            selection[name] = getattr(args, name)
    compatible = bool(cached) and selection == cached["selection"]
    now = datetime.now().astimezone()
    records = [cached["portfolio"], *cached["issues"]] if compatible else []
    cards = local_cards(tasks, [r["key"] for r in records])
    old_closed = {c["id"] for r in records for c in r["cards"] if c["status"] in CLOSED}
    closed = any(c["status"] in CLOSED and c["id"] not in old_closed for group in cards.values() for c in group)
    refreshed_at = cached.get("jira_updated_at")
    today = compatible and datetime.fromisoformat(refreshed_at).astimezone().date() == now.date()
    failed_at = datetime.fromisoformat(cached["jira_failed_at"]) if compatible and cached.get("jira_failed_at") else None
    recent_failure = (failed_at and failed_at.astimezone().date() == now.date()
                      and 0 <= (now - failed_at).total_seconds() < 600)
    need_descriptions = any("description" not in record for record in records)
    refresh = args.refresh or closed or ((not today or failed_at or need_descriptions) and not recent_failure)
    if refresh:
        try:
            portfolio, issues = jira_issues(args.key, selection)
        except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
            if not compatible:
                raise
            print(f"Обновление Jira не удалось: {error}", file=sys.stderr)
            failed_at = now
        else:
            failed_at = None
            records = [portfolio, *issues]
            if set(cards) != {r["key"] for r in records}:
                cards = local_cards(tasks, [r["key"] for r in records])
            refreshed_at = now.isoformat(timespec="seconds")
    for record in records:
        record["cards"] = cards[record["key"]]
    snapshot = {"portfolio": records[0], "issues": records[1:], "tasks_root": str(tasks),
                "selection": selection, "jira_updated_at": refreshed_at, "jira_stale": bool(failed_at),
                "local_updated_at": now.isoformat(timespec="seconds")}
    if defaults.get("status_aliases"):
        snapshot["status_aliases"] = defaults["status_aliases"]
    if failed_at:
        snapshot["jira_failed_at"] = failed_at.isoformat(timespec="seconds")
        snapshot["notice"] = f"Jira недоступна. Статусы Jira на {refreshed_at}; локальные карточки обновлены."
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        try:
            json.dump(snapshot, tmp, ensure_ascii=False, indent=2)
            tmp.write("\n")
        except BaseException:
            tmp_path.unlink()
            raise
    os.replace(tmp_path, path)
    source = "предыдущий снимок" if failed_at else "MCP" if refresh else "кеш"
    print(f"{path} · Jira: {source} ({refreshed_at}) · тикетов: {len(records)-1}"
          f" · карточек: {sum(map(len, cards.values()))}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("key", help="ключ портфеля в Jira")
    parser.add_argument("--project", help="каноническое имя проекта (по умолчанию из origin)")
    parser.add_argument("--tasks", type=Path, help="папка todo")
    parser.add_argument("--cache-dir", type=Path, help="каталог снимков")
    parser.add_argument("--child-project", help="включать дочерние тикеты этого проекта Jira")
    parser.add_argument("--via", nargs="*", help="также пройти через перечисленные дочерние тикеты")
    parser.add_argument("--jira-url", help="корень Jira для ссылок на тикеты")
    parser.add_argument("--refresh", action="store_true", help="обновить Jira сейчас")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*-\d+", args.key):
        parser.error("Нужен ключ портфеля вида PLAN-42")
    repo = Path(git_value("rev-parse", "--show-toplevel") or Path.cwd())
    remote = git_value("remote", "get-url", "origin").rstrip("/").removesuffix(".git")
    project = args.project or re.split("[/:]", remote)[-1] or repo.name
    if project in {".", ".."} or not project or "/" in project:
        parser.error("Некорректное имя проекта")
    docs = Path.home() / ".claude" / "docs" / project
    tasks = (args.tasks or next((p for p in [repo / "tasks", repo / "Tasks"] if p.is_dir()),
                                docs / "tasks")).expanduser().resolve()
    if args.tasks and not tasks.is_dir():
        parser.error(f"Папка todo не найдена: {tasks}")
    directory = (args.cache_dir or docs / "portfolios").expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{args.key}.json"
    config = docs / "portfolios" / "config.json"
    defaults = json.loads(config.read_text()) if config.is_file() else {}
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        update(args, path, tasks, defaults)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        sys.exit(f"Не удалось собрать портфель: {error}")
