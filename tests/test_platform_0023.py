"""Platform gate behavior only: synthetic VERSION/uname, no NAS proof."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "spk/package/payload/share/nut-us3000/lib.sh"
CALL = r'''
. "$1"
nutus3000_init() {
    nutus3000_version=$CASE_VERSION
    nutus3000_uname=case_uname
}
case_uname() {
    case "$1" in
        -m) printf '%s\n' "$CASE_MACHINE" ;;
        -a) printf '%s\n' "Linux NAS 5.10.55 x86_64 $CASE_MODEL" ;;
        *) return 1 ;;
    esac
}
nutus3000_validate_platform
'''


class Platform0023Test(unittest.TestCase):
    def probe(self, version, build, nano="0", unique="synology_epyc7002_sa6400",
              model="synology_epyc7002_sa6400", machine="x86_64", extra="",
              omit=()):
        with tempfile.TemporaryDirectory(prefix="nut-platform-0023-") as tmp:
            path = Path(tmp).resolve() / "VERSION"
            values = dict(productversion=version, buildnumber=build,
                          smallfixnumber=nano, unique=unique)
            path.write_text("".join(f'{k}="{v}"\n' for k, v in values.items()
                                    if k not in omit) + extra)
            result = subprocess.run(
                ["/bin/sh", "-c", CALL, "gate", str(LIB)],
                env=dict(os.environ, CASE_VERSION=str(path),
                         CASE_MACHINE=machine, CASE_MODEL=model),
                capture_output=True, text=True, timeout=3)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            return result.returncode

    def test_accepts_exact_sa6400_741_base_and_update1(self):
        for nano in ("0", "1"):
            with self.subTest(nano=nano):
                self.assertEqual(self.probe("7.4.1", "90080", nano), 0)

    def test_preserves_existing_72_policy(self):
        for version, build, want in (
            ("7.2.2", "72806", 0), ("7.2.2", "80000", 0),
            ("7.2.3", "80000", 0), ("7.2.1", "72806", 1),
            ("7.2.2", "72805", 1), ("7.2.02", "72806", 1),
        ):
            with self.subTest(version=version, build=build):
                self.assertEqual(self.probe(version, build, "8"), want)

    def test_rejects_unverified_versions_builds_models_and_updates(self):
        for version, build in (
            ("7.3.2", "86009"), ("7.4", "90075"), ("7.4.0", "90080"),
            ("7.4.2", "90080"), ("7.4.1", "90079"), ("7.4.1", "90081"),
            ("7.4.1", "090080"), ("8.0", "90080"),
        ):
            with self.subTest(version=version, build=build):
                self.assertNotEqual(self.probe(version, build), 0)
        for fields in (
            {"nano": "2"}, {"nano": "01"}, {"nano": ""},
            {"unique": "synology_epyc7002_fs6400"},
            {"model": "synology_epyc7002_fs6400"}, {"machine": "aarch64"},
            {"omit": ("smallfixnumber",)}, {"omit": ("unique",)},
            {"extra": 'smallfixnumber="1"\n'},
            {"extra": 'unique="synology_epyc7002_sa6400"\n'},
            {"extra": 'productversion="7.4.1"\n'},
            {"extra": 'buildnumber="90080"\n'},
        ):
            with self.subTest(fields=fields):
                self.assertNotEqual(self.probe("7.4.1", "90080", **fields), 0)


if __name__ == "__main__":
    unittest.main()
