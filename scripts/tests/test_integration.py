import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from common import integration_analysis  # noqa: E402


def git(root: Path, *args: str) -> str:
    cp = subprocess.run(
        ["git", *args], cwd=root, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if cp.returncode:
        raise AssertionError(f"git {' '.join(args)} failed:\n{cp.stderr}\n{cp.stdout}")
    return cp.stdout.strip()


class IntegrationGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.name", "Fleet Test")
        git(self.root, "config", "user.email", "fleet@example.test")
        (self.root / "seed.txt").write_text("base\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "base")
        self.base = git(self.root, "rev-parse", "HEAD")
        kit = Path(__file__).resolve().parents[2]
        self.cfg = json.loads((kit / ".agents/fleet.json").read_text(encoding="utf-8"))

    def tearDown(self):
        self.temp.cleanup()

    def worker_branch(self, branch: str, path: str, task: str) -> str:
        git(self.root, "checkout", "-b", branch, self.base)
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"{task}\n", encoding="utf-8")
        git(self.root, "add", path)
        git(self.root, "commit", "-m", f"feat: worker [{task}]")
        return git(self.root, "rev-parse", "HEAD")

    def test_clean_no_ff_merges_pass(self):
        web = self.worker_branch("trk-web-web-001", "apps/web/a.txt", "WEB-001")
        api = self.worker_branch("trk-api-api-001", "services/api/a.txt", "API-001")
        git(self.root, "checkout", "-b", "trk-integration-int-001", self.base)
        git(self.root, "merge", "--no-ff", web, "-m", "merge web [INT-001]")
        git(self.root, "merge", "--no-ff", api, "-m", "merge api [INT-001]")
        (self.root / "README.md").write_text("assembled\n", encoding="utf-8")
        git(self.root, "add", "README.md")
        git(self.root, "commit", "-m", "chore: assemble [INT-001]")

        result = integration_analysis(
            self.root, self.cfg, "integration", self.base, "HEAD",
            self.cfg["tracks"]["integration"]["allow"], [web, api],
        )
        self.assertEqual(result["violations"], [])
        self.assertEqual(set(result["merged_heads"]), {web, api})

    def test_manual_merge_edit_is_rejected(self):
        web = self.worker_branch("trk-web-web-001", "apps/web/a.txt", "WEB-001")
        git(self.root, "checkout", "-b", "trk-integration-int-001", self.base)
        git(self.root, "merge", "--no-ff", "--no-commit", web)
        (self.root / "apps/web/a.txt").write_text("manually edited by integrator\n", encoding="utf-8")
        git(self.root, "add", "apps/web/a.txt")
        git(self.root, "commit", "-m", "merge web with edit [INT-001]")

        result = integration_analysis(
            self.root, self.cfg, "integration", self.base, "HEAD",
            self.cfg["tracks"]["integration"]["allow"], [web],
        )
        self.assertTrue(any("MANUALLY_EDITED_MERGE" in item for item in result["violations"]))

    def test_direct_worker_path_commit_is_rejected(self):
        git(self.root, "checkout", "-b", "trk-integration-int-001", self.base)
        target = self.root / "apps/web/a.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("illegal\n", encoding="utf-8")
        git(self.root, "add", "apps/web/a.txt")
        git(self.root, "commit", "-m", "fix: cross-track [INT-001]")

        result = integration_analysis(
            self.root, self.cfg, "integration", self.base, "HEAD",
            self.cfg["tracks"]["integration"]["allow"], [],
        )
        self.assertTrue(any("OUTSIDE_TRACK" in item for item in result["violations"]))


if __name__ == "__main__":
    unittest.main()
