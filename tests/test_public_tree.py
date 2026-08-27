from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_TOP = {
    ".gitignore",
    "CHANGELOG.md",
    "LICENSE",
    "LICENSES",
    "README.md",
    "README_RU.md",
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
    def test_top_level_is_an_allowed_subset_during_bootstrap(self):
        actual = {path.name for path in ROOT.iterdir() if path.name != ".git"}
        self.assertTrue(actual <= ALLOWED_TOP)
        self.assertTrue({".gitignore", "spk", "tests"} <= actual)

    def test_forbidden_private_paths_are_absent(self):
        bad = [
            path
            for path in ROOT.rglob("*")
            if FORBIDDEN_PARTS.intersection(path.parts)
        ]
        self.assertEqual([], bad)

    def test_historical_spk_files_are_absent(self):
        self.assertEqual([], list(ROOT.rglob("*.spk")))


if __name__ == "__main__":
    unittest.main()
