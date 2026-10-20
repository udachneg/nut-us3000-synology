"""Advisory DSM metadata and real INFO publishing; no NAS operations."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "spk/package/payload/share/nut-us3000/lib.sh"
SOURCE = ROOT / "spk/package/native/nut-us3000-hostctl.c"
KNOWN = ('productversion="7.2.2"\nbuildnumber="72806"\n'
         'smallfixnumber="8"\n')
LIVE_UNAME = ("Linux NAS 5.10.55+ #72806 SMP Mon Jul 21 23:15:58 CST 2025 "
              "x86_64 GNU/Linux synology_epyc7002_sa6400\n")
CALL = r'''
. "$1"
nutus3000_init() {
    nutus3000_version=$CASE_VERSION
    nutus3000_uname=case_uname
}
case_uname() {
    case "$1" in
        -m) printf '%s\n' "$CASE_MACHINE" ;;
        -a) printf '%s\n' "Linux NAS $CASE_MODEL" ;;
        *) return 1 ;;
    esac
}
nutus3000_validate_platform
'''


class PlatformCompatibilityTest(unittest.TestCase):
    def probe(self, metadata, machine="x86_64",
              model="synology_epyc7002_sa6400"):
        with tempfile.TemporaryDirectory(prefix="nut-platform-0024-") as tmp:
            path = Path(tmp).resolve() / "VERSION"
            if metadata is not None:
                path.write_text(metadata)
            return subprocess.run(
                ["/bin/sh", "-c", CALL, "gate", str(LIB)],
                env=dict(os.environ, CASE_VERSION=str(path),
                         CASE_MACHINE=machine, CASE_MODEL=model),
                capture_output=True, text=True, timeout=3)

    def test_version_and_unreadable_metadata_do_not_block_platform(self):
        # A version allowlist must not silently disable UPS after a DSM update.
        for metadata in (KNOWN, KNOWN.replace("7.2.2", "7.4.1"),
                         KNOWN.replace("7.2.2", "8.0").replace("72806", "99999"),
                         KNOWN.replace('"8"', '"20"'), None, "", "not=VERSION\n",
                         KNOWN + 'productversion="7.4.1"\n'):
            with self.subTest(metadata=metadata):
                result = self.probe(metadata)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "")

    def test_incompatible_or_unidentifiable_platform_still_blocks(self):
        for machine, model in (
            ("aarch64", "synology_epyc7002_sa6400"),
            ("x86_64", "synology_apollolake_ds920"),
            ("x86_64", ""),
            ("x86_64", "synology_epyc7002_sa6400 synology_epyc7002_sa6400"),
        ):
            with self.subTest(machine=machine, model=model):
                self.assertNotEqual(self.probe(KNOWN, machine, model).returncode, 0)


class DescriptionCompatibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="nut-description-0024-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name).resolve()
        cls.info_root = cls.root / "var"
        cls.package = cls.info_root / "packages/nut-us3000"
        cls.package.mkdir(parents=True)
        cls.version_root = cls.root / "etc.defaults"
        cls.version_root.mkdir()
        cls.version = cls.version_root / "VERSION"
        cls.info = cls.package / "INFO"
        cls.binary = cls.root / "hostctl"
        cls.uname_output = cls.root / "uname-output"
        cls.uname_tool = cls.root / "uname"
        cls.uname_tool.write_text(
            '#!/bin/sh\n[ "$#" = 1 ] && [ "$1" = -a ] || exit 64\n'
            f"exec /bin/cat '{cls.uname_output}'\n")
        cls.uname_tool.chmod(0o755)
        definitions = {
            "NUT_US3000_INFO_ROOT": cls.info_root,
            "NUT_US3000_VERSION_ROOT": cls.version_root,
            "NUT_US3000_SETTINGS_ROOT": cls.root / "absent-settings",
            "NUT_US3000_SETTINGS_UNAME": cls.uname_tool,
        }
        command = ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                   "-DNUT_US3000_TESTING=1",
                   f"-DNUT_US3000_INFO_OWNER={os.getuid()}"]
        if sys.platform == "darwin":
            command += ["-D_DARWIN_C_SOURCE=1"]
        command += [f'-D{k}="{v}"' for k, v in definitions.items()]
        result = subprocess.run(command + [str(SOURCE), "-o", str(cls.binary)],
                                capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)

    def publish(self, metadata, state="healthy", uname=LIVE_UNAME):
        self.uname_output.write_text(uname)
        if self.version.exists() or self.version.is_symlink():
            self.version.unlink()
        if metadata is not None:
            self.version.write_bytes(metadata.encode() if isinstance(metadata, str) else metadata)
        self.info.write_text('package="nut-us3000"\nversion="2.8.5-0024"\n'
                             'description="old"\ndescription_rus="old"\n'
                             'maintainer="Hevtech"\n')
        result = subprocess.run([str(self.binary), "description-" + state],
                                capture_output=True, text=True, timeout=4)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.info.read_text()
        self.assertIn('version="2.8.5-0024"', text)
        self.assertIn('maintainer="Hevtech"', text)
        self.assertEqual(len(text.splitlines()), 5)
        self.assertFalse((self.package / ".INFO-nut-us3000-status.tmp").exists())
        return text

    def test_previously_exercised_environment_is_distinct_from_unverified(self):
        known = self.publish(KNOWN)
        self.assertIn("🟢 среда ранее проверялась", known)
        for metadata in (KNOWN.replace("7.2.2", "7.4.1").replace("72806", "90080"),
                         KNOWN.replace("7.2.2", "8.0"),
                         KNOWN.replace('"8"', '"9"')):
            with self.subTest(metadata=metadata):
                text = self.publish(metadata)
                self.assertIn("🟡 эта версия DSM ещё не проверена", text)
                self.assertIn("🟡 DSM environment not yet verified", text)
                self.assertNotIn("🟢 среда ранее проверялась", text)

    def test_unreadable_ambiguous_or_unsafe_metadata_is_only_advisory(self):
        for metadata in (None, "", "broken\n", KNOWN + 'productversion="7.4.1"\n',
                         KNOWN.replace('smallfixnumber="8"\n', ""),
                         KNOWN.replace('"7.2.2"', '"$(touch /tmp/NOT-EXECUTED)"'),
                         KNOWN.encode() + b"\x00", "x" * 65537):
            with self.subTest(metadata=metadata if metadata is None else str(metadata)[:90]):
                text = self.publish(metadata)
                self.assertIn("🟡 не удалось определить среду DSM", text)
                self.assertNotIn("$(touch", text)
                self.assertIn("🟢 связь с ИБП подтверждена", text)

    def test_warning_never_replaces_state_or_settings(self):
        states = {
            "pending": "🟡 проверка ещё не завершена",
            "waiting": "🟡 ожидание после загрузки",
            "healthy": "🟢 связь с ИБП подтверждена",
            "degraded": "🔴 проблема связи",
            "unavailable": "🔴 ИБП недоступен",
            "error": "🟡 ошибка проверки",
            "stopped": "⚪ пакет остановлен",
        }
        for state, expected in states.items():
            with self.subTest(state=state):
                text = self.publish(KNOWN.replace("7.2.2", "8.0"), state)
                self.assertIn(expected, text)
                self.assertIn("🟡 эта версия DSM ещё не проверена", text)
                self.assertIn("◆ НАСТРОЙКА DSM: 🟡 не удалось проверить", text)
                self.assertIn("◆ БРАНДМАУЭР: 🟡 не удалось проверить", text)
                self.assertIn("Задержка 5 минут", text)
                self.assertIn("TCP 3493", text)

    def test_live_version_without_unique_uses_uname_identity(self):
        # Actual NAS capture: VERSION has three relevant keys, model is in uname.
        for metadata in (KNOWN, KNOWN + 'unique="misleading_other_model"\n'):
            with self.subTest(metadata=metadata):
                text = self.publish(metadata)
                self.assertIn("🟢 среда ранее проверялась", text)
                self.assertIn("🟢 связь с ИБП подтверждена", text)

    def test_uname_identity_is_required_for_exercised_label_not_for_publishing(self):
        for uname, expected in (
            (LIVE_UNAME.replace("sa6400", "fs6400"), "🟡 эта версия DSM ещё не проверена"),
            ("", "🟡 не удалось определить среду DSM"),
            (LIVE_UNAME + "synology_epyc7002_sa6400\n", "🟡 не удалось определить среду DSM"),
        ):
            with self.subTest(uname=uname):
                text = self.publish(KNOWN, uname=uname)
                self.assertIn(expected, text)
                self.assertNotIn("🟢 среда ранее проверялась", text)
                self.assertIn("🟢 связь с ИБП подтверждена", text)


if __name__ == "__main__":
    unittest.main()
