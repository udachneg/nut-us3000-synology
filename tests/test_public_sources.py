from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "spk/sources/source-manifest.sha256"
FETCHER = ROOT / "spk/scripts/fetch-verify-sources.sh"
SIGNATURE = ROOT / "spk/sources/nut-2.8.5.tar.gz.sig"
KEYRING = ROOT / "spk/sources/nut-key.gpg"
RELEASE_MANIFEST = ROOT / "release/SOURCE-COMPONENTS-0016.sha256"
RELEASE_NOTES = ROOT / "release/RELEASE-NOTES-0016-RC2.md"
CANONICAL_SPK = ROOT / "artifacts/nut-us3000_epyc7002-7.2_2.8.5-0016.spk"

NUT_BYTES = b"fixture NUT 2.8.5 source\n"
LIBUSB_BYTES = b"fixture libusb 1.0.29 source\n"
SIG_BYTES = b"fixture NUT signature\n"
KEY_BYTES = b"fixture NUT keyring\n"
BINARY_KEY_BYTES = b"fixture binary NUT keyring\n"

EXPECTED_MANIFEST = {
    "artifacts/nut-2.8.5.tar.gz":
        "18bf32e59eb764b13da3c4fa70384926d7fa584cb31d2fe7f137a570633eeec1",
    "spk/sources/nut-2.8.5.tar.gz.sig":
        "3211f48f7a312ae13770828d768a5e4d95c6866bfd96bf79df44665c8e6c85fb",
    "spk/sources/nut-key.gpg":
        "c12ead62f833ad128266c1a812d0b487a62929adf1e28859a2783c8dc1c7f2a0",
    "artifacts/libusb-1.0.29.tar.bz2":
        "5977fc950f8d1395ccea9bd48c06b3f808fd3c2c961b44b0c2e6e29fc3a70a85",
}

EXPECTED_RELEASE_COMPONENTS = {
    "artifacts/nut-us3000_epyc7002-7.2_2.8.5-0016.spk":
        "8b288b035aac4fee7ac85850892b7e6064fb0029f38cfb040ce8443858f7e2b9",
    "artifacts/nut-2.8.5.tar.gz":
        "18bf32e59eb764b13da3c4fa70384926d7fa584cb31d2fe7f137a570633eeec1",
    "spk/sources/nut-2.8.5.tar.gz.sig":
        "3211f48f7a312ae13770828d768a5e4d95c6866bfd96bf79df44665c8e6c85fb",
    "spk/sources/nut-key.gpg":
        "c12ead62f833ad128266c1a812d0b487a62929adf1e28859a2783c8dc1c7f2a0",
    "artifacts/libusb-1.0.29.tar.bz2":
        "5977fc950f8d1395ccea9bd48c06b3f808fd3c2c961b44b0c2e6e29fc3a70a85",
    "artifacts/normalized-manifest-0016.sha256":
        "ea0d8d46050a1e46e5c49c2467924433185ed3a26e7feac0c03f00718fe838d5",
    "artifacts/BUILD-PROVENANCE-0016.txt":
        "d97491391ea060654597217f6aa77f9c7b840c93a718e21e90b81e2bb7f1b47a",
}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class PublicSourceManifestTest(unittest.TestCase):
    def test_manifest_pins_exact_public_release_inputs(self):
        self.assertTrue(MANIFEST.is_file())
        parsed = {}
        for line in MANIFEST.read_text().splitlines():
            digest, relative = line.split("  ", 1)
            self.assertNotIn(relative, parsed)
            parsed[relative] = digest
        self.assertEqual(EXPECTED_MANIFEST, parsed)

    def test_bundled_signature_and_key_match_manifest(self):
        self.assertTrue(SIGNATURE.is_file())
        self.assertTrue(KEYRING.is_file())
        self.assertEqual(EXPECTED_MANIFEST["spk/sources/nut-2.8.5.tar.gz.sig"], sha256(SIGNATURE.read_bytes()))
        self.assertEqual(EXPECTED_MANIFEST["spk/sources/nut-key.gpg"], sha256(KEYRING.read_bytes()))


class PublicReleaseManifestTest(unittest.TestCase):
    def test_release_manifest_has_exact_component_set_and_current_hashes(self):
        self.assertTrue(RELEASE_MANIFEST.is_file())
        parsed = {}
        for line in RELEASE_MANIFEST.read_text().splitlines():
            digest, relative = line.split("  ", 1)
            self.assertNotIn(relative, parsed)
            parsed[relative] = digest
        self.assertEqual(EXPECTED_RELEASE_COMPONENTS, parsed)
        for relative, digest in parsed.items():
            component = ROOT / relative
            self.assertTrue(component.is_file(), relative)
            self.assertEqual(digest, sha256(component.read_bytes()), relative)

    def test_release_notes_mark_rc_as_pending_fresh_preconfigured_install(self):
        self.assertTrue(RELEASE_NOTES.is_file())
        notes = " ".join(RELEASE_NOTES.read_text().lower().split())
        for required in (
            "v2.8.5-0016-rc2", "pre-release", "fresh package install",
            "preconfigured dsm host",
        ):
            self.assertIn(required, notes)

    def test_rc_tag_suffix_does_not_change_internal_spk_version(self):
        self.assertTrue(CANONICAL_SPK.is_file())
        with tarfile.open(CANONICAL_SPK, mode="r:") as archive:
            info = archive.extractfile("INFO")
            self.assertIsNotNone(info)
            metadata = info.read().decode()
        self.assertIn('version="2.8.5-0016"', metadata)
        self.assertNotIn('version="2.8.5-0016-rc2"', metadata)


class PublicSourceFetcherTest(unittest.TestCase):
    def setUp(self):
        if not FETCHER.is_file():
            self.fail(f"production fetcher is missing: {FETCHER}")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / "spk/scripts").mkdir(parents=True)
        (self.root / "spk/sources").mkdir(parents=True)
        (self.root / "fake-bin").mkdir()
        shutil.copy2(FETCHER, self.root / "spk/scripts/fetch-verify-sources.sh")
        (self.root / "spk/sources/nut-2.8.5.tar.gz.sig").write_bytes(SIG_BYTES)
        (self.root / "spk/sources/nut-key.gpg").write_bytes(KEY_BYTES)
        self.write_fixture_manifest()
        self.write_fake_commands()

    def write_fixture_manifest(self):
        entries = (
            (sha256(NUT_BYTES), "artifacts/nut-2.8.5.tar.gz"),
            (sha256(SIG_BYTES), "spk/sources/nut-2.8.5.tar.gz.sig"),
            (sha256(KEY_BYTES), "spk/sources/nut-key.gpg"),
            (sha256(LIBUSB_BYTES), "artifacts/libusb-1.0.29.tar.bz2"),
        )
        (self.root / "spk/sources/source-manifest.sha256").write_text(
            "".join(f"{digest}  {relative}\n" for digest, relative in entries)
        )

    def write_fake_commands(self):
        fake_bin = self.root / "fake-bin"
        (fake_bin / "curl").write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "out= url= previous=\n"
            "for argument in \"$@\"; do\n"
            "  [ \"$previous\" = --output ] && out=$argument\n"
            "  previous=$argument\n"
            "  url=$argument\n"
            "done\n"
            "[ -n \"$out\" ]\n"
            "case ${url##*/} in\n"
            "  nut-2.8.5.tar.gz) printf '%s' \"$FIXTURE_NUT\" > \"$out\" ;;\n"
            "  nut-2.8.5.tar.gz.sig) printf '%s' \"$FIXTURE_SIG\" > \"$out\" ;;\n"
            "  libusb-1.0.29.tar.bz2) printf '%s' \"$FIXTURE_LIBUSB\" > \"$out\" ;;\n"
            "  *) printf 'unexpected' > \"$out\" ;;\n"
            "esac\n"
            "case ${FIXTURE_MODE:-good} in\n"
            "  curl-fail) exit 23 ;;\n"
            "  bad-nut) printf 'mutated' > \"$out\" ;;\n"
            "esac\n"
        )
        (fake_bin / "gpgv").write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "[ \"$1\" = --keyring ]\n"
            "[ \"$(cat \"$2\")\" = \"$FIXTURE_BINARY_KEY\" ] || exit 2\n"
            "[ \"${FIXTURE_MODE:-good}\" != signature-fail ] || exit 1\n"
            "exit 0\n"
        )
        (fake_bin / "gpg").write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "out= previous=\n"
            "for argument in \"$@\"; do\n"
            "  [ \"$previous\" = --output ] && out=$argument\n"
            "  previous=$argument\n"
            "done\n"
            "[ -n \"$out\" ]\n"
            "printf '%s' \"$FIXTURE_BINARY_KEY\" > \"$out\"\n"
        )
        for command in fake_bin.iterdir():
            command.chmod(0o755)

    def environment(self, mode: str = "good") -> dict[str, str]:
        return os.environ | {
            "PATH": f"{self.root / 'fake-bin'}:{os.environ['PATH']}",
            "FIXTURE_MODE": mode,
            "FIXTURE_NUT": NUT_BYTES.decode(),
            "FIXTURE_SIG": SIG_BYTES.decode(),
            "FIXTURE_LIBUSB": LIBUSB_BYTES.decode(),
            "FIXTURE_BINARY_KEY": BINARY_KEY_BYTES.decode().rstrip("\n"),
        }

    def run_fetcher(self, artifacts: Path, mode: str = "good"):
        return subprocess.run(
            ["/bin/sh", str(self.root / "spk/scripts/fetch-verify-sources.sh"), str(artifacts)],
            text=True,
            capture_output=True,
            env=self.environment(mode),
            check=False,
        )

    @staticmethod
    def published(artifacts: Path) -> set[str]:
        if not artifacts.exists():
            return set()
        return {path.name for path in artifacts.iterdir()}

    def test_verified_sources_publish_atomically(self):
        artifacts = self.root / "artifacts"
        completed = self.run_fetcher(artifacts)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(
            {"nut-2.8.5.tar.gz", "libusb-1.0.29.tar.bz2"},
            self.published(artifacts),
        )
        self.assertEqual(NUT_BYTES, (artifacts / "nut-2.8.5.tar.gz").read_bytes())
        self.assertEqual(LIBUSB_BYTES, (artifacts / "libusb-1.0.29.tar.bz2").read_bytes())

    def test_download_hash_and_signature_failures_publish_nothing(self):
        for mode in ("curl-fail", "bad-nut", "signature-fail"):
            with self.subTest(mode=mode):
                artifacts = self.root / f"artifacts-{mode}"
                completed = self.run_fetcher(artifacts, mode)
                self.assertNotEqual(0, completed.returncode)
                self.assertEqual(set(), self.published(artifacts))

    def test_existing_symlink_is_rejected_without_mutation(self):
        artifacts = self.root / "artifacts-symlink"
        artifacts.mkdir()
        target = artifacts / "external"
        target.write_bytes(b"external\n")
        link = artifacts / "nut-2.8.5.tar.gz"
        link.symlink_to(target)
        before = target.read_bytes()
        completed = self.run_fetcher(artifacts)
        self.assertNotEqual(0, completed.returncode)
        self.assertTrue(link.is_symlink())
        self.assertEqual(before, target.read_bytes())
        self.assertFalse((artifacts / "libusb-1.0.29.tar.bz2").exists())

    def test_bad_origin_or_unexpected_basename_is_rejected_before_download(self):
        script = self.root / "spk/scripts/fetch-verify-sources.sh"
        original = script.read_text()
        for old, new in (
            ("https://networkupstools.org/", "http://networkupstools.org/"),
            ("nut-2.8.5.tar.gz", "unexpected.tar.gz"),
        ):
            with self.subTest(new=new):
                script.write_text(original.replace(old, new, 1))
                artifacts = self.root / ("artifacts-" + new.replace("/", "-"))
                completed = self.run_fetcher(artifacts)
                self.assertNotEqual(0, completed.returncode)
                self.assertEqual(set(), self.published(artifacts))
        script.write_text(original)


if __name__ == "__main__":
    unittest.main()
