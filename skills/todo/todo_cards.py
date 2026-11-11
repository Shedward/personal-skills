CLOSED = {"done", "dropped"}
score = {"low": 1, "medium": 2, "high": 3}


def group_dirs(root):
    return sorted(d for d in root.iterdir() if d.is_dir() and d.name.casefold() not in {"done", "resources"})


def blocker(card):
    value = str(card.get("next") or "").strip()
    if value[:1] in {"'", '"'} and value[-1] == value[0]:
        value = value[1:-1]
    actor, _, step = value.partition(":")
    return actor.strip(), step.strip()


def active_worker(card):
    if card.get("status") == "in-progress" and blocker(card)[0] in ("", "agent"):
        return str(card.get("worker") or "").strip().strip("\"'").strip()
    return ""


def read_card(path, tasks):
    if not path.resolve().is_relative_to(tasks.resolve()):
        raise ValueError(f"Карточка вне папки задач: {path}")
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
            elif name in {"type", "status", "next", "worker", "resolution", "effort", "impact"}:
                card[name] = value.strip().strip("\"'")
        else:
            raise ValueError(f"Не закрыт frontmatter: {path}")
        card["title"] = next((line[2:].strip() for line in stream if line.startswith("# ")), path.stem)
    if not card.get("status"):
        raise ValueError(f"Нет статуса карточки: {path}")
    return card
