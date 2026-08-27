import hashlib
import io
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSPECTOR = ROOT / "spk/scripts/inspect-spk.py"
PACKAGE = ROOT / "spk/package"
OVERLAY = ROOT / "spk/spksrc-overlay/spk/nut-us3000"
HOOKS = ("preinst", "postinst", "preuninst", "postuninst", "preupgrade", "postupgrade")


class SpksrcArtifactTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nut-us3000-spk-artifact-", dir="/private/tmp")
        self.root = Path(self.temporary.name)
        self.inspection_count = 0
        self.fixture_count = 0
        self.readelf = self.root / "readelf"
        self.readelf.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "for argument do target=$argument; done\n"
            "machine='Advanced Micro Devices X86-64'\n"
            "[ \"${FAKE_ELF_MODE:-}\" != wrong-machine ] || machine='AArch64'\n"
            "printf '  Class:                             ELF64\\n'\n"
            "printf \"  Data:                              2's complement, little endian\\n\"\n"
            "printf '  Machine:                           %s\\n' \"$machine\"\n"
            "case $target in\n"
            "  */lib/*.so.*) : ;;\n"
            "  *) printf '      [Requesting program interpreter: /lib64/ld-linux-x86-64.so.2]\\n' ;;\n"
            "esac\n"
            "case $target in\n"
            "  */bin/upsc) needed='libupsclient.so.7 libc.so.6' ;;\n"
            "  */libexec/nut/nut-us3000-hostctl|*/libexec/nut/nut-us3000-controller) needed='libc.so.6' ;;\n"
            "  */libexec/nut/usbhid-ups) needed='libusb-1.0.so.0 libm.so.6 libc.so.6' ;;\n"
            "  */lib/libupsclient.so.7.1.0) needed='libc.so.6'; printf ' 0x000000000000000e (SONAME)             Library soname: [libupsclient.so.7]\\n' ;;\n"
            "  */lib/libusb-1.0.so.0.5.0) needed='libc.so.6 ld-linux-x86-64.so.2'; printf ' 0x000000000000000e (SONAME)             Library soname: [libusb-1.0.so.0]\\n' ;;\n"
            "  *) needed='libc.so.6' ;;\n"
            "esac\n"
            "for library in $needed; do printf ' 0x0000000000000001 (NEEDED)             Shared library: [%s]\\n' \"$library\"; done\n"
            "rpath=/var/packages/nut-us3000/target/lib\n"
            "[ \"${FAKE_ELF_MODE:-}\" != build-rpath ] || rpath=\"$rpath:/spksrc/work/install/lib\"\n"
            "case $target in\n"
            "  */libexec/nut/nut-us3000-hostctl) : ;;\n"
            "  */libexec/nut/nut-us3000-controller) [ \"${FAKE_ELF_MODE:-}\" != controller-rpath ] || printf ' 0x000000000000000f (RPATH)              Library rpath: [%s]\\n' \"$rpath\" ;;\n"
            "  *) printf ' 0x000000000000000f (RPATH)              Library rpath: [%s]\\n' \"$rpath\" ;;\n"
            "esac\n"
        )
        self.readelf.chmod(0o755)

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def add_directory(archive, name, mode=0o755):
        member = tarfile.TarInfo(name)
        member.type = tarfile.DIRTYPE
        member.mode = mode
        archive.addfile(member)

    @staticmethod
    def add_file(archive, name, data, mode=0o644):
        member = tarfile.TarInfo(name)
        member.size = len(data)
        member.mode = mode
        archive.addfile(member, io.BytesIO(data))

    @staticmethod
    def add_symlink(archive, name, target):
        member = tarfile.TarInfo(name)
        member.type = tarfile.SYMTYPE
        member.linkname = target
        # A native Linux spksrc build records runtime symlinks with the
        # conventional, semantically ignored 0777 link mode.
        member.mode = 0o777
        archive.addfile(member)

    def build_spk(self, *, arch="epyc7002", hook_mutation=False, extra_payload=False,
                  link_target="libupsclient.so.7.1.0", missing_arduino=False,
                  unsafe_outer=False, privilege_override=None):
        payload_stream = io.BytesIO()
        with tarfile.open(fileobj=payload_stream, mode="w:gz", format=tarfile.GNU_FORMAT) as payload:
            for directory in (
                "./app/", "./bin/", "./lib/", "./libexec/", "./libexec/nut/", "./sbin/",
                "./share/", "./share/nut-us3000/", "./share/nut-us3000/templates/",
                "./app/help/", "./app/help/enu/", "./app/help/rus/", "./app/texts/",
                "./app/texts/enu/", "./app/texts/rus/",
            ):
                self.add_directory(payload, directory)
            for name in ("bin/upsc", "sbin/upsd", "sbin/upsdrvctl"):
                self.add_file(payload, "./" + name, b"\x7fELF fixture " + name.encode(), 0o755)
            driver = b"\x7fELF fixture usbhid-ups"
            if not missing_arduino:
                driver += b" Arduino HID 0.22"
            self.add_file(payload, "./libexec/nut/usbhid-ups", driver, 0o755)
            self.add_file(payload, "./libexec/nut/nut-us3000-hostctl", b"\x7fELF fixture hostctl", 0o750)
            self.add_file(payload, "./libexec/nut/nut-us3000-controller", b"\x7fELF fixture controller", 0o750)
            self.add_file(payload, "./lib/libupsclient.so.7.1.0", b"\x7fELF upsclient", 0o644)
            self.add_symlink(payload, "./lib/libupsclient.so.7", link_target)
            self.add_file(payload, "./lib/libusb-1.0.so.0.5.0", b"\x7fELF libusb", 0o644)
            self.add_symlink(payload, "./lib/libusb-1.0.so.0", "libusb-1.0.so.0.5.0")
            self.add_file(payload, "./share/nut-us3000/lib.sh", (PACKAGE / "payload/share/nut-us3000/lib.sh").read_bytes(), 0o755)
            self.add_file(payload, "./share/nut-us3000/healthcheck.sh", (PACKAGE / "payload/share/nut-us3000/healthcheck.sh").read_bytes(), 0o755)
            self.add_file(payload, "./share/nut-us3000/retry-step.sh", (PACKAGE / "payload/share/nut-us3000/retry-step.sh").read_bytes(), 0o755)
            self.add_file(payload, "./share/nut-us3000/templates/ups.conf", (PACKAGE / "templates/ups.conf").read_bytes())
            self.add_file(payload, "./share/nut-us3000/templates/upsd.conf", (PACKAGE / "templates/upsd.conf").read_bytes())
            for relative in (
                "helptoc.conf", "help/enu/nut-us3000.html", "help/rus/nut-us3000.html",
                "texts/enu/strings", "texts/rus/strings",
            ):
                self.add_file(payload, "./app/" + relative, (PACKAGE / "payload/app" / relative).read_bytes())
            if extra_payload:
                self.add_file(payload, "./sbin/upsmon", b"\x7fELF extra", 0o755)
        package_bytes = payload_stream.getvalue()
        checksum = hashlib.md5(package_bytes).hexdigest()
        info = (
            'package="nut-us3000"\n'
            'version="2.8.5-0015"\n'
            'description="Native USB driver and host-local NUT 2.8.5 endpoint for UGREEN US3000."\n\n'
            'description_rus="Нативный USB-драйвер и локальный NUT 2.8.5 для UGREEN US3000."\n'
            f'arch="{arch}"\n'
            'maintainer="NUT US3000 local build"\n'
            'maintainer_url="https://networkupstools.org/"\n'
            'distributor=""\n'
            'distributor_url=""\n'
            'os_min_ver="7.2.2-72806"\n'
            'helpurl="https://networkupstools.org/"\n'
            'displayname="NUT US3000"\n'
            'dsmuidir="app"\n'
            'dsmappname="com.synocommunity.packages.nut-us3000"\n'
            'support_conf_folder="yes"\n'
            f'checksum="{checksum}"\n'
        ).encode()
        self.fixture_count += 1
        spk = self.root / f"fixture-{self.fixture_count:02d}.spk"
        with tarfile.open(spk, mode="w", format=tarfile.GNU_FORMAT) as outer:
            for directory in ("WIZARD_UIFILES/", "conf/", "scripts/"):
                self.add_directory(outer, directory)
            self.add_file(outer, "INFO", info)
            self.add_file(outer, "LICENSE", (OVERLAY / "src/LICENSE").read_bytes())
            self.add_file(outer, "PACKAGE_ICON.PNG", b"\x89PNG\r\n\x1a\nfixture")
            self.add_file(outer, "PACKAGE_ICON_256.PNG", b"\x89PNG\r\n\x1a\nfixture256")
            for name in (
                "install_uifile", "install_uifile_rus",
                "upgrade_uifile", "upgrade_uifile_rus",
                "uninstall_uifile", "uninstall_uifile_rus",
            ):
                self.add_file(outer, "WIZARD_UIFILES/" + name, (PACKAGE / "wizard" / name).read_bytes())
            privilege = (
                (PACKAGE / "conf/privilege").read_bytes()
                if privilege_override is None
                else privilege_override
            )
            self.add_file(outer, "conf/privilege", privilege)
            self.add_file(outer, "conf/resource", b"{}\n")
            self.add_file(outer, "package.tgz", package_bytes)
            self.add_file(outer, "scripts/functions", b"fixture functions\n", 0o755)
            self.add_file(outer, "scripts/installer", b"fixture generic installer\n", 0o755)
            self.add_file(outer, "scripts/service-setup", b"fixture service setup\n")
            self.add_file(outer, "scripts/start-stop-status", (PACKAGE / "scripts/start-stop-status").read_bytes(), 0o755)
            for name in HOOKS:
                hook = (PACKAGE / "scripts" / name).read_bytes()
                if hook_mutation and name == "preinst":
                    hook += b"# mutation\n"
                self.add_file(outer, "scripts/" + name, hook, 0o755)
            if unsafe_outer:
                self.add_file(outer, "../escape", b"unsafe")
        return spk

    def run_inspector(self, spk, *, elf_mode=""):
        self.assertTrue(INSPECTOR.is_file(), f"missing required A1 artifact: {INSPECTOR}")
        self.inspection_count += 1
        manifest = self.root / f"{spk.name}.{self.inspection_count}.manifest"
        completed = subprocess.run(
            [str(INSPECTOR), str(ROOT), str(spk), str(self.readelf), str(manifest)],
            env=os.environ | {"FAKE_ELF_MODE": elf_mode},
            text=True,
            capture_output=True,
            check=False,
        )
        return completed, manifest

    def test_exact_spk_is_accepted_and_manifest_is_stable(self):
        spk = self.build_spk()
        first, first_manifest = self.run_inspector(spk)
        self.assertEqual(0, first.returncode, first.stderr)
        first_bytes = first_manifest.read_bytes()
        second, second_manifest = self.run_inspector(spk)
        self.assertEqual(0, second.returncode, second.stderr)
        self.assertEqual(first_bytes, second_manifest.read_bytes())
        text = first_bytes.decode()
        self.assertIn("FORMAT=NUT_US3000_SPK_AUDIT_V2\n", text)
        self.assertIn("INFO_ARCH=epyc7002\n", text)
        self.assertIn("INFO_OS_MIN_VER=7.2.2-72806\n", text)
        self.assertIn("INFO_OS_MAX_VER=NONE\n", text)
        self.assertIn("PRIVILEGE_DEFAULT_RUN_AS=package\n", text)
        self.assertIn("HOSTCTL_ARCHIVE_MODE=0750\n", text)
        self.assertIn("HOSTCTL_INSTALL_USER=root\n", text)
        self.assertIn("HOSTCTL_INSTALL_GROUP=package\n", text)
        self.assertIn("HOSTCTL_INSTALL_PERMISSION=6550\n", text)
        self.assertIn("HOSTCTL_CAPABILITIES=NONE\n", text)
        self.assertIn("CONTROLLER_ARCHIVE_MODE=0750\n", text)
        self.assertIn("CONTROLLER_INSTALL_USER=package\n", text)
        self.assertIn("CONTROLLER_INSTALL_GROUP=package\n", text)
        self.assertIn("CONTROLLER_INSTALL_PERMISSION=0750\n", text)
        self.assertIn("ARDUINO_SUBDRIVER=Arduino HID 0.22\n", text)
        self.assertIn("PAYLOAD_FILE_COUNT=20\n", text)
        self.assertIn("ELF_COUNT=8\n", text)
        self.assertIn("ELF_003_PATH=libexec/nut/nut-us3000-controller\n", text)
        self.assertIn("ELF_003_RPATH=NONE\n", text)
        self.assertIn("ELF_003_NEEDED=libc.so.6\n", text)
        self.assertTrue(text.endswith("END=NUT_US3000_SPK_AUDIT_V2\n"))
        self.assertEqual("SPK_AUDIT_COMPLETE\n", first.stdout)

    def test_privilege_contract_mutations_are_rejected(self):
        canonical = (PACKAGE / "conf/privilege").read_text()
        mutations = (
            canonical.replace('"run-as": "package"', '"run-as": "root"'),
            canonical.replace(
                '"relpath": "libexec/nut/nut-us3000-hostctl",\n      "user": "root"',
                '"relpath": "libexec/nut/nut-us3000-hostctl",\n      "user": "package"',
            ),
            canonical.replace(
                '"user": "root",\n      "group": "package",\n      "permission": "6550"',
                '"user": "root",\n      "group": "root",\n      "permission": "6550"',
            ),
            canonical.replace('"permission": "6550"', '"permission": "0750"'),
            canonical.replace(
                '"permission": "6550"\n    }',
                '"permission": "6550",\n      "capabilities": ["cap_net_admin+ep"]\n    }',
            ),
        )
        for index, mutation in enumerate(mutations, start=1):
            with self.subTest(mutation=index):
                completed, manifest = self.run_inspector(
                    self.build_spk(privilege_override=mutation.encode())
                )
                self.assertNotEqual(0, completed.returncode)
                self.assertFalse(manifest.exists())

    def test_metadata_lifecycle_runtime_and_arduino_mutations_are_rejected(self):
        cases = (
            (self.build_spk(arch="x86_64"), ""),
            (self.build_spk(hook_mutation=True), ""),
            (self.build_spk(extra_payload=True), ""),
            (self.build_spk(link_target="../../escape"), ""),
            (self.build_spk(missing_arduino=True), ""),
        )
        for spk, mode in cases:
            with self.subTest(spk=spk.name):
                completed, manifest = self.run_inspector(spk, elf_mode=mode)
                self.assertNotEqual(0, completed.returncode)
                self.assertFalse(manifest.exists())

    def test_unsafe_outer_archive_and_wrong_elf_contract_are_rejected(self):
        cases = (
            (self.build_spk(unsafe_outer=True), ""),
            (self.build_spk(), "wrong-machine"),
            (self.build_spk(), "build-rpath"),
            (self.build_spk(), "controller-rpath"),
        )
        for spk, mode in cases:
            with self.subTest(mode=mode or "unsafe-outer"):
                completed, manifest = self.run_inspector(spk, elf_mode=mode)
                self.assertNotEqual(0, completed.returncode)
                self.assertFalse(manifest.exists())


if __name__ == "__main__":
    unittest.main()
