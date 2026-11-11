from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timedelta
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "portfolio"))
import collect


class PortfolioTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.tasks = self.root / "tasks"
        self.group = self.tasks / "feature-APP-1"
        self.group.mkdir(parents=True)
        self.card = self.group / "2026-01-01-decision.md"
        self.card.write_text("---\nstatus: open\n---\n# Исходный вопрос\n")
        self.path = self.root / "PLAN-1.json"
        self.args = SimpleNamespace(key="PLAN-1", via=None, child_project="APP", jira_url=None, refresh=False)
        def jira(key, selection):
            return ({"key": key, "status": "open", "title": "Портфель", "description": "Цель"},
                    [{"key": "APP-1", "status": "open", "title": "Экран", "description": None}])
        mock = patch.object(collect, "jira_issues", side_effect=jira)
        self.addCleanup(mock.stop)
        self.fetch = mock.start()

    def snapshot(self):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            collect.update(self.args, self.path, self.tasks, {})
        return json.loads(self.path.read_text())

    def test_cache_reads_current_local_files_and_refreshes_on_completion(self):
        self.snapshot()
        self.card.write_text("---\nstatus: in-progress\nnext: design: ответ\n---\n# Новый вопрос\n")
        card = self.snapshot()["issues"][0]["cards"][0]
        self.assertEqual((card["title"], card["next"]), ("Новый вопрос", "design: ответ"))
        self.assertEqual(self.fetch.call_count, 1)
        archived = self.tasks / "Done" / self.group.name
        archived.parent.mkdir()
        self.group.rename(archived)
        (archived / self.card.name).write_text("---\nstatus: done\nresolution: согласовано\n---\n# Вопрос\n")
        card = self.snapshot()["issues"][0]["cards"][0]
        self.assertEqual(card["resolution"], "согласовано")
        self.assertEqual(card["path"], str((archived / self.card.name).relative_to(self.tasks)))
        self.snapshot()
        self.assertEqual(self.fetch.call_count, 2)

    def test_first_use_next_day_and_explicit_refresh(self):
        state = self.snapshot()
        state["jira_updated_at"] = (datetime.now().astimezone() - timedelta(days=1)).isoformat()
        self.path.write_text(json.dumps(state))
        self.snapshot()
        self.snapshot()
        self.assertEqual(self.fetch.call_count, 2)
        self.args.refresh = True
        self.snapshot()
        self.assertEqual(self.fetch.call_count, 3)

    def test_snapshot_from_before_descriptions_refreshes_once(self):
        state = self.snapshot()
        for issue in [state["portfolio"], *state["issues"]]:
            del issue["description"]
        self.path.write_text(json.dumps(state))
        self.assertEqual(self.snapshot()["portfolio"]["description"], "Цель")
        self.assertIsNone(self.snapshot()["issues"][0]["description"])
        self.assertEqual(self.fetch.call_count, 2)

    def test_unavailable_jira_keeps_last_success_and_retries(self):
        old = self.snapshot()
        fetch = self.fetch.side_effect
        self.fetch.side_effect = TimeoutError("offline")
        self.args.refresh = True
        stale = self.snapshot()
        self.assertEqual(stale["jira_updated_at"], old["jira_updated_at"])
        self.assertTrue(stale["jira_stale"])
        self.assertEqual(stale["issues"], old["issues"])
        self.args.refresh = False
        self.assertTrue(self.snapshot()["jira_stale"])
        self.assertEqual(self.fetch.call_count, 2)
        stale["jira_failed_at"] = (datetime.now().astimezone() - timedelta(minutes=11)).isoformat()
        self.path.write_text(json.dumps(stale))
        self.fetch.side_effect = fetch
        self.assertFalse(self.snapshot()["jira_stale"])
        self.assertEqual(self.fetch.call_count, 3)

    def test_failed_cold_start_or_new_selection_preserves_existing_file(self):
        with patch.object(collect, "jira_issues", side_effect=TimeoutError), self.assertRaises(TimeoutError):
            self.snapshot()
        self.assertFalse(self.path.exists())
        old = self.snapshot()
        self.args.via = ["PLAT-2"]
        with patch.object(collect, "jira_issues", side_effect=TimeoutError), self.assertRaises(TimeoutError):
            self.snapshot()
        self.assertEqual(json.loads(self.path.read_text()), old)


class JiraLinksTests(unittest.TestCase):
    def test_inclusions_respect_direction_project_and_platform(self):
        def issue(key):
            return {"key": key, "fields": {"summary": key, "status": {"name": "Open"}}}
        def includes(key):
            return {"type": {"outward": "includes"}, "outwardIssue": issue(key)}
        root, platform = issue("PLAN-1"), issue("PLAT-2")
        root["fields"]["issuelinks"] = [includes("APP-1"), includes("PLAT-2"), includes("OTHER-9"),
                                        {"type": {"outward": "blocks"}, "outwardIssue": issue("APP-9")},
                                        {"type": {"outward": "includes"}, "inwardIssue": issue("APP-8")}]
        platform["fields"]["issuelinks"] = [includes("APP-1"), includes("APP-2")]
        options = {"via": ["PLAT-2"], "child_project": "APP", "jira_url": None}
        portfolio, issues = collect.select_issues({i["key"]: i for i in [root, platform]}, "PLAN-1", options)
        self.assertEqual(portfolio["other_inclusions"], {"OTHER-9": "OTHER-9"})
        self.assertEqual([i["key"] for i in issues], ["APP-1", "APP-2"])
