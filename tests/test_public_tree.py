from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_TOP = {
    ".gitignore",
    "CHANGELOG.md",
    "LICENSE",
    "LICENSES",
    "README.md",
    "README_RU.md",
    "release",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "docs",
    "spk",
    "tests",
}
FORBIDDEN_PARTS = {
    ".superpowers",
    "evidence",
    "live",
    "host-integration",
    "__pycache__",
}


class PublicTreeTest(unittest.TestCase):
    @staticmethod
    def tracked_paths():
        completed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        return [Path(raw.decode()) for raw in completed.stdout.split(b"\0") if raw]

    def test_top_level_is_exact(self):
        actual = {
            path.name
            for path in ROOT.iterdir()
            if path.name not in {".git", "artifacts"}
        }
        self.assertEqual(ALLOWED_TOP, actual)

    def test_local_binary_artifacts_are_ignored(self):
        artifacts = ROOT / "artifacts"
        if not artifacts.exists():
            return
        completed = subprocess.run(
            ["git", "check-ignore", "--quiet", "artifacts/"],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(0, completed.returncode)

    def test_forbidden_private_paths_are_absent(self):
        bad = [
            path
            for path in self.tracked_paths()
            if FORBIDDEN_PARTS.intersection(path.parts)
        ]
        self.assertEqual([], bad)

    def test_historical_spk_files_are_absent(self):
        self.assertEqual([], [path for path in self.tracked_paths() if path.suffix == ".spk"])


if __name__ == "__main__":
    unittest.main()
