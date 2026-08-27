from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "spk/sources/source-manifest.sha256"
FETCHER = ROOT / "spk/scripts/fetch-verify-sources.sh"
SIGNATURE = ROOT / "spk/sources/nut-2.8.5.tar.gz.sig"
KEYRING = ROOT / "spk/sources/nut-key.gpg"

NUT_BYTES = b"fixture NUT 2.8.5 source\n"
LIBUSB_BYTES = b"fixture libusb 1.0.29 source\n"
SIG_BYTES = b"fixture NUT signature\n"
KEY_BYTES = b"fixture NUT keyring\n"

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
            "[ \"${FIXTURE_MODE:-good}\" != signature-fail ] || exit 1\n"
            "exit 0\n"
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
