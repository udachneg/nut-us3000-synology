from pathlib import Path
import os
import shutil
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "spk/scripts/fetch-verify-toolkit.sh"
SPKSRC_BUILD = ROOT / "spk/scripts/build-spksrc-spk.sh"
LOCK = ROOT / "spk/sources/synology-toolkit.md5"
ARCHIVES = (
    "base_env-7.2.txz",
    "ds.epyc7002-7.2.dev.txz",
    "ds.epyc7002-7.2.env.txz",
    "epyc7002-gcc1220_glibc236_x86_64-GPL.txz",
)
SHA256S = {
    "base_env-7.2.txz": "1" * 64,
    "ds.epyc7002-7.2.dev.txz": "2" * 64,
    "ds.epyc7002-7.2.env.txz": "3" * 64,
    "epyc7002-gcc1220_glibc236_x86_64-GPL.txz": "4" * 64,
}


class SpkSupplyChainTest(unittest.TestCase):
    def test_final_spksrc_build_uses_only_pinned_local_inputs(self):
        text = SPKSRC_BUILD.read_text()
        for forbidden in ("curl", "wget", "docker pull", "git clone", "fetch-verify-toolkit.sh"):
            self.assertNotIn(forbidden, text)
        for required in (
            "spk/package/native/nut-us3000-controller.c",
            "spk/package/payload/share/nut-us3000/retry-step.sh",
            "spk/package/payload/app/helptoc.conf",
            "SPKSRC_COMMIT=5c3cc7da1d4221d7e081ed2a31ba820b0455d4de",
            "ghcr.io/synocommunity/spksrc@sha256:deeef1a01210c914c43a7c18a40aee62885eeee041cc70e7bd1907153561cc94",
        ):
            self.assertIn(required, text)

    def make_fixture(self, mode: str = "good", transform=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "spk/scripts").mkdir(parents=True)
        (root / "spk/sources").mkdir()
        if SCRIPT.exists():
            shutil.copy2(SCRIPT, root / "spk/scripts/fetch-verify-toolkit.sh")
        lock_text = LOCK.read_text()
        if transform:
            lock_text = transform(lock_text)
        (root / "spk/sources/synology-toolkit.md5").write_text(lock_text)

        fake_bin = root / "fake-bin"
        fake_bin.mkdir()
        (fake_bin / "curl").write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "out= url= previous=\n"
            "for arg in \"$@\"; do\n"
            "  [ \"$previous\" = --output ] && out=$arg\n"
            "  previous=$arg\n"
            "  url=$arg\n"
            "done\n"
            "[ -n \"$out\" ]\n"
            "name=${url##*/}\n"
            "printf 'fixture archive bytes: %s\\n' \"$name\" > \"$out\"\n"
            "if [ \"${FIXTURE_MODE:-good}\" = curl-fail ]; then exit 23; fi\n"
        )
        md5_body = (
            "#!/bin/sh\n"
            "set -eu\n"
            "name=${1##*/}\n"
            "case $name in\n"
            "  base_env-7.2.txz) sum=67caa22f50a45f2b252a011fd45020a8;;\n"
            "  ds.epyc7002-7.2.dev.txz) sum=21a23d292f81c39da1851978593dd5dc;;\n"
            "  ds.epyc7002-7.2.env.txz) sum=b928b3c0adcacfbd53e9f3f5133a8a27;;\n"
            "  epyc7002-gcc1220_glibc236_x86_64-GPL.txz) sum=117ae882569c315db4b19e5426f50eb9;;\n"
            "  *) exit 64;;\n"
            "esac\n"
            "if [ \"${FIXTURE_MODE:-good}\" = md5-fail ]; then sum=00000000000000000000000000000000; fi\n"
        )
        (fake_bin / "md5sum").write_text(md5_body + "printf '%s  %s\\n' \"$sum\" \"$1\"\n")
        (fake_bin / "md5").write_text(md5_body + "[ \"$1\" = -q ]\nprintf '%s\\n' \"$sum\"\n")
        sha_body = (
            "#!/bin/sh\n"
            "set -eu\n"
            "name=${1##*/}\n"
            "case $name in\n"
            "  base_env-7.2.txz) sum=" + SHA256S[ARCHIVES[0]] + ";;\n"
            "  ds.epyc7002-7.2.dev.txz) sum=" + SHA256S[ARCHIVES[1]] + ";;\n"
            "  ds.epyc7002-7.2.env.txz) sum=" + SHA256S[ARCHIVES[2]] + ";;\n"
            "  epyc7002-gcc1220_glibc236_x86_64-GPL.txz) sum=" + SHA256S[ARCHIVES[3]] + ";;\n"
            "  *) exit 64;;\n"
            "esac\n"
        )
        (fake_bin / "sha256sum").write_text(sha_body + "printf '%s  %s\\n' \"$sum\" \"$1\"\n")
        (fake_bin / "shasum").write_text(
            sha_body + "[ \"$1\" = -a ] && [ \"$2\" = 256 ]\nprintf '%s  %s\\n' \"$sum\" \"$3\"\n"
        )
        for command in fake_bin.iterdir():
            command.chmod(0o755)
        env = os.environ | {"PATH": f"{fake_bin}:{os.environ['PATH']}", "FIXTURE_MODE": mode}
        return root, env

    @staticmethod
    def published(cache: Path) -> set[str]:
        return {path.name for path in cache.iterdir()} if cache.exists() else set()

    def run_fetcher(self, root: Path, cache: Path, env: dict[str, str]):
        fixture_script = root / "spk/scripts/fetch-verify-toolkit.sh"
        self.assertTrue(
            fixture_script.is_file(),
            f"production script is missing: {SCRIPT}",
        )
        return subprocess.run(
            ["/bin/sh", str(fixture_script), str(cache)],
            text=True, capture_output=True, env=env,
        )

    def test_rejects_non_https_or_non_synology_url(self):
        for replacement in (
            "http://global.synologydownload.com/",
            "https://mirror.example.invalid/",
        ):
            with self.subTest(replacement=replacement):
                root, env = self.make_fixture(
                    transform=lambda text, replacement=replacement: text.replace(
                        "https://global.synologydownload.com/", replacement, 1
                    )
                )
                cache = root / "cache"
                completed = self.run_fetcher(root, cache, env)
                self.assertNotEqual(0, completed.returncode)
                self.assertEqual(set(), self.published(cache))

    def test_rejects_duplicate_or_unexpected_archive_basename(self):
        def duplicate(text: str) -> str:
            lines = text.splitlines()
            lines[1] = lines[0]
            return "\n".join(lines) + "\n"

        def unexpected(text: str) -> str:
            return text + (
                "00000000000000000000000000000000  unexpected.txz  "
                "https://global.synologydownload.com/download/unexpected.txz\n"
            )

        for transform in (duplicate, unexpected):
            with self.subTest(transform=transform.__name__):
                root, env = self.make_fixture(transform=transform)
                cache = root / "cache"
                completed = self.run_fetcher(root, cache, env)
                self.assertNotEqual(0, completed.returncode)
                self.assertEqual(set(), self.published(cache))

    def test_preserves_curl_nonzero_result_without_publication(self):
        root, env = self.make_fixture(mode="curl-fail")
        cache = root / "cache"
        completed = self.run_fetcher(root, cache, env)
        self.assertEqual(23, completed.returncode, completed.stderr)
        self.assertEqual(set(), self.published(cache))

    def test_rejects_publisher_md5_mismatch_without_publication(self):
        root, env = self.make_fixture(mode="md5-fail")
        cache = root / "cache"
        completed = self.run_fetcher(root, cache, env)
        self.assertNotEqual(0, completed.returncode)
        self.assertEqual(set(), self.published(cache))

    def test_rechecks_existing_sha_lock_byte_for_byte(self):
        root, env = self.make_fixture()
        cache = root / "cache"
        cache.mkdir()
        existing = "".join(f"{SHA256S[name]}  {name}\n" for name in ARCHIVES).rstrip("\n")
        sha_lock = cache / "SHA256SUMS"
        sha_lock.write_text(existing)
        completed = self.run_fetcher(root, cache, env)
        self.assertNotEqual(0, completed.returncode)
        self.assertEqual(existing, sha_lock.read_text())
        self.assertEqual({"SHA256SUMS"}, self.published(cache))

    def test_publishes_exactly_four_verified_archives_and_metadata(self):
        root, env = self.make_fixture()
        cache = root / "cache"
        completed = self.run_fetcher(root, cache, env)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual({"verified", "SHA256SUMS", "PROVENANCE.txt"}, self.published(cache))
        verified = cache / "verified"
        self.assertEqual(set(ARCHIVES), {path.name for path in verified.iterdir()})
        self.assertEqual(
            [f"fixture archive bytes: {name}\n" for name in ARCHIVES],
            [(verified / name).read_text() for name in ARCHIVES],
        )
        for path in (cache / "SHA256SUMS", cache / "PROVENANCE.txt"):
            self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))
        self.assertEqual(
            "".join(f"{SHA256S[name]}  {name}\n" for name in ARCHIVES),
            (cache / "SHA256SUMS").read_text(),
        )
        provenance = (cache / "PROVENANCE.txt").read_text()
        self.assertNotIn(str(root), provenance)
        self.assertNotIn("fake-bin", provenance)


class SpkSupplyChainFixRoundTest(unittest.TestCase):
    def make_fixture(self, mode: str = "good", tool_family: str = "linux"):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "spk/scripts").mkdir(parents=True)
        (root / "spk/sources").mkdir()
        shutil.copy2(SCRIPT, root / "spk/scripts/fetch-verify-toolkit.sh")
        shutil.copy2(LOCK, root / "spk/sources/synology-toolkit.md5")
        fake_bin = root / "fake-bin"
        fake_bin.mkdir()
        system_bin = root / "system-bin"
        system_bin.mkdir()
        for command in ("awk", "chmod", "cmp", "dirname", "find", "grep", "ls", "mkdir", "mktemp", "rm", "wc"):
            os.symlink(shutil.which(command), system_bin / command)

        (fake_bin / "curl").write_text(
            "#!/bin/sh\nset -eu\nout= url= previous= followed=no\n"
            "for arg in \"$@\"; do\n"
            "  if [ \"$previous\" = --output ]; then out=$arg; fi\n"
            "  if [ \"$arg\" = --location ]; then followed=yes; fi\n"
            "  previous=$arg; url=$arg\ndone\n"
            "[ -n \"$out\" ]\n"
            "if [ \"${FIXTURE_MODE:-good}\" = redirect-foreign ] && [ \"$followed\" = no ]; then exit 47; fi\n"
            "printf 'fixture archive bytes: %s\\n' \"${url##*/}\" > \"$out\"\n"
        )
        md5_cases = (
            "case ${file##*/} in\n"
            "base_env-7.2.txz) sum=67caa22f50a45f2b252a011fd45020a8;;\n"
            "ds.epyc7002-7.2.dev.txz) sum=21a23d292f81c39da1851978593dd5dc;;\n"
            "ds.epyc7002-7.2.env.txz) sum=b928b3c0adcacfbd53e9f3f5133a8a27;;\n"
            "epyc7002-gcc1220_glibc236_x86_64-GPL.txz) sum=117ae882569c315db4b19e5426f50eb9;;\n"
            "*) exit 64;; esac\n"
        )
        sha_cases = (
            "case ${file##*/} in\n"
            f"base_env-7.2.txz) sum={SHA256S[ARCHIVES[0]]};;\n"
            f"ds.epyc7002-7.2.dev.txz) sum={SHA256S[ARCHIVES[1]]};;\n"
            f"ds.epyc7002-7.2.env.txz) sum={SHA256S[ARCHIVES[2]]};;\n"
            f"epyc7002-gcc1220_glibc236_x86_64-GPL.txz) sum={SHA256S[ARCHIVES[3]]};;\n"
            "*) exit 64;; esac\n"
        )
        if tool_family == "linux":
            (fake_bin / "md5sum").write_text(
                "#!/bin/sh\nset -eu\nfile=$1\n" + md5_cases
                + "if [ \"${FIXTURE_MODE:-good}\" = malformed-md5 ]; then printf '%s  %s extra\\n' \"$sum\" \"$file\"; else printf '%s  %s\\n' \"$sum\" \"$file\"; fi\n"
            )
            (fake_bin / "sha256sum").write_text(
                "#!/bin/sh\nset -eu\nfile=$1\n" + sha_cases
                + "if [ \"${FIXTURE_MODE:-good}\" = malformed-sha ]; then printf '%s  %s extra\\n' \"$sum\" \"$file\"; else printf '%s  %s\\n' \"$sum\" \"$file\"; fi\n"
            )
        elif tool_family == "mac":
            (fake_bin / "md5").write_text(
                "#!/bin/sh\nset -eu\n[ \"$1\" = -q ] && [ \"$#\" -eq 2 ]\nfile=$2\n" + md5_cases + "printf '%s\\n' \"$sum\"\n"
            )
            (fake_bin / "shasum").write_text(
                "#!/bin/sh\nset -eu\n[ \"$1\" = -a ] && [ \"$2\" = 256 ] && [ \"$#\" -eq 3 ]\nfile=$3\n" + sha_cases + "printf '%s  %s\\n' \"$sum\" \"$file\"\n"
            )
        else:
            raise ValueError(tool_family)
        (fake_bin / "mv").write_text(
            "#!/bin/sh\nset -eu\nfor dest; do :; done\n"
            "case \"${FIXTURE_MODE:-good}:$dest\" in\n"
            "mv-fail-sha:*/SHA256SUMS|mv-fail-provenance:*/PROVENANCE.txt|mv-fail-verified:*/verified) exit 47;;\nesac\n"
            "exec \"$REAL_MV\" \"$@\"\n"
        )
        for command in fake_bin.iterdir():
            command.chmod(0o755)
        secret = f"fixture-secret-{root.name}"
        env = {
            "PATH": f"{fake_bin}:{system_bin}",
            "FIXTURE_MODE": mode,
            "FIXTURE_SECRET": secret,
            "REAL_MV": shutil.which("mv"),
        }
        return root, env, secret

    def run_fetcher(self, root: Path, cache: Path, env: dict[str, str]):
        return subprocess.run(
            ["/bin/sh", str(root / "spk/scripts/fetch-verify-toolkit.sh"), str(cache)],
            text=True, capture_output=True, env=env,
        )

    def assert_no_publication(self, cache: Path):
        self.assertEqual(set(), {path.name for path in cache.iterdir()} if cache.exists() else set())

    def test_rejects_cross_origin_redirect_without_publication(self):
        root, env, _ = self.make_fixture(mode="redirect-foreign")
        cache = root / "cache"
        completed = self.run_fetcher(root, cache, env)
        self.assertEqual(47, completed.returncode, completed.stderr)
        self.assert_no_publication(cache)

    def test_rejects_malformed_hash_tool_output_without_publication(self):
        for mode in ("malformed-md5", "malformed-sha"):
            with self.subTest(mode=mode):
                root, env, _ = self.make_fixture(mode=mode)
                cache = root / "cache"
                completed = self.run_fetcher(root, cache, env)
                self.assertNotEqual(0, completed.returncode)
                self.assert_no_publication(cache)

    def test_macos_hash_tool_fallback_publishes_verified_bytes(self):
        root, env, _ = self.make_fixture(tool_family="mac")
        cache = root / "cache"
        completed = self.run_fetcher(root, cache, env)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(set(ARCHIVES), {path.name for path in (cache / "verified").iterdir()})

    @staticmethod
    def cache_state(cache: Path):
        metadata = {
            name: ((cache / name).read_bytes(), stat.S_IMODE((cache / name).stat().st_mode))
            for name in ("SHA256SUMS", "PROVENANCE.txt")
        }
        verified = {
            path.name: (
                path.is_dir(),
                path.is_symlink(),
                path.read_bytes() if path.is_file() else None,
            )
            for path in (cache / "verified").iterdir()
        }
        return metadata, verified

    def test_rejects_insecure_existing_metadata_modes_without_mutation(self):
        root, env, _ = self.make_fixture()
        cache = root / "cache"
        self.assertEqual(0, self.run_fetcher(root, cache, env).returncode)
        for path in (cache / "SHA256SUMS", cache / "PROVENANCE.txt"):
            path.chmod(0o644)
        before = self.cache_state(cache)
        completed = self.run_fetcher(root, cache, env)
        self.assertNotEqual(0, completed.returncode)
        self.assertEqual(before, self.cache_state(cache))

    def test_later_validation_failure_preserves_insecure_existing_metadata_state(self):
        root, env, _ = self.make_fixture()
        cache = root / "cache"
        self.assertEqual(0, self.run_fetcher(root, cache, env).returncode)
        for path in (cache / "SHA256SUMS", cache / "PROVENANCE.txt"):
            path.chmod(0o644)
        (cache / "verified" / "unexpected").write_text("stale")
        before = self.cache_state(cache)
        completed = self.run_fetcher(root, cache, env)
        self.assertNotEqual(0, completed.returncode)
        self.assertEqual(before, self.cache_state(cache))

    def test_rejects_extra_or_nonregular_existing_verified_entries(self):
        for kind in ("file", "directory", "symlink"):
            with self.subTest(kind=kind):
                root, env, _ = self.make_fixture()
                cache = root / "cache"
                self.assertEqual(0, self.run_fetcher(root, cache, env).returncode)
                extra = cache / "verified" / "unexpected"
                if kind == "file":
                    extra.write_text("stale")
                elif kind == "directory":
                    extra.mkdir()
                else:
                    extra.symlink_to(cache / "verified" / ARCHIVES[0])
                completed = self.run_fetcher(root, cache, env)
                self.assertNotEqual(0, completed.returncode)
                self.assertTrue(extra.exists() or extra.is_symlink())

    def test_publish_failures_roll_back_every_created_target(self):
        for mode in ("mv-fail-sha", "mv-fail-provenance", "mv-fail-verified"):
            with self.subTest(mode=mode):
                root, env, _ = self.make_fixture(mode=mode)
                cache = root / "cache"
                completed = self.run_fetcher(root, cache, env)
                self.assertEqual(47, completed.returncode, completed.stderr)
                self.assert_no_publication(cache)

    def test_published_metadata_omits_fixture_secret(self):
        root, env, secret = self.make_fixture()
        cache = root / "cache"
        completed = self.run_fetcher(root, cache, env)
        self.assertEqual(0, completed.returncode, completed.stderr)
        for path in (cache / "SHA256SUMS", cache / "PROVENANCE.txt"):
            self.assertNotIn(secret, path.read_text())


if __name__ == "__main__":
    unittest.main()
