"""Общая отрисовка карточек для todo и portfolio."""
import hashlib
import html
from pathlib import Path
import re
import shutil
from urllib.parse import quote
import zlib

score = {"low": 1, "medium": 2, "high": 3}
grade = {"effort": {"low": "good", "medium": "mid", "high": "bad"},
         "impact": {"low": "bad", "medium": "mid", "high": "good"}}
LANES = ("open", "in-progress", "waiting", "closed")
labels = {"user": "От тебя", "agent": "Агент"}
CLOSE_BUTTON = '<button class="close" type="button" aria-label="Закрыть">×</button>'


class Attachments:
    def __init__(self, output, tasks_root):
        self.directory = output.parent / "board-assets"
        self.root = tasks_root.resolve()
        self.copied = {}

    def url(self, path):
        source = path.resolve()
        if not source.is_relative_to(self.root) or not source.is_file():
            return ""
        if source not in self.copied:
            name = source.name
            digest = hashlib.sha256(str(source.relative_to(self.root)).encode()).hexdigest()[:12]
            target = self.directory / (digest + "_" + name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            self.copied[source] = "board-assets/" + digest + "_" + quote(name)
        return self.copied[source]


def attach_body(body, parent, attachments):
    return re.sub(r"(!\[[^\]]*\]\()([^)]+)\)", lambda m: m[1] + attachments.url(parent / m[2]) + ")", body)


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


def card(t, open_ids, open_anywhere):
    e = html.escape
    title = re.sub(r"`([^`]+)`", r"<code>\1</code>", e(t["title"]))
    rows = [f'<div class="top"><span class="ref"><span class="n">[{t["n"]}]</span>'
            f'<span class="id" title="Нажми, чтобы скопировать" '
            f'onclick="navigator.clipboard.writeText(this.textContent)">{e(t["id"])}</span></span>'
            f'<span class="type tinted {e(t.get("type", ""))}">{e(t.get("type", "?"))}</span></div>',
            f'<button type="button" class="title" data-view="view-{e(t["id"])}">{title}</button>']
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


def view(t, opened=None):
    title = re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(t["title"]))
    return (f'<dialog class="view" id="view-{html.escape(t["id"])}"{" open" if t["id"] == opened else ""}>'
            f'<div class="sheet">{CLOSE_BUTTON}'
            f'<h2><span class="n">[{t["n"]}]</span> {title}</h2>{markdown(t["body"])}</div></dialog>')


def lane(t):
    if t.get("status") in ("done", "dropped"):
        return "closed"
    return "waiting" if blocker(t)[0] not in ("", *labels) else t.get("status")


def lanes_for(tasks):
    lanes = {key: [] for key in LANES}
    for t in tasks:
        effort, impact = score.get(t.get("effort")), score.get(t.get("impact"))
        t["value"] = impact - effort if effort and impact else None
        lanes[lane(t)].append(t)
    for key, items in lanes.items():
        if key == "closed":
            items.sort(key=lambda t: -t.get("mtime", 0))
        else:
            items.sort(key=lambda t: (-(t["value"] if t["value"] is not None else -9),
                                      score.get(t.get("effort"), 9), t["id"]))
    return lanes


def columns(lanes, numbers, open_ids, open_anywhere, prefix=""):
    sections = []
    for title, items in lanes.items():
        for t in items:
            t["n"] = next(numbers)
        fold_id = html.escape(f"fold-{prefix}{title}")
        checked = " checked" if title == "closed" else ""
        cards = "".join(card(t, open_ids, open_anywhere) for t in items)
        sections.append(f'<section class="column"><input type="checkbox" class="fold" id="{fold_id}"{checked}>'
                        f'<label class="head" for="{fold_id}"><h2>{title} <span class="count">{len(items)}</span></h2></label>'
                        f'<div class="cards">{cards}</div></section>')
    return "".join(sections)


def style():
    return Path(__file__).with_suffix(".css").read_text(encoding="utf-8")


def hover_rules(open_ids, tasks):
    return "\n".join(
        f'.board:has(a.dep[href="#{i}"]:hover) [id="{i}"] {{ outline: 2px solid var(--ring); outline-offset: 2px; }}'
        for i in sorted(open_ids)) + "\n" + "\n".join(
        f'.layout:has([id="view-{t["id"]}"][open]) [id="{t["id"]}"] {{ border-color: var(--ring); }}'
        for t in tasks)


SCRIPT = """<script>
let opener;
function closeViews() { document.querySelectorAll(".view[open]").forEach(d => d.close()); }
document.addEventListener("click", e => {
    const close = e.target.closest(".view .close");
    if (close) { close.closest("dialog").close(); return; }
    const dep = e.target.closest("a.dep");
    if (dep && dep.hash) {
        const card = document.getElementById(decodeURIComponent(dep.hash.slice(1)));
        if (card) {
            for (let node = card.parentElement; node; node = node.parentElement) {
                if (node.tagName === "DETAILS") node.open = true;
                if (node.classList.contains("column")) node.querySelector(".fold").checked = false;
            }
        }
    }
    const trigger = e.target.closest("[data-view]");
    if (trigger) {
        closeViews();
        const panel = document.getElementById(trigger.dataset.view);
        if (panel) { opener = trigger; panel.show(); panel.querySelector(".close").focus({preventScroll:true}); }
    }
});
document.addEventListener("close", e => { if (e.target.matches(".view") && !document.querySelector(".view[open]")) opener?.focus({preventScroll:true}); }, true);
document.addEventListener("keydown", e => { if (e.key === "Escape") closeViews(); });
</script>"""
