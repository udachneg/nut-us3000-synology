from pathlib import Path
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import struct
import subprocess
import tempfile
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "spk/package"
INFO_SCRIPT = PACKAGE / "INFO.sh"
PRIVILEGE = PACKAGE / "conf/privilege"
PORT_CONFIG = PACKAGE / "port-config/nut-us3000.sc"
WIZARDS = PACKAGE / "wizard"
TEMPLATES = PACKAGE / "templates"
SCRIPTS = PACKAGE / "scripts"
ICON_GENERATOR = ROOT / "spk/scripts/generate-icons.py"
APP_PAYLOAD = PACKAGE / "payload/app"
ROOT_LICENSE = ROOT / "LICENSE"
LIBUSB_LICENSE = ROOT / "LICENSES/LGPL-2.1-or-later.txt"
THIRD_PARTY_NOTICES = ROOT / "THIRD_PARTY_NOTICES.md"

LIFECYCLE_NAMES = (
    "postinst",
    "postuninst",
    "preinst",
    "preuninst",
    "preupgrade",
    "postupgrade",
)
EXPECTED_INFO = {
    "package": "nut-us3000",
    "version": "2.8.5-0016",
    "displayname": "NUT US3000",
    "description": "Native USB driver and host-local NUT 2.8.5 endpoint for UGREEN US3000.",
    "description_rus": "Нативный USB-драйвер и локальный NUT 2.8.5 для UGREEN US3000.",
    "maintainer": "HEVTECH",
    "arch": "epyc7002",
    "os_min_ver": "7.2.2-72806",
    "thirdparty": "yes",
    "offline_install": "yes",
    "ctl_stop": "yes",
}
EXPECTED_UPS_CONF = (
    b"[ups]\n"
    b"    driver = usbhid-ups\n"
    b"    port = auto\n"
    b"    vendorid = 2b89\n"
    b"    productid = ffff\n"
    b"    serial = DC600\n"
    b"    subdriver = \"Arduino HID 0.22\"\n"
    b"    usb_hid_rep_index = 0\n"
    b"    usb_hid_ep_in = 1\n"
    b"    usb_hid_ep_out = 1\n"
    b"    pollonly\n"
)
EXPECTED_UPSD_CONF = (
    b"LISTEN 127.0.0.1 3493\n"
    b"LISTEN 10.255.255.1 3493\n"
)
LEGACY_0007_UPSD_CONF = b"LISTEN 127.0.0.1 3493\n"
EXPECTED_UPSD_USERS = b"[monuser]\n    password = secret\n    upsmon secondary\n"


class SpkMetadataFixture(unittest.TestCase):
    def require_file(self, path: Path):
        self.assertTrue(path.is_file(), f"production artifact is missing: {path}")

    def temp_root(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return Path(temporary.name).resolve()

    def copy_script(self, source: Path, target: Path, replacements=()):
        self.require_file(source)
        text = source.read_text()
        for old, new in replacements:
            text = text.replace(old, new)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        target.chmod(0o755)

    def package_fixture(
        self,
        fail_publish_basename: str | None = None,
        publish_mode: str = "fail-before",
        fail_chmod_basename: str | None = None,
        dsm7_storage: bool = False,
    ):
        root = self.temp_root()
        package_root = root / "dsm/var/packages/nut-us3000"
        package_root.mkdir(parents=True)
        config_alias = package_root / "etc"
        package_dest = root / "package-target"
        if dsm7_storage:
            volume = root / "volume3"
            config_dir = volume / "@appconf/nut-us3000"
            package_var = volume / "@appdata/nut-us3000"
            config_dir.mkdir(parents=True)
            package_var.mkdir(parents=True)
            config_alias.symlink_to(config_dir, target_is_directory=True)
        else:
            config_dir = config_alias
            package_var = root / "package-var"
            package_var.mkdir()
        template_dest = package_dest / "share/nut-us3000/templates"
        template_dest.mkdir(parents=True)

        for name, expected in (
            ("ups.conf", EXPECTED_UPS_CONF),
            ("upsd.conf", EXPECTED_UPSD_CONF),
        ):
            source = TEMPLATES / name
            self.require_file(source)
            self.assertEqual(expected, source.read_bytes())
            shutil.copy2(source, template_dest / name)

        fixture_scripts = root / "scripts"
        for name in LIFECYCLE_NAMES:
            self.copy_script(
                SCRIPTS / name,
                fixture_scripts / name,
                (("/var/packages/nut-us3000/etc", str(config_alias)),),
            )

        helper = package_dest / "share/nut-us3000/lib.sh"
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text(
            "nutus3000_any_exact_package_pid() {\n"
            "    return \"${FIXTURE_PID_RESULT:-1}\"\n"
            "}\n"
        )

        hostctl_log = root / "hostctl.commands"
        hostctl_log.write_text("")
        hostctl = package_dest / "libexec/nut/nut-us3000-hostctl"
        hostctl.parent.mkdir(parents=True)
        hostctl.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "[ \"$#\" -eq 1 ] && [ \"$1\" = retire-port-config ] || exit 64\n"
            "printf '%s\\n' \"$1\" >> \"$HOSTCTL_LOG\"\n"
            "exit \"${HOSTCTL_RETIRE_RESULT:-0}\"\n"
        )
        hostctl.chmod(0o755)

        env = os.environ | {
            "HOSTCTL_LOG": str(hostctl_log),
            "SYNOPKG_PKGDEST": str(package_dest),
            "SYNOPKG_PKGVAR": str(package_var),
        }
        if fail_publish_basename is not None or fail_chmod_basename is not None:
            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
        if fail_publish_basename is not None:
            fake_publication = (
                "#!/bin/sh\n"
                "set -eu\n"
                "command_name=${0##*/}\n"
                "case $command_name in\n"
                "  mv) real_command=$REAL_MV;;\n"
                "  ln) real_command=$REAL_LN;;\n"
                "  *) exit 64;;\n"
                "esac\n"
                "for destination; do :; done\n"
                "if [ \"${destination##*/}\" = \"${FAIL_PUBLISH_BASENAME}\" ]; then\n"
                "  case $PUBLISH_MODE in\n"
                "    fail-before) exit 47;;\n"
                "    fail-after) \"$real_command\" \"$@\"; exit 47;;\n"
                "    race-file) printf 'raced target\\n' > \"$destination\";;\n"
                "    race-dangling) \"$REAL_LN\" -s \"$RACE_DANGLING_TARGET\" \"$destination\";;\n"
                "    substitute-parent)\n"
                "      \"$REAL_MV\" \"$SUBSTITUTE_PARENT\" \"$DISPLACED_PARENT\"\n"
                "      \"$REAL_LN\" -s \"$ALTERNATE_PARENT\" \"$SUBSTITUTE_PARENT\"\n"
                "      ;;\n"
                "    substitute-parent-directory)\n"
                "      \"$REAL_MV\" \"$SUBSTITUTE_PARENT\" \"$DISPLACED_PARENT\"\n"
                "      \"$REAL_MKDIR\" \"$SUBSTITUTE_PARENT\"\n"
                "      \"$REAL_CHMOD\" 711 \"$SUBSTITUTE_PARENT\"\n"
                "      LC_ALL=C \"$REAL_LS\" -id \"$SUBSTITUTE_PARENT\" > \"$FOREIGN_DIRECTORY_STATE\"\n"
                "      ;;\n"
                "    *) exit 64;;\n"
                "  esac\n"
                "fi\n"
                "exec \"$real_command\" \"$@\"\n"
            )
            for command in ("mv", "ln"):
                fake_command = fake_bin / command
                fake_command.write_text(fake_publication)
                fake_command.chmod(0o755)
            env |= {
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "FAIL_PUBLISH_BASENAME": fail_publish_basename,
                "PUBLISH_MODE": publish_mode,
                "REAL_MV": shutil.which("mv"),
                "REAL_LN": shutil.which("ln"),
                "REAL_MKDIR": shutil.which("mkdir"),
                "REAL_CHMOD": shutil.which("chmod"),
                "REAL_LS": shutil.which("ls"),
                "RACE_DANGLING_TARGET": str(root / "race-missing-target"),
            }
            if publish_mode == "substitute-parent":
                alternate_parent = root / "late-parent-alternate"
                alternate_parent.mkdir()
                if fail_publish_basename == "config-manifest.sha256":
                    substitute_parent = package_var
                    displaced_parent = root / "late-package-var-displaced"
                else:
                    substitute_parent = config_dir
                    displaced_parent = root / "late-config-displaced"
                env |= {
                    "SUBSTITUTE_PARENT": str(substitute_parent),
                    "DISPLACED_PARENT": str(displaced_parent),
                    "ALTERNATE_PARENT": str(alternate_parent),
                }
            elif publish_mode == "substitute-parent-directory":
                env |= {
                    "SUBSTITUTE_PARENT": str(config_dir),
                    "DISPLACED_PARENT": str(root / "late-config-displaced"),
                    "FOREIGN_DIRECTORY_STATE": str(root / "foreign-directory-state"),
                }
        if fail_chmod_basename is not None:
            fake_chmod = fake_bin / "chmod"
            fake_chmod.write_text(
                "#!/bin/sh\n"
                "set -eu\n"
                "for destination; do :; done\n"
                "if [ \"${destination##*/}\" = \"${FAIL_CHMOD_BASENAME}\" ]; then exit 48; fi\n"
                "exec \"$REAL_CHMOD\" \"$@\"\n"
            )
            fake_chmod.chmod(0o755)
            env |= {
                "PATH": f"{fake_bin}:{env['PATH']}",
                "FAIL_CHMOD_BASENAME": fail_chmod_basename,
                "REAL_CHMOD": shutil.which("chmod"),
            }
        return root, config_dir, package_dest, package_var, fixture_scripts, env

    @staticmethod
    def run_script(scripts: Path, name: str, env: dict[str, str]):
        return subprocess.run(
            ["/bin/sh", str(scripts / name)],
            text=True,
            capture_output=True,
            env=env,
        )

    def publish_fixture(self):
        fixture = self.package_fixture()
        root, config_dir, package_dest, package_var, scripts, env = fixture
        completed = self.run_script(scripts, "postinst", env)
        self.assertEqual(0, completed.returncode, completed.stderr)
        return fixture

    @staticmethod
    def write_manifest(config_dir: Path, package_var: Path):
        manifest = package_var / "config-manifest.sha256"
        manifest.write_bytes(
            b"".join(
                f"{hashlib.sha256((config_dir / name).read_bytes()).hexdigest()}  {name}\n".encode()
                for name in ("ups.conf", "upsd.conf", "upsd.users")
            )
        )
        manifest.chmod(0o600)

    def legacy_0007_fixture(
        self,
        fail_publish_basename: str | None = None,
        publish_mode: str = "fail-before",
        dsm7_storage: bool = False,
    ):
        fixture = self.package_fixture(
            fail_publish_basename=fail_publish_basename,
            publish_mode=publish_mode,
            dsm7_storage=dsm7_storage,
        )
        _, config_dir, _, package_var, _, _ = fixture
        config_dir.mkdir(parents=True, exist_ok=True)
        config_dir.chmod(0o750)
        for name, content, mode in (
            ("ups.conf", EXPECTED_UPS_CONF, 0o640),
            ("upsd.conf", LEGACY_0007_UPSD_CONF, 0o640),
            ("upsd.users", EXPECTED_UPSD_USERS, 0o600),
        ):
            target = config_dir / name
            target.write_bytes(content)
            target.chmod(mode)
        self.write_manifest(config_dir, package_var)
        return fixture

    @staticmethod
    def config_state(config_dir: Path, package_var: Path):
        state = {}
        for path in (
            config_dir / "ups.conf",
            config_dir / "upsd.conf",
            config_dir / "upsd.users",
            package_var / "config-manifest.sha256",
        ):
            state[path.name] = (
                path.read_bytes(),
                stat.S_IMODE(path.stat().st_mode),
                path.is_symlink(),
            )
        return state

    def assert_no_config_disclosure(self, completed):
        combined = (completed.stdout + completed.stderr).encode()
        for sensitive in (
            b"secret",
            b"[monuser]",
            b"LISTEN 127.0.0.1 3493",
            b"driver = usbhid-ups",
        ):
            self.assertNotIn(sensitive, combined)


class InfoAndPrivilegeTest(SpkMetadataFixture):
    def test_public_license_bundle_covers_hevtech_nut_libusb_and_spksrc(self):
        self.require_file(ROOT_LICENSE)
        self.require_file(LIBUSB_LICENSE)
        self.require_file(THIRD_PARTY_NOTICES)
        gpl = ROOT_LICENSE.read_text()
        lgpl = LIBUSB_LICENSE.read_text()
        notices = THIRD_PARTY_NOTICES.read_text()
        self.assertIn("GNU GENERAL PUBLIC LICENSE", gpl)
        self.assertIn("Version 2, June 1991", gpl)
        self.assertGreater(len(gpl), 17_000)
        self.assertIn("GNU LESSER GENERAL PUBLIC LICENSE", lgpl)
        self.assertIn("Version 2.1, February 1999", lgpl)
        self.assertGreater(len(lgpl), 23_000)
        for required in (
            "HEVTECH", "GPL-2.0-or-later", "NUT 2.8.5",
            "libusb 1.0.29", "LGPL-2.1-or-later", "SynoCommunity spksrc",
            "5c3cc7da1d4221d7e081ed2a31ba820b0455d4de",
            "nut-2.8.5.tar.gz", "libusb-1.0.29.tar.bz2",
        ):
            self.assertIn(required, notices)

    def test_public_native_sources_have_exact_hevtech_license_header(self):
        header = (
            "/*\n"
            " * Copyright (C) 2026 HEVTECH\n"
            " * SPDX-License-Identifier: GPL-2.0-or-later\n"
            " */\n"
        )
        for name in ("nut-us3000-controller.c", "nut-us3000-hostctl.c"):
            with self.subTest(name=name):
                source = PACKAGE / "native" / name
                self.require_file(source)
                self.assertTrue(source.read_text().startswith(header))

    def test_info_is_evaluated_by_pkg_dump_info_in_exact_field_order(self):
        root = self.temp_root()
        include = root / "pkgscripts/include/pkg_util.sh"
        include.parent.mkdir(parents=True)
        fields = tuple(EXPECTED_INFO)
        format_string = "\\n".join(f'{field}="%s"' for field in fields) + "\\n"
        arguments = " ".join(f'"${{{field}-}}"' for field in fields)
        include.write_text(
            "pkg_dump_info() {\n"
            "    [ \"$#\" -eq 0 ] || return 64\n"
            "    printf 'called\\n' > \"$PKG_DUMP_MARKER\"\n"
            f"    printf '{format_string}' {arguments}\n"
            "}\n"
        )
        fixture_info = root / "INFO.sh"
        self.copy_script(
            INFO_SCRIPT,
            fixture_info,
            (("/pkgscripts/include/pkg_util.sh", str(include)),),
        )

        marker = root / "pkg-dump-called"
        completed = subprocess.run(
            ["/bin/sh", str(fixture_info)],
            text=True,
            capture_output=True,
            env=os.environ | {"PKG_DUMP_MARKER": str(marker)},
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(
            "".join(f'{key}="{value}"\n' for key, value in EXPECTED_INFO.items()),
            completed.stdout,
        )
        self.assertEqual("", completed.stderr)
        self.assertEqual("called\n", marker.read_text())

    def test_privilege_keeps_package_default_and_declares_only_exact_tools(self):
        self.require_file(PRIVILEGE)
        privilege = json.loads(PRIVILEGE.read_text())
        self.assertEqual(
            {
                "defaults": {"run-as": "package"},
                "username": "nutus3000",
                "groupname": "nutus3000",
                "tool": [
                    {
                        "relpath": "libexec/nut/usbhid-ups",
                        "user": "package",
                        "group": "package",
                        "permission": "0750",
                    },
                    {
                        "relpath": "libexec/nut/nut-us3000-hostctl",
                        "user": "root",
                        "group": "package",
                        "permission": "6550",
                    },
                    {
                        "relpath": "libexec/nut/nut-us3000-controller",
                        "user": "package",
                        "group": "package",
                        "permission": "0750",
                    },
                ],
            },
            privilege,
        )
        self.assertNotIn("capabilities", json.dumps(privilege, sort_keys=True))

    def test_package_omits_firewall_port_metadata_to_avoid_dsm_allow_prompt(self):
        self.assertFalse(
            PORT_CONFIG.exists() or PORT_CONFIG.is_symlink(),
            "DSM port metadata must stay absent so Package Center cannot offer LAN access to 3493",
        )

    def test_wizards_are_static_valid_localized_guidance_without_commands(self):
        expected = {
            "install_uifile", "install_uifile_rus",
            "upgrade_uifile", "upgrade_uifile_rus",
            "uninstall_uifile", "uninstall_uifile_rus",
        }
        self.assertTrue(WIZARDS.is_dir())
        self.assertEqual(expected, {path.name for path in WIZARDS.iterdir()})
        combined = ""
        for name in sorted(expected):
            path = WIZARDS / name
            value = json.loads(path.read_text())
            self.assertIsInstance(value, list)
            self.assertTrue(value)
            combined += path.read_text().lower()
        for required in ("10.255.255.1", "3493", "usb", "firewall"):
            self.assertIn(required, combined)
        for forbidden in ("sudo ", "iptables", "synofirewall", "/usr/syno/etc/firewall"):
            self.assertNotIn(forbidden, combined)

        for forbidden in (
            "0011", "0012", "rollback", "hybrid guard", "transient",
            "capability helper", "capabilities", "monuser", "secret",
        ):
            self.assertNotIn(forbidden, combined)

    def test_help_topology_and_localized_user_copy_cover_the_final_contract(self):
        expected = {
            "helptoc.conf",
            "help/enu/nut-us3000.html",
            "help/rus/nut-us3000.html",
            "texts/enu/strings",
            "texts/rus/strings",
        }
        self.assertEqual(
            expected,
            {str(path.relative_to(APP_PAYLOAD)) for path in APP_PAYLOAD.rglob("*") if path.is_file()},
        )
        toc = json.loads((APP_PAYLOAD / "helptoc.conf").read_text())
        self.assertEqual("SYNO.SDS.NUTUS3000", toc.get("app"))
        self.assertEqual("app_tree:index_title", toc.get("title"))
        self.assertEqual("nut-us3000.html", toc.get("content"))
        self.assertEqual([], toc.get("toc"))

        english = "\n".join((
            (APP_PAYLOAD / "help/enu/nut-us3000.html").read_text(),
            (APP_PAYLOAD / "texts/enu/strings").read_text(),
            *(path.read_text() for path in WIZARDS.glob("*_uifile") if not path.name.endswith("_rus")),
        )).lower()
        russian = "\n".join((
            (APP_PAYLOAD / "help/rus/nut-us3000.html").read_text(),
            (APP_PAYLOAD / "texts/rus/strings").read_text(),
            *(path.read_text() for path in WIZARDS.glob("*_uifile_rus")),
        )).lower()
        for token in (
            "ugreen us3000", "2b89:ffff", "10.255.255.1:3493",
            "synology ups server", "10 minutes", "package center",
            "controller", "dsm ups", "notifications", "keep", "delete",
        ):
            self.assertIn(token, english)
        for token in (
            "ugreen us3000", "2b89:ffff", "10.255.255.1:3493",
            "сервер ибп synology", "10 минут", "центр пакетов",
            "контроллер", "ибп dsm", "уведомлен", "сохран", "удал",
        ):
            self.assertIn(token, russian)
        combined = english + russian
        self.assertIn("dsm 7.2.2-72806", english)
        self.assertIn("dsm 7.2.2-72806", russian)
        for forbidden in (
            "0011", "0012", "rollback", "debug", "hybrid", "transient",
            "monuser", "secret", "password", "smtp",
            "later dsm 7.2 updates", "последующие обновления dsm 7.2",
        ):
            self.assertNotIn(forbidden, combined)

    def test_uninstall_wizards_offer_one_exclusive_keep_or_delete_choice(self):
        for name in ("uninstall_uifile", "uninstall_uifile_rus"):
            with self.subTest(name=name):
                document = json.loads((WIZARDS / name).read_text())
                selectors = [
                    item
                    for step in document
                    for item in step.get("items", [])
                    if item.get("type") == "singleselect"
                ]
                self.assertEqual(1, len(selectors))
                subitems = selectors[0].get("subitems")
                self.assertEqual(
                    ["wizard_keep_data", "wizard_delete_data"],
                    [item.get("key") for item in subitems],
                )
                self.assertEqual([True, False], [item.get("defaultValue") for item in subitems])
                self.assertEqual(1, sum(item.get("defaultValue") is True for item in subitems))

    def test_lifecycle_scripts_have_no_forbidden_dsm_nut_paths_or_root_override(self):
        forbidden = (
            "/usr/syno/bin/synoups",
            "/usr/syno/etc/ups",
            "/etc/ups",
            '"run-as": "root"',
            "'run-as': 'root'",
            "sudo",
            "spm-exec",
        )
        for name in LIFECYCLE_NAMES:
            with self.subTest(name=name):
                path = SCRIPTS / name
                self.require_file(path)
                text = path.read_text()
                for token in forbidden:
                    self.assertNotIn(token, text)


class TemplateAndPublicationTest(SpkMetadataFixture):
    def test_postinst_retires_legacy_port_config_before_fresh_publication(self):
        root, config_dir, _, package_var, scripts, env = self.package_fixture()

        completed = self.run_script(scripts, "postinst", env)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("retire-port-config\n", (root / "hostctl.commands").read_text())
        self.assertTrue((config_dir / "ups.conf").is_file())
        self.assertTrue((package_var / "config-manifest.sha256").is_file())

    def test_postinst_retirement_failure_prevents_fresh_config_publication(self):
        root, config_dir, _, package_var, scripts, env = self.package_fixture()
        env["HOSTCTL_RETIRE_RESULT"] = "1"

        completed = self.run_script(scripts, "postinst", env)

        self.assertNotEqual(0, completed.returncode)
        self.assertEqual("retire-port-config\n", (root / "hostctl.commands").read_text())
        self.assertFalse(config_dir.exists())
        self.assertFalse((package_var / "config-manifest.sha256").exists())

    def test_postinst_retirement_runs_before_existing_publication_early_exit(self):
        root, config_dir, _, package_var, scripts, env = self.package_fixture()
        published = self.run_script(scripts, "postinst", env)
        self.assertEqual(0, published.returncode, published.stderr)
        before = self.config_state(config_dir, package_var)
        (root / "hostctl.commands").write_text("")
        env["HOSTCTL_RETIRE_RESULT"] = "1"

        repeated = self.run_script(scripts, "postinst", env)

        self.assertNotEqual(0, repeated.returncode)
        self.assertEqual("retire-port-config\n", (root / "hostctl.commands").read_text())
        self.assertEqual(before, self.config_state(config_dir, package_var))

    def test_templates_are_byte_exact(self):
        for name, expected in (
            ("ups.conf", EXPECTED_UPS_CONF),
            ("upsd.conf", EXPECTED_UPSD_CONF),
        ):
            with self.subTest(name=name):
                path = TEMPLATES / name
                self.require_file(path)
                self.assertEqual(expected, path.read_bytes())

    def test_first_publication_writes_exact_bytes_modes_and_private_manifest(self):
        _, config_dir, _, package_var, scripts, env = self.package_fixture()
        completed = self.run_script(scripts, "postinst", env)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("", completed.stdout)
        self.assert_no_config_disclosure(completed)
        self.assertEqual(0o750, stat.S_IMODE(config_dir.stat().st_mode))
        expected = {
            "ups.conf": (EXPECTED_UPS_CONF, 0o640),
            "upsd.conf": (EXPECTED_UPSD_CONF, 0o640),
            "upsd.users": (EXPECTED_UPSD_USERS, 0o600),
        }
        for name, (content, mode) in expected.items():
            path = config_dir / name
            self.assertEqual(content, path.read_bytes())
            self.assertEqual(mode, stat.S_IMODE(path.stat().st_mode))
            self.assertFalse(path.is_symlink())

        manifest = package_var / "config-manifest.sha256"
        self.assertFalse(manifest.is_symlink())
        self.assertEqual(0o600, stat.S_IMODE(manifest.stat().st_mode))
        expected_manifest = "".join(
            f"{hashlib.sha256(content).hexdigest()}  {name}\n"
            for name, (content, _) in expected.items()
        ).encode()
        self.assertEqual(expected_manifest, manifest.read_bytes())
        self.assertNotIn(b"secret", manifest.read_bytes())

    def test_dsm7_config_alias_publishes_into_appconf(self):
        root, config_dir, _, package_var, scripts, env = self.package_fixture(
            dsm7_storage=True
        )
        config_alias = root / "dsm/var/packages/nut-us3000/etc"
        self.assertTrue(config_alias.is_symlink())

        completed = self.run_script(scripts, "postinst", env)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(0o750, stat.S_IMODE(config_dir.stat().st_mode))
        self.assertEqual(EXPECTED_UPS_CONF, (config_dir / "ups.conf").read_bytes())
        self.assertEqual(EXPECTED_UPSD_CONF, (config_dir / "upsd.conf").read_bytes())
        self.assertEqual(EXPECTED_UPSD_USERS, (config_dir / "upsd.users").read_bytes())
        self.assertTrue((package_var / "config-manifest.sha256").is_file())
        self.assertEqual([], list(config_dir.glob(".nut-us3000-postinst.*")))
        self.assert_no_config_disclosure(completed)

    def test_postinst_accepts_only_exact_complete_existing_publication_without_mutation(self):
        for dsm7_storage in (False, True):
            with self.subTest(dsm7_storage=dsm7_storage):
                fixture = self.package_fixture(dsm7_storage=dsm7_storage)
                root, config_dir, _, package_var, scripts, env = fixture
                first = self.run_script(scripts, "postinst", env)
                self.assertEqual(0, first.returncode, first.stderr)
                before = self.config_state(config_dir, package_var)

                repeated = self.run_script(scripts, "postinst", env)

                self.assertEqual(0, repeated.returncode, repeated.stderr)
                self.assertEqual(before, self.config_state(config_dir, package_var))
                self.assertEqual([], list(config_dir.glob(".nut-us3000-postinst.*")))
                self.assertEqual([], list(package_var.glob(".nut-us3000-postinst.*")))
                self.assert_no_config_disclosure(repeated)

    def test_postinst_migrates_only_exact_0007_upsd_conf_and_manifest(self):
        for dsm7_storage in (False, True):
            with self.subTest(dsm7_storage=dsm7_storage):
                fixture = self.legacy_0007_fixture(dsm7_storage=dsm7_storage)
                _, config_dir, _, package_var, scripts, env = fixture
                unchanged = {
                    name: (
                        (config_dir / name).read_bytes(),
                        (config_dir / name).stat().st_ino,
                        stat.S_IMODE((config_dir / name).stat().st_mode),
                    )
                    for name in ("ups.conf", "upsd.users")
                }

                preupgrade = self.run_script(scripts, "preupgrade", env)
                self.assertEqual(0, preupgrade.returncode, preupgrade.stderr)
                completed = self.run_script(scripts, "postinst", env)

                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertEqual(EXPECTED_UPSD_CONF, (config_dir / "upsd.conf").read_bytes())
                self.assertEqual(0o640, stat.S_IMODE((config_dir / "upsd.conf").stat().st_mode))
                for name, expected in unchanged.items():
                    target = config_dir / name
                    self.assertEqual(
                        expected,
                        (target.read_bytes(), target.stat().st_ino, stat.S_IMODE(target.stat().st_mode)),
                    )
                expected_manifest = b"".join(
                    f"{hashlib.sha256((config_dir / name).read_bytes()).hexdigest()}  {name}\n".encode()
                    for name in ("ups.conf", "upsd.conf", "upsd.users")
                )
                self.assertEqual(
                    expected_manifest,
                    (package_var / "config-manifest.sha256").read_bytes(),
                )
                self.assertEqual([], list(config_dir.glob(".nut-us3000-postinst.*")))
                self.assertEqual([], list(package_var.glob(".nut-us3000-postinst.*")))
                self.assert_no_config_disclosure(completed)

    def test_postinst_rejects_0007_like_modified_state_without_mutation(self):
        for mutation in ("ups-conf", "upsd-conf", "upsd-users"):
            with self.subTest(mutation=mutation):
                fixture = self.legacy_0007_fixture()
                _, config_dir, _, package_var, scripts, env = fixture
                target = config_dir / {
                    "ups-conf": "ups.conf",
                    "upsd-conf": "upsd.conf",
                    "upsd-users": "upsd.users",
                }[mutation]
                target.write_bytes(target.read_bytes() + b"modified\n")
                self.write_manifest(config_dir, package_var)
                before = self.config_state(config_dir, package_var)

                completed = self.run_script(scripts, "postinst", env)

                self.assertNotEqual(0, completed.returncode)
                self.assertEqual(before, self.config_state(config_dir, package_var))
                self.assertEqual([], list(config_dir.glob(".nut-us3000-postinst.*")))
                self.assertEqual([], list(package_var.glob(".nut-us3000-postinst.*")))
                self.assert_no_config_disclosure(completed)

    def test_0007_migration_replacement_failure_rolls_back_both_files(self):
        for phase in ("fail-before", "fail-after"):
            for basename in ("upsd.conf", "config-manifest.sha256"):
                with self.subTest(phase=phase, basename=basename):
                    fixture = self.legacy_0007_fixture(
                        fail_publish_basename=basename,
                        publish_mode=phase,
                    )
                    _, config_dir, _, package_var, scripts, env = fixture
                    before = self.config_state(config_dir, package_var)

                    completed = self.run_script(scripts, "postinst", env)

                    self.assertEqual(47, completed.returncode, completed.stderr)
                    self.assertEqual(before, self.config_state(config_dir, package_var))
                    self.assertEqual([], list(config_dir.glob(".nut-us3000-postinst.*")))
                    self.assertEqual([], list(package_var.glob(".nut-us3000-postinst.*")))
                    self.assert_no_config_disclosure(completed)

    def test_postinst_rejects_changed_complete_publication_without_mutation(self):
        for mutation in ("config-content", "config-mode", "manifest-content", "manifest-mode"):
            with self.subTest(mutation=mutation):
                _, config_dir, _, package_var, scripts, env = self.publish_fixture()
                if mutation == "config-content":
                    target = config_dir / "ups.conf"
                    target.write_bytes(target.read_bytes() + b"changed\n")
                elif mutation == "config-mode":
                    (config_dir / "upsd.conf").chmod(0o600)
                elif mutation == "manifest-content":
                    manifest = package_var / "config-manifest.sha256"
                    manifest.write_bytes(manifest.read_bytes() + b"changed\n")
                else:
                    (package_var / "config-manifest.sha256").chmod(0o640)
                before = self.config_state(config_dir, package_var)

                repeated = self.run_script(scripts, "postinst", env)

                self.assertNotEqual(0, repeated.returncode)
                self.assertEqual(before, self.config_state(config_dir, package_var))
                self.assertEqual([], list(config_dir.glob(".nut-us3000-postinst.*")))
                self.assertEqual([], list(package_var.glob(".nut-us3000-postinst.*")))
                self.assert_no_config_disclosure(repeated)

    def test_any_existing_config_name_is_never_overwritten(self):
        for name in ("ups.conf", "upsd.conf", "upsd.users"):
            for kind in ("file", "symlink", "dangling-symlink"):
                with self.subTest(name=name, kind=kind):
                    _, config_dir, _, package_var, scripts, env = self.package_fixture()
                    config_dir.mkdir()
                    target = config_dir / name
                    sentinel = config_dir / "sentinel"
                    sentinel.write_bytes(b"sentinel\n")
                    if kind == "file":
                        target.write_bytes(b"existing\n")
                    elif kind == "symlink":
                        target.symlink_to(sentinel)
                    else:
                        target.symlink_to(config_dir / "missing")
                    before = os.lstat(target)

                    completed = self.run_script(scripts, "postinst", env)
                    self.assertNotEqual(0, completed.returncode)
                    self.assertNotIn("secret", completed.stdout + completed.stderr)
                    after = os.lstat(target)
                    self.assertEqual((before.st_ino, before.st_mode), (after.st_ino, after.st_mode))
                    self.assertEqual(b"sentinel\n", sentinel.read_bytes())
                    for other in {"ups.conf", "upsd.conf", "upsd.users"} - {name}:
                        self.assertFalse((config_dir / other).exists())
                        self.assertFalse((config_dir / other).is_symlink())
                    self.assertFalse((package_var / "config-manifest.sha256").exists())

    def test_symlink_config_directory_or_parent_component_is_rejected(self):
        for kind in ("directory", "parent-component"):
            with self.subTest(kind=kind):
                root, config_dir, _, package_var, scripts, env = self.package_fixture()
                alternate = root / "alternate"
                alternate.mkdir()
                if kind == "directory":
                    config_dir.symlink_to(alternate, target_is_directory=True)
                else:
                    package_root = config_dir.parent
                    shutil.rmtree(package_root)
                    package_root.symlink_to(alternate, target_is_directory=True)

                completed = self.run_script(scripts, "postinst", env)
                self.assertNotEqual(0, completed.returncode)
                self.assertEqual([], list(alternate.iterdir()))
                self.assertFalse((package_var / "config-manifest.sha256").exists())
                self.assertNotIn("secret", completed.stdout + completed.stderr)

    def test_config_directory_chmod_failure_removes_new_directory_and_staging(self):
        root, config_dir, _, package_var, scripts, env = self.package_fixture(
            fail_chmod_basename="etc"
        )
        completed = self.run_script(scripts, "postinst", env)
        self.assertEqual(48, completed.returncode, completed.stderr)
        self.assertFalse(config_dir.exists())
        self.assertFalse((package_var / "config-manifest.sha256").exists())
        self.assertEqual([], list(config_dir.parent.glob(".nut-us3000-postinst.*")))
        self.assert_no_config_disclosure(completed)

    def test_symlink_or_nonregular_template_is_rejected_without_publication(self):
        for kind in ("symlink", "directory"):
            with self.subTest(kind=kind):
                _, config_dir, package_dest, package_var, scripts, env = self.package_fixture()
                template = package_dest / "share/nut-us3000/templates/ups.conf"
                template.unlink()
                if kind == "symlink":
                    template.symlink_to(package_dest / "missing")
                else:
                    template.mkdir()
                completed = self.run_script(scripts, "postinst", env)
                self.assertNotEqual(0, completed.returncode)
                self.assertFalse(config_dir.exists())
                self.assertFalse((package_var / "config-manifest.sha256").exists())
                self.assertNotIn("secret", completed.stdout + completed.stderr)

    def test_each_publication_failure_before_or_after_effect_rolls_back_our_inodes(self):
        for phase in ("fail-before", "fail-after"):
            for basename in (
                "ups.conf",
                "upsd.conf",
                "upsd.users",
                "config-manifest.sha256",
            ):
                with self.subTest(phase=phase, basename=basename):
                    _, config_dir, _, package_var, scripts, env = self.package_fixture(
                        basename, publish_mode=phase
                    )
                    completed = self.run_script(scripts, "postinst", env)
                    self.assertEqual(47, completed.returncode, completed.stderr)
                    self.assertFalse(config_dir.exists())
                    self.assertFalse((package_var / "config-manifest.sha256").exists())
                    self.assertEqual([], list(config_dir.parent.glob(".nut-us3000-postinst.*")))
                    self.assertEqual([], list(package_var.glob(".nut-us3000-postinst.*")))
                    self.assertNotIn("secret", completed.stdout + completed.stderr)

    def test_publication_time_file_or_dangling_target_is_preserved_without_siblings(self):
        names = ("ups.conf", "upsd.conf", "upsd.users", "config-manifest.sha256")
        for kind in ("race-file", "race-dangling"):
            for basename in names:
                with self.subTest(kind=kind, basename=basename):
                    _, config_dir, _, package_var, scripts, env = self.package_fixture(
                        basename, publish_mode=kind
                    )
                    completed = self.run_script(scripts, "postinst", env)
                    self.assertNotEqual(0, completed.returncode)
                    raced = (
                        package_var / basename
                        if basename == "config-manifest.sha256"
                        else config_dir / basename
                    )
                    if kind == "race-file":
                        self.assertEqual(b"raced target\n", raced.read_bytes())
                        self.assertFalse(raced.is_symlink())
                    else:
                        self.assertTrue(raced.is_symlink())
                        self.assertEqual(
                            Path(env["RACE_DANGLING_TARGET"]), Path(os.readlink(raced))
                        )
                    for other in names:
                        if other == basename:
                            continue
                        sibling = (
                            package_var / other
                            if other == "config-manifest.sha256"
                            else config_dir / other
                        )
                        self.assertFalse(sibling.exists())
                        self.assertFalse(sibling.is_symlink())
                    self.assertEqual([], list(config_dir.parent.glob(".nut-us3000-postinst.*")))
                    self.assertEqual([], list(package_var.glob(".nut-us3000-postinst.*")))
                    self.assertNotIn("secret", completed.stdout + completed.stderr)

    def test_late_config_or_manifest_parent_substitution_cannot_redirect_publication(self):
        for basename in (
            "ups.conf",
            "upsd.conf",
            "upsd.users",
            "config-manifest.sha256",
        ):
            with self.subTest(basename=basename):
                _, config_dir, _, package_var, scripts, env = self.package_fixture(
                    basename, publish_mode="substitute-parent"
                )
                completed = self.run_script(scripts, "postinst", env)
                self.assertNotEqual(0, completed.returncode)
                alternate = Path(env["ALTERNATE_PARENT"])
                displaced = Path(env["DISPLACED_PARENT"])
                self.assertEqual([], list(alternate.iterdir()))
                self.assertFalse((package_var / "config-manifest.sha256").exists())
                self.assertFalse((package_var / "config-manifest.sha256").is_symlink())
                for name in ("ups.conf", "upsd.conf", "upsd.users"):
                    candidate = displaced / name
                    self.assertFalse(candidate.exists())
                    self.assertFalse(candidate.is_symlink())
                self.assertEqual(
                    [],
                    list(displaced.glob(".nut-us3000-postinst.*"))
                    + list(alternate.glob(".nut-us3000-postinst.*")),
                )
                self.assertNotIn("secret", completed.stdout + completed.stderr)

    def test_cleanup_preserves_late_foreign_empty_config_directory(self):
        root, config_dir, _, package_var, scripts, env = self.package_fixture(
            "ups.conf", publish_mode="substitute-parent-directory"
        )
        completed = self.run_script(scripts, "postinst", env)
        self.assertNotEqual(0, completed.returncode)
        state_marker = Path(env["FOREIGN_DIRECTORY_STATE"])
        recorded_inode = int(state_marker.read_text().split(maxsplit=1)[0])
        self.assertTrue(config_dir.is_dir(), "foreign replacement directory was removed")
        replacement = os.lstat(config_dir)
        self.assertFalse(config_dir.is_symlink())
        self.assertTrue(config_dir.is_dir())
        self.assertEqual(recorded_inode, replacement.st_ino)
        self.assertEqual(0o711, stat.S_IMODE(replacement.st_mode))
        self.assertEqual([], list(config_dir.iterdir()))

        displaced = Path(env["DISPLACED_PARENT"])
        for name in ("ups.conf", "upsd.conf", "upsd.users"):
            candidate = displaced / name
            self.assertFalse(candidate.exists())
            self.assertFalse(candidate.is_symlink())
        self.assertFalse((package_var / "config-manifest.sha256").exists())
        self.assertFalse((package_var / "config-manifest.sha256").is_symlink())
        self.assertEqual([], list(config_dir.parent.glob(".nut-us3000-postinst.*")))
        self.assertEqual([], list(package_var.glob(".nut-us3000-postinst.*")))
        self.assertNotIn("secret", completed.stdout + completed.stderr)

    def test_existing_manifest_blocks_publication_without_mutation(self):
        _, config_dir, _, package_var, scripts, env = self.package_fixture()
        manifest = package_var / "config-manifest.sha256"
        manifest.write_bytes(b"existing manifest\n")
        manifest.chmod(0o600)
        completed = self.run_script(scripts, "postinst", env)
        self.assertNotEqual(0, completed.returncode)
        self.assertEqual(b"existing manifest\n", manifest.read_bytes())
        self.assertFalse(config_dir.exists())


class UpgradeAndUninstallTest(SpkMetadataFixture):
    def test_preupgrade_accepts_exact_manifest_and_postupgrade_preserves_every_byte(self):
        _, config_dir, _, package_var, scripts, env = self.publish_fixture()
        before = self.config_state(config_dir, package_var)
        pre = self.run_script(scripts, "preupgrade", env)
        self.assertEqual(0, pre.returncode, pre.stderr)
        post = self.run_script(scripts, "postupgrade", env)
        self.assertEqual(0, post.returncode, post.stderr)
        self.assertEqual(before, self.config_state(config_dir, package_var))
        self.assertNotIn("secret", pre.stdout + pre.stderr + post.stdout + post.stderr)

    def test_preupgrade_accepts_dsm7_config_alias_without_mutation(self):
        fixture = self.package_fixture(dsm7_storage=True)
        _, config_dir, _, package_var, scripts, env = fixture
        published = self.run_script(scripts, "postinst", env)
        self.assertEqual(0, published.returncode, published.stderr)
        before = self.config_state(config_dir, package_var)

        completed = self.run_script(scripts, "preupgrade", env)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(before, self.config_state(config_dir, package_var))
        self.assertNotIn("secret", completed.stdout + completed.stderr)

    def test_preupgrade_rejects_each_changed_config_without_mutation(self):
        for name in ("ups.conf", "upsd.conf", "upsd.users"):
            with self.subTest(name=name):
                _, config_dir, _, package_var, scripts, env = self.publish_fixture()
                target = config_dir / name
                target.write_bytes(target.read_bytes() + b"changed\n")
                before = self.config_state(config_dir, package_var)
                completed = self.run_script(scripts, "preupgrade", env)
                self.assertNotEqual(0, completed.returncode)
                self.assertEqual(before, self.config_state(config_dir, package_var))
                self.assertNotIn("secret", completed.stdout + completed.stderr)

    def test_preupgrade_rejects_nonregular_or_symlink_config_and_manifest(self):
        cases = (
            ("config-symlink", "ups.conf"),
            ("config-directory", "upsd.conf"),
            ("manifest-symlink", "config-manifest.sha256"),
            ("manifest-directory", "config-manifest.sha256"),
        )
        for kind, name in cases:
            with self.subTest(kind=kind):
                _, config_dir, _, package_var, scripts, env = self.publish_fixture()
                target = (package_var if name == "config-manifest.sha256" else config_dir) / name
                saved = target.read_bytes()
                target.unlink()
                if kind.endswith("symlink"):
                    replacement = target.parent / f"{name}.replacement"
                    replacement.write_bytes(saved)
                    target.symlink_to(replacement)
                else:
                    target.mkdir()
                completed = self.run_script(scripts, "preupgrade", env)
                self.assertNotEqual(0, completed.returncode)
                self.assertNotIn("secret", completed.stdout + completed.stderr)

    def test_preupgrade_rejects_nonprivate_or_nonstrict_manifest(self):
        for kind in ("mode", "extra-line", "reordered"):
            with self.subTest(kind=kind):
                _, _, _, package_var, scripts, env = self.publish_fixture()
                manifest = package_var / "config-manifest.sha256"
                if kind == "mode":
                    manifest.chmod(0o640)
                elif kind == "extra-line":
                    manifest.write_bytes(manifest.read_bytes() + b"0" * 64 + b"  extra\n")
                else:
                    lines = manifest.read_bytes().splitlines(keepends=True)
                    manifest.write_bytes(b"".join(reversed(lines)))
                completed = self.run_script(scripts, "preupgrade", env)
                self.assertNotEqual(0, completed.returncode)
                self.assertNotIn("secret", completed.stdout + completed.stderr)

    def test_preupgrade_fails_closed_when_hash_tool_is_unavailable(self):
        root, _, _, _, scripts, env = self.publish_fixture()
        restricted_bin = root / "restricted-bin"
        restricted_bin.mkdir()
        for command in ("cmp", "ls", "mktemp", "rm"):
            resolved = shutil.which(command)
            self.assertIsNotNone(resolved)
            (restricted_bin / command).symlink_to(resolved)
        restricted_env = env | {"PATH": str(restricted_bin)}
        completed = self.run_script(scripts, "preupgrade", restricted_env)
        self.assertNotEqual(0, completed.returncode)
        self.assertNotIn("secret", completed.stdout + completed.stderr)

    def test_preuninst_uses_named_helper_and_fails_closed(self):
        for helper_result, expected in ((0, 1), (1, 0), (2, 1), (64, 1)):
            with self.subTest(helper_result=helper_result):
                _, _, _, _, scripts, env = self.package_fixture()
                completed = self.run_script(
                    scripts,
                    "preuninst",
                    env | {"FIXTURE_PID_RESULT": str(helper_result)},
                )
                self.assertEqual(expected, completed.returncode, completed.stderr)

        _, _, package_dest, _, scripts, env = self.package_fixture()
        (package_dest / "share/nut-us3000/lib.sh").unlink()
        completed = self.run_script(scripts, "preuninst", env)
        self.assertNotEqual(0, completed.returncode)

    def test_preuninst_never_uses_same_named_path_command_when_helper_omits_function(self):
        root, _, package_dest, _, scripts, env = self.package_fixture()
        helper = package_dest / "share/nut-us3000/lib.sh"
        helper.write_text("fixture_value=ordinary-sourced-library\n")
        marker = root / "path-collision-was-called"
        collision_bin = root / "collision-bin"
        collision_bin.mkdir()
        collision = collision_bin / "nutus3000_any_exact_package_pid"
        collision.write_text(
            "#!/bin/sh\n"
            "printf 'called\\n' > \"$PATH_COLLISION_MARKER\"\n"
            "exit 1\n"
        )
        collision.chmod(0o755)
        completed = self.run_script(
            scripts,
            "preuninst",
            env
            | {
                "PATH": f"{collision_bin}:{env['PATH']}",
                "PATH_COLLISION_MARKER": str(marker),
            },
        )
        self.assertNotEqual(0, completed.returncode)
        self.assertFalse(marker.exists())

    def test_noop_lifecycle_scripts_succeed_without_touching_config(self):
        _, config_dir, _, package_var, scripts, env = self.publish_fixture()
        before = self.config_state(config_dir, package_var)
        for name in ("preinst", "postuninst", "postupgrade"):
            with self.subTest(name=name):
                completed = self.run_script(scripts, name, env)
                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertEqual("", completed.stdout)
                self.assertEqual(before, self.config_state(config_dir, package_var))


class IconGenerationTest(SpkMetadataFixture):
    @staticmethod
    def parse_png(path: Path):
        data = path.read_bytes()
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise AssertionError("not a PNG")
        chunks = []
        offset = 8
        while offset < len(data):
            length = struct.unpack(">I", data[offset : offset + 4])[0]
            chunk_type = data[offset + 4 : offset + 8]
            payload = data[offset + 8 : offset + 8 + length]
            crc = struct.unpack(">I", data[offset + 8 + length : offset + 12 + length])[0]
            if crc != zlib.crc32(chunk_type + payload) & 0xFFFFFFFF:
                raise AssertionError("invalid PNG CRC")
            chunks.append((chunk_type, payload))
            offset += length + 12
        if offset != len(data):
            raise AssertionError("trailing PNG bytes")
        return chunks

    def run_generator(self, output_dir: Path):
        self.require_file(ICON_GENERATOR)
        return subprocess.run(
            ["python3", str(ICON_GENERATOR), str(output_dir)],
            text=True,
            capture_output=True,
        )

    def test_icons_are_deterministic_rgb_pngs_with_fixed_dimensions_and_pixels(self):
        root = self.temp_root()
        first = root / "first"
        second = root / "second"
        first.mkdir()
        second.mkdir()
        for output in (first, second):
            completed = self.run_generator(output)
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual("", completed.stdout)
            self.assertEqual(
                {"PACKAGE_ICON.PNG", "PACKAGE_ICON_256.PNG"},
                {path.name for path in output.iterdir()},
            )

        for name, size in (("PACKAGE_ICON.PNG", 64), ("PACKAGE_ICON_256.PNG", 256)):
            first_bytes = (first / name).read_bytes()
            self.assertEqual(first_bytes, (second / name).read_bytes())
            expected_hash = {
                "PACKAGE_ICON.PNG": "c92bd67ea26cb5b1e8f4714a3648e7c37dc012e04a7922f76b2bc51913cfb6dd",
                "PACKAGE_ICON_256.PNG": "434584f959565d3a4ea3fcc965383d8379de7edef4f1f9a7feb68df43494b02e",
            }[name]
            self.assertEqual(expected_hash, hashlib.sha256(first_bytes).hexdigest())
            chunks = self.parse_png(first / name)
            self.assertEqual([b"IHDR", b"IDAT", b"IEND"], [kind for kind, _ in chunks])
            width, height, depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", chunks[0][1]
            )
            self.assertEqual((size, size, 8, 2, 0, 0, 0), (
                width, height, depth, color_type, compression, filtering, interlace
            ))
            rows = zlib.decompress(chunks[1][1])
            stride = 1 + size * 3
            self.assertEqual(stride * size, len(rows))
            self.assertTrue(all(rows[row * stride] == 0 for row in range(size)))

            def pixel(x, y):
                start = y * stride + 1 + x * 3
                return tuple(rows[start : start + 3])

            self.assertEqual((20, 42, 74), pixel(0, 0))
            self.assertEqual((63, 201, 123), pixel(size // 2, size // 8))
            self.assertEqual((232, 244, 238), pixel(size // 2, size // 3))
            self.assertEqual((63, 201, 123), pixel(size // 2, size // 2))
            self.assertEqual((20, 42, 74), pixel(size - 1, size - 1))
            colors = {
                tuple(rows[offset : offset + 3])
                for row in range(size)
                for offset in range(row * stride + 1, (row + 1) * stride, 3)
            }
            self.assertGreaterEqual(len(colors), 6)

    def test_existing_icon_or_symlink_refuses_all_publication(self):
        for name, kind in (
            ("PACKAGE_ICON.PNG", "file"),
            ("PACKAGE_ICON_256.PNG", "file"),
            ("PACKAGE_ICON.PNG", "dangling-symlink"),
            ("PACKAGE_ICON_256.PNG", "dangling-symlink"),
        ):
            with self.subTest(name=name, kind=kind):
                root = self.temp_root()
                output = root / "icons"
                output.mkdir()
                target = output / name
                if kind == "file":
                    target.write_bytes(b"existing icon\n")
                else:
                    target.symlink_to(output / "missing")
                completed = self.run_generator(output)
                self.assertNotEqual(0, completed.returncode)
                other = output / (
                    "PACKAGE_ICON_256.PNG" if name == "PACKAGE_ICON.PNG" else "PACKAGE_ICON.PNG"
                )
                self.assertFalse(other.exists())
                self.assertFalse(other.is_symlink())
                if kind == "file":
                    self.assertEqual(b"existing icon\n", target.read_bytes())
                else:
                    self.assertTrue(target.is_symlink())

    def test_second_icon_publication_failure_rolls_back_first_and_staging(self):
        self.require_file(ICON_GENERATOR)
        root = self.temp_root()
        output = root / "icons"
        output.mkdir()
        specification = importlib.util.spec_from_file_location(
            "nut_us3000_generate_icons_fixture", ICON_GENERATOR
        )
        self.assertIsNotNone(specification)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        real_link = os.link
        calls = 0

        def fail_second_link(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected second publication failure")
            return real_link(source, target)

        module.os.link = fail_second_link
        try:
            result = module.main([str(ICON_GENERATOR), str(output)])
        finally:
            module.os.link = real_link
        self.assertEqual(1, result)
        self.assertEqual([], list(output.iterdir()))


if __name__ == "__main__":
    unittest.main()
