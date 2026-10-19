from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
README_EN = ROOT / "README.md"
README_RU = ROOT / "README_RU.md"
BUILDING = ROOT / "docs/BUILDING.md"
VALIDATION = ROOT / "docs/VALIDATION.md"
SECURITY = ROOT / "SECURITY.md"
CHANGELOG = ROOT / "CHANGELOG.md"


class PublicDocumentationTest(unittest.TestCase):
    def require_text(self, path: Path) -> str:
        self.assertTrue(path.is_file(), f"public document is missing: {path}")
        return path.read_text()

    def test_readmes_cover_the_same_complete_user_flow(self):
        english = self.require_text(README_EN)
        russian = self.require_text(README_RU)
        english_lower = english.lower()
        russian_lower = russian.lower()
        english_flat = " ".join(english_lower.split())
        russian_flat = " ".join(russian_lower.split())

        for token in (
            "2.8.5-0016", "DSM 7.2.2-72806", "epyc7002", "SA6400",
            "2b89:ffff", "DC600", "Arduino HID 0.22", "10.255.255.1",
            "10 minutes", "TCP 3493", "Arc Apps & Permissions",
            "Package Center", "unofficial", "GPL-2.0-or-later",
        ):
            self.assertIn(token.lower(), english_lower)
        for token in (
            "2.8.5-0016", "DSM 7.2.2-72806", "epyc7002", "SA6400",
            "2b89:ffff", "DC600", "Arduino HID 0.22", "10.255.255.1",
            "10 минут", "TCP 3493", "Arc Apps & Permissions",
            "Центр пакетов", "неофициальный", "GPL-2.0-or-later",
        ):
            self.assertIn(token.lower(), russian_lower)

        self.assertIn("every 5 minutes", english_lower)
        self.assertIn("каждые 5 минут", russian_lower)
        self.assertIn("firewall", english_lower)
        self.assertIn("брандмауэр", russian_lower)
        for text in (english_lower, russian_lower):
            self.assertNotIn("sudo ", text)
            self.assertNotIn("ssh ", text)
        self.assertIn("fresh package install on a preconfigured host", english_flat)
        self.assertIn("свежая установка пакета на заранее настроенном хосте", russian_flat)
        self.assertIn("does not create", english_flat)
        self.assertIn("не создаёт", russian_flat)
        self.assertIn("all interfaces", english_flat)
        self.assertIn("все интерфейсы", russian_flat)
        self.assertIn("all sources", english_flat)
        self.assertIn("все источники", russian_flat)
        self.assertIn("not required", english_flat)
        self.assertIn("не требуется", russian_flat)

    def test_public_docs_have_resolvable_language_and_project_links(self):
        english = self.require_text(README_EN)
        russian = self.require_text(README_RU)
        self.assertIn("[Русский](README_RU.md)", english)
        self.assertIn("[English](README.md)", russian)
        for document in (english, russian):
            for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", document):
                if "://" not in target and not target.startswith("#"):
                    self.assertTrue((ROOT / target).resolve().is_file(), target)

    def test_build_validation_security_and_changelog_contracts(self):
        building = self.require_text(BUILDING)
        validation = self.require_text(VALIDATION)
        security = self.require_text(SECURITY)
        changelog = self.require_text(CHANGELOG)
        for required in (
            "fetch-verify-sources.sh", "prepare-build-env.sh", "build-release.sh",
            "--network none", "5c3cc7da1d4221d7e081ed2a31ba820b0455d4de",
            "18bf32e59eb764b13da3c4fa70384926d7fa584cb31d2fe7f137a570633eeec1",
            "5977fc950f8d1395ccea9bd48c06b3f808fd3c2c961b44b0c2e6e29fc3a70a85",
        ):
            self.assertIn(required, building)
        self.assertIn("RC_PENDING_PUBLIC_CLEAN_INSTALL", validation)
        self.assertIn("preconfigured host", validation.lower())
        self.assertIn("inherited", validation.lower())
        self.assertIn("private vulnerability reporting", security.lower())
        self.assertIn("2.8.5-0016", changelog)
        self.assertIn("pre-release", changelog.lower())

    def test_public_tree_contains_no_private_identifiers(self):
        forbidden = (
            "/Users/" + "ehlopenko",
            "/volume3/docker/" + ".nut-us3000-native-spk-phase1-backup",
            "ehlopenko" + "5463w",
            "quickconnect" + ".to",
            "@gmail" + ".com",
            "@yandex" + ".ru",
        )
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            try:
                text = path.read_text()
            except UnicodeDecodeError:
                continue
            for marker in forbidden:
                self.assertNotIn(marker, text, f"private marker in {path.relative_to(ROOT)}")


if __name__ == "__main__":
    unittest.main()
