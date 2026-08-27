from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PREPARE = ROOT / "spk/scripts/prepare-build-env.sh"
BUILD = ROOT / "spk/scripts/build-release.sh"
PROVENANCE = ROOT / "spk/scripts/write-provenance.py"


class ReleaseBuildContractTest(unittest.TestCase):
    def test_network_bootstrap_and_offline_build_are_separate(self):
        self.assertTrue(PREPARE.is_file())
        self.assertTrue(BUILD.is_file())
        prepare = PREPARE.read_text()
        build = BUILD.read_text()
        self.assertIn("docker pull", prepare)
        self.assertIn("git clone", prepare)
        self.assertNotIn("docker pull", build)
        self.assertNotIn("git clone", build)
        self.assertNotIn("curl", build)
        self.assertNotIn("wget", build)
        self.assertGreaterEqual(build.count("--network none"), 2)

    def test_release_build_rejects_nonempty_output_before_docker(self):
        self.assertTrue(BUILD.is_file())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            output = root / "output"
            output.mkdir()
            (output / "existing").write_text("must survive\n")
            completed = subprocess.run(
                ["/bin/sh", str(BUILD), str(ROOT), "fixture-cache", str(output)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(0, completed.returncode)
            self.assertEqual("must survive\n", (output / "existing").read_text())

    def test_prepare_maps_verified_toolkit_to_spksrc_download_cache(self):
        prepare = PREPARE.read_text()
        self.assertIn("/spksrc/distrib/toolchain/7.2", prepare)
        self.assertIn("/spksrc/distrib/toolkit/7.2", prepare)
        self.assertIn("epyc7002-gcc1220_glibc236_x86_64-GPL.txz", prepare)
        self.assertIn("ds.epyc7002-7.2.dev.txz", prepare)
        self.assertNotIn("cp -a /toolkit/. /spksrc/distrib/", prepare)


class ProvenanceWriterTest(unittest.TestCase):
    def setUp(self):
        if not PROVENANCE.is_file():
            self.fail(f"production provenance writer is missing: {PROVENANCE}")

    def run_writer(self, *arguments: str):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "provenance.txt"
            completed = subprocess.run(
                ["python3", str(PROVENANCE), str(output), *arguments],
                text=True,
                capture_output=True,
                check=False,
            )
            payload = output.read_text() if output.exists() else None
            return completed, payload

    def test_writer_sorts_an_exact_allowlist(self):
        completed, payload = self.run_writer(
            "SPKSRC_COMMIT=5c3cc7da1d4221d7e081ed2a31ba820b0455d4de",
            "NUT_SHA256=18bf32e59eb764b13da3c4fa70384926d7fa584cb31d2fe7f137a570633eeec1",
            "BUILD_NETWORK=none",
            "PACKAGE_VERSION=2.8.5-0016",
            "LIBUSB_SHA256=5977fc950f8d1395ccea9bd48c06b3f808fd3c2c961b44b0c2e6e29fc3a70a85",
            "BUILDER_IMAGE_ID=sha256:" + "a" * 64,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(
            f"BUILDER_IMAGE_ID=sha256:{'a' * 64}\n"
            "BUILD_NETWORK=none\n"
            "LIBUSB_SHA256=5977fc950f8d1395ccea9bd48c06b3f808fd3c2c961b44b0c2e6e29fc3a70a85\n"
            "NUT_SHA256=18bf32e59eb764b13da3c4fa70384926d7fa584cb31d2fe7f137a570633eeec1\n"
            "PACKAGE_VERSION=2.8.5-0016\n"
            "SPKSRC_COMMIT=5c3cc7da1d4221d7e081ed2a31ba820b0455d4de\n",
            payload,
        )

    def test_writer_rejects_unknown_duplicate_newline_and_private_path(self):
        base = (
            "SPKSRC_COMMIT=5c3cc7da1d4221d7e081ed2a31ba820b0455d4de",
            "NUT_SHA256=" + "1" * 64,
            "BUILD_NETWORK=none",
            "PACKAGE_VERSION=2.8.5-0016",
            "LIBUSB_SHA256=" + "2" * 64,
            "BUILDER_IMAGE_ID=sha256:" + "3" * 64,
        )
        bad_sets = (
            base + ("UNKNOWN=value",),
            base + (base[0],),
            base[:-1] + ("BUILDER_IMAGE_ID=line1\nline2",),
            base[:-1] + ("BUILDER_IMAGE_ID=/Users/private/cache",),
        )
        for arguments in bad_sets:
            with self.subTest(arguments=arguments[-1]):
                completed, payload = self.run_writer(*arguments)
                self.assertNotEqual(0, completed.returncode)
                self.assertIsNone(payload)


if __name__ == "__main__":
    unittest.main()
