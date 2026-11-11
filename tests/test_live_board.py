import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills"))
from todo.live_board import LiveBoard


class LiveBoardTest(unittest.TestCase):
    def test_archived_group_keeps_card_details_and_frontmatter_out_of_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            group = root / "Done" / "feature-MOB-1"
            group.mkdir(parents=True)
            (group / "item.md").write_text("---\nstatus: done\nresolution: итог --- принят\n---\n# Задача\nОписание")
            board = LiveBoard(root, group="Done/feature-MOB-1")
            self.assertIn('data-view="view-item"', board.page())
            detail = board.detail("view-item")
            self.assertIn("Описание", detail)
            self.assertNotIn("принят", detail)

    def test_portfolio_reads_markdown_instead_of_cached_cards_and_loads_detail_on_demand(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            groups = [root / k for k in ("MOB-1", "MOB-2")]
            for g in groups:
                g.mkdir()
            card = groups[0] / "item.md"
            card.write_text("---\nstatus: open\n---\n# Проверка\nПервое описание")
            snapshot = root / "p.json"
            records = [{"key": key, "title": key, "status": "Open", "description": "Текст из Jira",
                        "cards": [{"id": "old-cache"}]} for key in ("RDS-1", "MOB-1", "MOB-2")]
            snapshot.write_text(json.dumps({"portfolio": records[0], "issues": records[1:]}))
            board = LiveBoard(root, snapshot)
            page = board.page()
            self.assertNotIn("Первое описание", page)
            self.assertNotIn("Текст из Jira", page)
            self.assertNotIn("old-cache", page)
            self.assertIn("Текст из Jira", board.detail("issue-MOB-1"))
            group = LiveBoard(root, group=groups[0].name)
            self.assertNotIn("Первое описание", group.page())
            card.write_text("---\nstatus: open\n---\n# Проверка\nНовое описание")
            self.assertIn("Новое описание", group.detail("view-item"))
            card.rename(groups[1] / card.name)
            group.page()
            self.assertIsNone(group.detail("view-item"))
            board.page()
            self.assertIn("Новое описание", board.detail("view-item"))
            backlog = LiveBoard(root)
            self.assertIn("MOB-2", backlog.page())
            self.assertIsNone(backlog.detail("view-item"))
