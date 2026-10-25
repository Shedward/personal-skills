import os
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="personal skills ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo with spaces"
        (self.repo / ".git").mkdir(parents=True)
        for name in ("skills-sync", "alpha", "zeta"):
            folder = self.repo / "skills" / name
            folder.mkdir(parents=True)
            (folder / "SKILL.md").write_text(name)
        self.dest = self.root / "codex skills"
        self.env = dict(os.environ, PERSONAL_SKILLS_CODEX_DIR=str(self.dest))

    def run_install(self, *args):
        return subprocess.run(
            ["sh", str(REPO / "install.sh"), *args, str(self.repo)],
            env=self.env, text=True, capture_output=True,
        )

    def test_links_repeat_and_new_skill(self):
        self.assertEqual(self.run_install("--codex").returncode, 0)
        self.assertEqual(self.run_install("--codex").returncode, 0)
        for source in (self.repo / "skills").iterdir():
            self.assertEqual((self.dest / source.name).resolve(), source)
        (self.dest / "alpha" / "SKILL.md").write_text("edited through link")
        self.assertEqual((self.repo / "skills/alpha/SKILL.md").read_text(), "edited through link")
        new = self.repo / "skills/new"
        new.mkdir()
        (new / "SKILL.md").touch()
        self.assertEqual(self.run_install("--codex").returncode, 0)
        self.assertEqual((self.dest / "new").resolve(), new)

    def test_conflicts_preserve_all_destinations(self):
        for kind in ("directory", "file", "foreign-link", "broken-link"):
            with self.subTest(kind=kind):
                self.dest = self.root / kind
                self.env["PERSONAL_SKILLS_CODEX_DIR"] = str(self.dest)
                self.dest.mkdir()
                conflict = self.dest / "zeta"
                if kind == "directory":
                    conflict.mkdir()
                    (conflict / "original").write_text("keep")
                elif kind == "file":
                    conflict.write_text("keep")
                else:
                    conflict.symlink_to(self.repo if kind == "foreign-link" else self.root / "missing")
                before = list(self.dest.iterdir())
                result = self.run_install("--codex")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Conflict", result.stderr)
                self.assertEqual(list(self.dest.iterdir()), before)
                if kind == "directory":
                    self.assertEqual((conflict / "original").read_text(), "keep")
                elif kind == "file":
                    self.assertEqual(conflict.read_text(), "keep")

    def mock_claude(self, listing="[]", list_status=0):
        binary = self.root / "bin"
        binary.mkdir()
        log = self.root / "claude.log"
        mock = binary / "claude"
        mock.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$PERSONAL_SKILLS_TEST_LOG"\n'
                        'if [ "$*" = "plugin marketplace list --json" ]; then\n'
                        '  printf "%s\\n" "$PERSONAL_SKILLS_TEST_LIST"\n'
                        '  exit "$PERSONAL_SKILLS_TEST_STATUS"\nfi\n')
        mock.chmod(0o755)
        self.env.update(PATH=f"{binary}:{os.environ['PATH']}", PERSONAL_SKILLS_TEST_LOG=str(log),
                        PERSONAL_SKILLS_TEST_LIST=listing, PERSONAL_SKILLS_TEST_STATUS=str(list_status))
        return log

    def test_claude_modes_use_cli(self):
        log = self.mock_claude()
        self.assertEqual(self.run_install("--claude").returncode, 0)
        self.assertFalse(self.dest.exists())
        self.assertIn("plugin install my@personal-skills", log.read_text())
        self.assertIn("plugin update my@personal-skills", log.read_text())
        self.assertEqual(self.run_install("--both").returncode, 0)
        self.assertTrue((self.dest / "alpha").is_symlink())

    def test_registered_marketplace_is_not_added_again(self):
        log = self.mock_claude(json.dumps([
            {"name": "personal-skills", "installLocation": str(self.repo)}
        ]))
        self.assertEqual(self.run_install("--both").returncode, 0)
        self.assertNotIn("plugin marketplace add", log.read_text())
        self.assertIn("plugin update my@personal-skills", log.read_text())

    def test_marketplace_list_failure_stops_before_mutations(self):
        log = self.mock_claude(list_status=1)
        self.assertNotEqual(self.run_install("--both").returncode, 0)
        self.assertFalse(self.dest.exists())
        self.assertEqual(log.read_text().splitlines(), ["plugin marketplace list --json"])

    def test_invalid_marketplace_list_stops_before_mutations(self):
        log = self.mock_claude("invalid JSON")
        self.assertNotEqual(self.run_install("--both").returncode, 0)
        self.assertFalse(self.dest.exists())
        self.assertEqual(log.read_text().splitlines(), ["plugin marketplace list --json"])

    def test_foreign_marketplace_stops_before_mutations(self):
        log = self.mock_claude(json.dumps([
            {"name": "personal-skills", "installLocation": str(self.root / "other")}
        ]))
        result = self.run_install("--both")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("points elsewhere", result.stderr)
        self.assertFalse(self.dest.exists())
        self.assertEqual(log.read_text().splitlines(), ["plugin marketplace list --json"])

    def test_marketplace_without_location_is_invalid(self):
        log = self.mock_claude(json.dumps([{"name": "personal-skills"}]))
        result = self.run_install("--both")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no valid installLocation", result.stderr)
        self.assertFalse(self.dest.exists())
        self.assertEqual(log.read_text().splitlines(), ["plugin marketplace list --json"])

    def test_worktree_git_file_is_accepted(self):
        (self.repo / ".git").rmdir()
        (self.repo / ".git").write_text("gitdir: /some/repo/.git/worktrees/test\n")
        self.assertEqual(self.run_install("--codex").returncode, 0)
        self.assertTrue((self.dest / "alpha").is_symlink())

    def test_invalid_options_do_not_install(self):
        self.assertNotEqual(self.run_install("--invalid").returncode, 0)
        self.assertFalse(self.dest.exists())


if __name__ == "__main__":
    unittest.main()
