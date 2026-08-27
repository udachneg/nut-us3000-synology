from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "spk/package"
OVERLAY = ROOT / "spk/spksrc-overlay"
LICENSE_SOURCE = OVERLAY / "spk/nut-us3000/src/LICENSE"
BUILD_SCRIPT = ROOT / "spk/scripts/build-spksrc-spk.sh"
LOCK = ROOT / "spk/sources/spksrc.lock"
SPKSRC_COMMIT = "5c3cc7da1d4221d7e081ed2a31ba820b0455d4de"
LIFECYCLE_NAMES = (
    "preinst",
    "postinst",
    "preuninst",
    "postuninst",
    "preupgrade",
    "postupgrade",
)


class SpksrcPackagingTest(unittest.TestCase):
    def temp_root(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return Path(temporary.name).resolve()

    def require_file(self, path: Path):
        self.assertTrue(path.is_file(), f"required A1 artifact is missing: {path}")

    def test_lock_pins_current_spksrc_and_official_amd64_builder(self):
        self.require_file(LOCK)
        self.assertEqual(
            "SPKSRC_URL=https://github.com/SynoCommunity/spksrc.git\n"
            f"SPKSRC_COMMIT={SPKSRC_COMMIT}\n"
            "BUILDER_PLATFORM=linux/amd64\n"
            "BUILDER_IMAGE=ghcr.io/synocommunity/spksrc@"
            "sha256:deeef1a01210c914c43a7c18a40aee62885eeee041cc70e7bd1907153561cc94\n",
            LOCK.read_text(),
        )

    def test_nut_digests_are_exactly_the_three_hashes_required_by_spksrc(self):
        digests = OVERLAY / "cross/nut/digests"
        self.require_file(digests)
        self.assertEqual(
            "nut-2.8.5.tar.gz SHA1 be2a4b425cd65fd029a8a14a4fcdc1d7f8ed4896\n"
            "nut-2.8.5.tar.gz SHA256 18bf32e59eb764b13da3c4fa70384926d7fa584cb31d2fe7f137a570633eeec1\n"
            "nut-2.8.5.tar.gz MD5 5ad8ce61a788caf85cf62f301ba60e9f\n",
            digests.read_text(),
        )

    def create_public_project_fixture(self, root: Path) -> tuple[Path, Path]:
        project = root / "project"
        shutil.copytree(ROOT / "spk", project / "spk")
        (project / "artifacts").mkdir()
        (project / "artifacts/nut-2.8.5.tar.gz").write_bytes(b"fixture nut archive\n")
        (project / "artifacts/libusb-1.0.29.tar.bz2").write_bytes(b"fixture libusb archive\n")
        fake_sha = root / "fake-sha256sum"
        fake_sha.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "case ${1##*/} in\n"
            "  nut-2.8.5.tar.gz) sum=18bf32e59eb764b13da3c4fa70384926d7fa584cb31d2fe7f137a570633eeec1 ;;\n"
            "  libusb-1.0.29.tar.bz2) sum=5977fc950f8d1395ccea9bd48c06b3f808fd3c2c961b44b0c2e6e29fc3a70a85 ;;\n"
            "  nut-2.8.5.tar.gz.sig) sum=3211f48f7a312ae13770828d768a5e4d95c6866bfd96bf79df44665c8e6c85fb ;;\n"
            "  nut-key.gpg) sum=c12ead62f833ad128266c1a812d0b487a62929adf1e28859a2783c8dc1c7f2a0 ;;\n"
            "  *) exit 64 ;;\n"
            "esac\n"
            "printf '%s  %s\\n' \"$sum\" \"$1\"\n"
        )
        fake_sha.chmod(0o755)
        return project, fake_sha

    def test_package_normalizes_every_runtime_elf_rpath(self):
        recipe = OVERLAY / "spk/nut-us3000/Makefile"
        self.require_file(recipe)
        text = recipe.read_text()
        self.assertIn(
            "for elf in bin/upsc sbin/upsd sbin/upsdrvctl libexec/nut/usbhid-ups "
            "lib/libupsclient.so.7.1.0 lib/libusb-1.0.so.0.5.0; do \\\n"
            "\t\tpatchelf --set-rpath /var/packages/nut-us3000/target/lib "
            "$(STAGING_DIR)/$${elf}; \\\n"
            "\tdone\n",
            text,
        )

    def test_package_restores_nonexecutable_modes_on_private_libraries(self):
        recipe = OVERLAY / "spk/nut-us3000/Makefile"
        self.require_file(recipe)
        text = recipe.read_text()
        self.assertIn(
            "chmod 644 $(STAGING_DIR)/lib/libupsclient.so.7.1.0 "
            "$(STAGING_DIR)/lib/libusb-1.0.so.0.5.0\n",
            text,
        )

    def test_package_cross_compiles_exact_native_helper_and_registers_safe_ux_resources(self):
        recipe = OVERLAY / "spk/nut-us3000/Makefile"
        self.require_file(recipe)
        text = recipe.read_text()
        self.assertIn("SPK_REV = 0015\n", text)
        self.assertNotIn("OS_MAX_VER", text)
        self.assertIn("DESCRIPTION_RUS = Нативный USB-драйвер и локальный NUT 2.8.5 для UGREEN US3000.\n", text)
        self.assertNotIn("FWPORTS", text)
        self.assertIn("WIZARDS_DIR = src/wizard\n", text)
        self.assertNotIn(
            "SERVICE_TARGET = nut_us3000_service_target\n",
            text,
            "overriding SERVICE_TARGET bypasses normal spksrc service resources",
        )
        self.assertIn("POST_SERVICE_TARGET = nut_us3000_service_finalize\n", text)
        self.assertIn(
            "$(TC_PATH)$(TC_PREFIX)gcc -std=c11 -Wall -Wextra -Werror -Os "
            "src/native/nut-us3000-hostctl.c -o "
            "$(STAGING_DIR)/libexec/nut/nut-us3000-hostctl\n",
            text,
        )
        self.assertIn(
            "$(TC_PATH)$(TC_PREFIX)gcc -std=c11 -Wall -Wextra -Werror -Os "
            "-D_POSIX_C_SOURCE=200809L "
            "src/native/nut-us3000-controller.c -o "
            "$(STAGING_DIR)/libexec/nut/nut-us3000-controller\n",
            text,
        )
        self.assertIn(
            "chmod 750 $(STAGING_DIR)/libexec/nut/nut-us3000-hostctl\n",
            text,
        )
        self.assertIn(
            "chmod 750 $(STAGING_DIR)/libexec/nut/nut-us3000-controller\n",
            text,
        )
        self.assertNotIn("patchelf --set-rpath /var/packages/nut-us3000/target/lib $(STAGING_DIR)/libexec/nut/nut-us3000-controller", text)

    def test_package_includes_complete_nut_and_libusb_license_texts(self):
        recipe = OVERLAY / "spk/nut-us3000/Makefile"
        self.require_file(recipe)
        self.require_file(LICENSE_SOURCE)
        self.assertIn("LICENSE_FILE = src/LICENSE\n", recipe.read_text())
        license_text = LICENSE_SOURCE.read_text()
        self.assertIn("NUT 2.8.5 licensing notice\n", license_text)
        self.assertIn("GNU GENERAL PUBLIC LICENSE", license_text)
        self.assertIn("Version 2, June 1991", license_text)
        self.assertIn("GNU LESSER GENERAL PUBLIC LICENSE", license_text)
        self.assertIn("Version 2.1, February 1999", license_text)
        self.assertGreater(len(license_text), 40_000)

    def test_service_finalize_places_exact_lifecycle_entrypoints_at_dsm_top_level(self):
        self.require_file(OVERLAY / "spk/nut-us3000/Makefile")
        root = self.temp_root()
        recipe = root / "spk/nut-us3000"
        scripts = root / "work/scripts"
        (root / "mk").mkdir()
        (recipe / "src/hooks").mkdir(parents=True)
        shutil.copy2(OVERLAY / "spk/nut-us3000/Makefile", recipe / "Makefile")
        scripts.mkdir(parents=True)
        for name in LIFECYCLE_NAMES:
            source = PACKAGE / "scripts" / name
            shutil.copy2(source, recipe / "src/hooks" / name)
            (scripts / name).write_text("generic wrapper\n")
        (root / "mk/spksrc.common.mk").write_text("")
        (root / "mk/spksrc.spk.mk").write_text(
            f"DSM_SCRIPTS_DIR := {scripts}\n"
            f"STAGING_DIR := {root / 'work/target'}\n"
        )
        completed = subprocess.run(
            ["/usr/bin/make", "-C", str(recipe), "nut_us3000_service_finalize"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        for name in LIFECYCLE_NAMES:
            self.assertEqual((PACKAGE / "scripts" / name).read_bytes(), (scripts / name).read_bytes())
            self.assertEqual(0o755, (scripts / name).stat().st_mode & 0o777)
        self.assertFalse((scripts / "hooks").exists())

    def test_build_prepares_canonical_overlay_and_invokes_exact_epyc7002_target(self):
        for required in (
            BUILD_SCRIPT,
            LOCK,
            OVERLAY / "cross/nut/Makefile",
            OVERLAY / "cross/nut/digests",
            OVERLAY / "cross/nut/PLIST",
            OVERLAY / "spk/nut-us3000/Makefile",
        ):
            self.require_file(required)

        root = self.temp_root()
        project, fake_sha = self.create_public_project_fixture(root)
        spksrc = root / "spksrc"
        output = root / "output"
        fake_bin = root / "fake-bin"
        spksrc.mkdir()
        output.mkdir()
        fake_bin.mkdir()
        (spksrc / "mk").mkdir()
        (spksrc / "mk/spksrc.spk.mk").write_text("fixture\n")
        (spksrc / "toolchain/syno-epyc7002-7.2").mkdir(parents=True)
        (spksrc / "toolchain/syno-epyc7002-7.2/Makefile").write_text("fixture\n")

        fake_git = fake_bin / "git"
        fake_git.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "[ $# -eq 4 ]\n"
            "[ \"$1\" = -C ]\n"
            "[ \"$3\" = rev-parse ]\n"
            "[ \"$4\" = HEAD ]\n"
            f"printf '%s\\n' {SPKSRC_COMMIT}\n"
        )
        fake_git.chmod(0o755)

        make_log = root / "make.log"
        fake_make = fake_bin / "make"
        fake_make.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "printf 'CALL_BEGIN\\n' >> \"$MAKE_LOG\"\n"
            "printf '%s\\n' \"$@\" >> \"$MAKE_LOG\"\n"
            "printf 'CALL_END\\n' >> \"$MAKE_LOG\"\n"
            "[ \"$1\" = -C ]\n"
            "case \"$2\" in\n"
            "  */toolchain/syno-epyc7002-7.2)\n"
            "    [ \"$3\" = toolchain ]\n"
            "    ;;\n"
            "  */spk/nut-us3000)\n"
            "    [ \"$3\" = ARCH=epyc7002 ]\n"
            "    [ \"$4\" = TCVERSION=7.2 ]\n"
            "    [ \"$5\" = package ]\n"
            "    root=$(cd \"$2/../..\" && pwd -P)\n"
            "    mkdir -p \"$root/packages\"\n"
            "    printf 'fixture spk\\n' > \"$root/packages/nut-us3000_epyc7002-7.2_2.8.5-0016.spk\"\n"
            "    ;;\n"
            "  *) exit 97 ;;\n"
            "esac\n"
        )
        fake_make.chmod(0o755)

        transformed = root / "build-spksrc-spk.sh"
        text = BUILD_SCRIPT.read_text()
        text = text.replace("GIT=/usr/bin/git", f"GIT={fake_git}")
        text = text.replace("MAKE=/usr/bin/make", f"MAKE={fake_make}")
        text = text.replace("/usr/bin/sha256sum", str(fake_sha))
        transformed.write_text(text)
        transformed.chmod(0o755)

        completed = subprocess.run(
            ["/bin/sh", str(transformed), str(project), str(spksrc), str(output)],
            env=os.environ | {"MAKE_LOG": str(make_log)},
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("SPKSRC_SPK_COMPLETE nut-us3000_epyc7002-7.2_2.8.5-0016.spk\n", completed.stdout)
        self.assertEqual(
            "CALL_BEGIN\n"
            "-C\n"
            f"{spksrc}/toolchain/syno-epyc7002-7.2\n"
            "toolchain\n"
            "CALL_END\n"
            "CALL_BEGIN\n"
            "-C\n"
            f"{spksrc}/spk/nut-us3000\n"
            "ARCH=epyc7002\n"
            "TCVERSION=7.2\n"
            "package\n"
            "CALL_END\n",
            make_log.read_text(),
        )

        for relative in (
            "cross/nut/Makefile",
            "cross/nut/digests",
            "cross/nut/PLIST",
            "spk/nut-us3000/Makefile",
        ):
            self.assertEqual((OVERLAY / relative).read_bytes(), (spksrc / relative).read_bytes())
        for name in LIFECYCLE_NAMES + ("start-stop-status",):
            prepared = spksrc / "spk/nut-us3000/src"
            destination = prepared / name if name == "start-stop-status" else prepared / "hooks" / name
            self.assertEqual((PACKAGE / "scripts" / name).read_bytes(), destination.read_bytes())
        for relative in (
            "conf/privilege",
            "native/nut-us3000-controller.c",
            "native/nut-us3000-hostctl.c",
            "payload/share/nut-us3000/lib.sh",
            "payload/share/nut-us3000/healthcheck.sh",
            "payload/share/nut-us3000/retry-step.sh",
            "templates/ups.conf",
            "templates/upsd.conf",
        ):
            self.assertEqual((PACKAGE / relative).read_bytes(), (spksrc / "spk/nut-us3000/src" / relative).read_bytes())
        prepared = spksrc / "spk/nut-us3000/src"
        self.assertFalse((prepared / "port-config").exists())
        for relative in (
            "helptoc.conf",
            "help/enu/nut-us3000.html",
            "help/rus/nut-us3000.html",
            "texts/enu/strings",
            "texts/rus/strings",
        ):
            self.assertEqual(
                (PACKAGE / "payload/app" / relative).read_bytes(),
                (spksrc / "spk/nut-us3000/src/payload/app" / relative).read_bytes(),
            )
        for name in (
            "install_uifile", "install_uifile_rus",
            "upgrade_uifile", "upgrade_uifile_rus",
            "uninstall_uifile", "uninstall_uifile_rus",
        ):
            self.assertEqual(
                (PACKAGE / "wizard" / name).read_bytes(),
                (spksrc / "spk/nut-us3000/src/wizard" / name).read_bytes(),
            )
        self.assertEqual(b"fixture spk\n", (output / "nut-us3000_epyc7002-7.2_2.8.5-0016.spk").read_bytes())
        self.assertFalse((output / ".nut-us3000-spksrc-build").exists())

    def test_build_rejects_mutated_verified_source_evidence_before_make(self):
        self.require_file(BUILD_SCRIPT)
        root = self.temp_root()
        project, fake_sha = self.create_public_project_fixture(root)
        spksrc = root / "spksrc"
        output = root / "output"
        fake_bin = root / "fake-bin"
        spksrc.mkdir()
        output.mkdir()
        fake_bin.mkdir()

        manifest = project / "spk/sources/source-manifest.sha256"
        manifest.write_text(manifest.read_text().replace("18bf32e5", "08bf32e5", 1))

        (spksrc / "mk").mkdir()
        (spksrc / "mk/spksrc.spk.mk").write_text("fixture\n")
        (spksrc / "toolchain/syno-epyc7002-7.2").mkdir(parents=True)
        (spksrc / "toolchain/syno-epyc7002-7.2/Makefile").write_text("fixture\n")
        fake_git = fake_bin / "git"
        fake_git.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' {SPKSRC_COMMIT}\n"
        )
        fake_git.chmod(0o755)
        make_marker = root / "make-was-called"
        fake_make = fake_bin / "make"
        fake_make.write_text(
            "#!/bin/sh\n"
            "printf 'called\\n' > \"$MAKE_MARKER\"\n"
            "exit 0\n"
        )
        fake_make.chmod(0o755)

        transformed = root / "build-spksrc-spk.sh"
        text = (project / "spk/scripts/build-spksrc-spk.sh").read_text()
        text = text.replace("GIT=/usr/bin/git", f"GIT={fake_git}")
        text = text.replace("MAKE=/usr/bin/make", f"MAKE={fake_make}")
        text = text.replace("/usr/bin/sha256sum", str(fake_sha))
        transformed.write_text(text)
        transformed.chmod(0o755)
        completed = subprocess.run(
            ["/bin/sh", str(transformed), str(project), str(spksrc), str(output)],
            env=os.environ | {"MAKE_MARKER": str(make_marker)},
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(0, completed.returncode)
        self.assertFalse(make_marker.exists())
        self.assertEqual([], list(output.glob("*.spk")))


if __name__ == "__main__":
    unittest.main()
