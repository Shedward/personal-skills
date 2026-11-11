import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCAN = Path(__file__).resolve().parents[1] / "scripts" / "scan_group.py"


class ScanGroupTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def card(self, path, status="open", fields=""):
        path = self.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\nstatus: {status}\neffort: low\nimpact: high\n{fields}---\n# {path.stem}\n")
        return path

    def scan(self, *args):
        return json.loads(subprocess.check_output(
            [sys.executable, "-IB", str(SCAN), "MOB-1", "--tasks", str(self.root), *args], text=True))

    def test_live_assignment_is_not_dispatched_twice_and_does_not_mask_handoff(self):
        self.card("group-MOB-1/active.md", "in-progress", "next: agent: проверить\nworker: checker\n")
        self.card("group-MOB-1/ready.md")
        unconfirmed = self.scan()
        self.assertEqual([c["id"] for c in unconfirmed["review"]], ["active"])
        self.assertEqual([c["id"] for c in unconfirmed["candidates"]], ["ready"])
        report = self.scan("--running", "active")
        self.assertEqual([c["id"] for c in report["running"]], ["active"])
        self.assertEqual([c["id"] for c in report["candidates"]], ["ready"])
        self.card("group-MOB-1/active.md", "in-progress", "next: user: посмотреть дифф\nworker: checker\n")
        report = self.scan("--running", "active")
        self.assertEqual(report["running"], [])
        self.assertEqual([c["id"] for c in report["waiting"]], ["active"])

    def test_move_and_archive_change_scope_and_readiness(self):
        source = self.card("screen-MOB-1/source.md")
        self.card("screen-MOB-1/use.md", fields="depends-on:\n  - source\n")
        self.card("screen-MOB-10/another.md")
        self.card("Done/Resources/source.md")
        self.assertEqual([c["id"] for c in self.scan()["candidates"]], ["source"])

        source.rename(self.root / "source.md")
        report = self.scan()
        self.assertEqual(report["total"], 1)
        self.assertEqual(report["candidates"], [])
        self.assertEqual(report["waiting"][0]["dependencies"][0]["path"], "source.md")

        (self.root / "source.md").rename(self.root / "Done" / "source.md")
        self.card("Done/source.md", "done", "resolution: принято\n")
        self.assertEqual([c["id"] for c in self.scan()["candidates"]], ["use"])

    def test_uncertain_dependencies_and_next_actor(self):
        self.card("Done/older-MOB-2/choice.md", "dropped", "resolution: решили отложить\n")
        self.card("group-MOB-1/follow.md", fields="depends-on: [choice, missing, duplicate]\n")
        self.card("duplicate.md")
        self.card("other-MOB-2/duplicate.md", "done")
        self.card("group-MOB-1/resume.md", "in-progress", "next: agent: собрать пример\n")
        self.card("group-MOB-1/ask.md", "in-progress", 'next: "user: выбрать вариант"\n')
        self.card("group-MOB-1/design.md", "in-progress", 'next: "design: дать макет"\n')
        report = self.scan()
        self.assertEqual([c["id"] for c in report["candidates"]], ["resume"])
        self.assertEqual([c["id"] for c in report["waiting"]], ["ask", "design"])
        self.assertEqual([d["status"] for d in report["review"][0]["dependencies"]],
                         ["dropped", "missing", "ambiguous"])


if __name__ == "__main__":
    unittest.main()
