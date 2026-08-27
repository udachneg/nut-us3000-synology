from pathlib import Path
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "spk/package/native/nut-us3000-hostctl.c"
LEGACY_PORT_CONFIG = (
    b"[nut-us3000]\n"
    b'title="NUT US3000 (host-local)"\n'
    b'desc="Local DSM UPS integration endpoint"\n'
    b'port_forward="no"\n'
    b'dst.ports="3493/tcp"\n'
)


class NativeHostctlTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nut-us3000-hostctl-", dir="/private/tmp")
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def compile_helper(self, deny_root=False):
        self.assertTrue(SOURCE.is_file(), f"native helper source is missing: {SOURCE}")
        binary = self.root / "nut-us3000-hostctl"
        sysfs = self.root / "sys/bus/usb/devices"
        bind = self.root / "sys/bus/usb/drivers/usbhid/bind"
        ip = self.root / "ip"
        iptables = self.root / "iptables"
        legacy_service = self.root / "usr/local/etc/services.d/nut-us3000.sc"
        synofirewall = self.root / "synofirewall"
        sysfs.mkdir(parents=True)
        bind.parent.mkdir(parents=True)
        bind.write_text("")
        legacy_service.parent.mkdir(parents=True)
        legacy_service.parent.chmod(0o755)
        self.write_fake_ip(ip)
        self.write_fake_iptables(iptables)
        self.write_fake_synofirewall(synofirewall)
        defines = {
            "NUT_US3000_SYSFS_DEVICES": str(sysfs),
            "NUT_US3000_USBHID_BIND": str(bind),
            "NUT_US3000_IP": str(ip),
            "NUT_US3000_IPTABLES": str(iptables),
            "NUT_US3000_LEGACY_SERVICE": str(legacy_service),
            "NUT_US3000_SYNOFIREWALL": str(synofirewall),
        }
        command = ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-DNUT_US3000_TESTING=1"]
        command.append(f"-DNUT_US3000_SERVICE_DIR_OWNER={os.getuid()}")
        if deny_root:
            command.append("-DNUT_US3000_TEST_DENY_ROOT=1")
        command.extend(f'-D{name}="{value}"' for name, value in defines.items())
        command.extend([str(SOURCE), "-o", str(binary)])
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        return binary, sysfs, bind

    def write_fake_ip(self, path):
        alias = self.root / "alias.present"
        force_wrong_scope = self.root / "alias.force-wrong-scope"
        command_log = self.root / "ip.commands"
        path.write_text(
            "#!/bin/sh\n"
            "set -u\n"
            "[ \"${NUT_US3000_UNSAFE_TEST_VALUE+x}\" != x ] || exit 70\n"
            "[ \"${LC_ALL:-}\" = C ] || exit 71\n"
            "[ \"${PATH:-}\" = /usr/sbin:/usr/bin:/sbin:/bin ] || exit 72\n"
            f"state='{alias}'\n"
            f"force_wrong_scope='{force_wrong_scope}'\n"
            f"command_log='{command_log}'\n"
            "printf '%s\\n' \"$*\" >> \"$command_log\"\n"
            "case \"$*\" in\n"
            "  '-4 -o address show to 10.255.255.1/32')\n"
            "    [ ! -f \"$state\" ] || printf '1: lo inet 10.255.255.1/32 scope %s lo:nutus3000\\\\ valid_lft forever preferred_lft forever\\n' \"$(cat \"$state\")\"\n"
            "    exit 0 ;;\n"
            "  'address add 10.255.255.1/32 dev lo label lo:nutus3000 scope host')\n"
            "    if [ -f \"$force_wrong_scope\" ]; then printf 'global\\n' > \"$state\"; else printf 'host\\n' > \"$state\"; fi\n"
            "    exit 0 ;;\n"
            "  'address add 10.255.255.1/32 dev lo label lo:nutus3000') printf 'global\\n' > \"$state\"; exit 0 ;;\n"
            "  'address del 10.255.255.1/32 dev lo') rm -f \"$state\"; exit 0 ;;\n"
            "esac\n"
            "exit 64\n"
        )
        path.chmod(0o755)

    def write_fake_synofirewall(self, path):
        command_log = self.root / "synofirewall.commands"
        fail_reload = self.root / "synofirewall.fail-reload"
        path.write_text(
            "#!/bin/sh\n"
            "set -u\n"
            "[ \"${NUT_US3000_UNSAFE_TEST_VALUE+x}\" != x ] || exit 70\n"
            "[ \"${LC_ALL:-}\" = C ] || exit 71\n"
            "[ \"${PATH:-}\" = /usr/sbin:/usr/bin:/sbin:/bin ] || exit 72\n"
            f"command_log='{command_log}'\n"
            f"fail_reload='{fail_reload}'\n"
            "[ \"$*\" = --reload ] || exit 64\n"
            "printf '%s\\n' \"$*\" >> \"$command_log\"\n"
            "[ ! -f \"$fail_reload\" ] || exit 9\n"
            "exit 0\n"
        )
        path.chmod(0o755)

    def write_fake_iptables(self, path):
        guard = self.root / "guard.present"
        dsm_guard = self.root / "dsm-guard.present"
        fail_add = self.root / "guard.fail-add"
        exact = "! -i lo -d 10.255.255.1/32 -p tcp --dport 3493 -j DROP"
        dsm_exact = "-p tcp --dport 3493 -j DROP"
        path.write_text(
            "#!/bin/sh\n"
            "set -u\n"
            "[ \"${NUT_US3000_UNSAFE_TEST_VALUE+x}\" != x ] || exit 70\n"
            "[ \"${LC_ALL:-}\" = C ] || exit 71\n"
            "[ \"${PATH:-}\" = /usr/sbin:/usr/bin:/sbin:/bin ] || exit 72\n"
            f"state='{guard}'\n"
            f"dsm_state='{dsm_guard}'\n"
            f"fail_add='{fail_add}'\n"
            "case \"$*\" in\n"
            f"  '-C INPUT {exact}') [ -f \"$state\" ]; exit $? ;;\n"
            f"  '-C INPUT_FIREWALL {dsm_exact}') [ -f \"$dsm_state\" ]; exit $? ;;\n"
            f"  '-I INPUT 1 {exact}') [ ! -f \"$fail_add\" ] || exit 7; : > \"$state\"; exit 0 ;;\n"
            f"  '-D INPUT {exact}') rm -f \"$state\"; exit 0 ;;\n"
            "esac\n"
            "exit 64\n"
        )
        path.chmod(0o755)

    def run_helper(self, binary, command, env=None):
        return subprocess.run(
            [str(binary), command],
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    def test_source_has_no_runtime_path_override_or_shell_execution(self):
        self.assertTrue(SOURCE.is_file(), f"native helper source is missing: {SOURCE}")
        text = SOURCE.read_text()
        for forbidden in (
            "linux/capability.h", "sys/prctl.h", "SYS_capset", "CAP_NET_ADMIN",
            "PR_CAP_AMBIENT", "execv(", "getenv(", "system(", "popen(",
            "/bin/sh", "sudo", "spm-exec",
        ):
            self.assertNotIn(forbidden, text)
        for required in (
            '"2b89"', '"ffff"', '"DC600"', '"00"',
            '"10.255.255.1/32"', '"3493"',
            '"/usr/local/etc/services.d/nut-us3000.sc"',
            '"/usr/syno/bin/synofirewall"',
            "geteuid()", "setuid(0)", "getuid()", "execve(",
            "HOSTCTL_PRIVILEGE_OK",
        ):
            self.assertIn(required, text)

    def test_privilege_command_is_read_only(self):
        binary, _, _ = self.compile_helper()
        result = self.run_helper(binary, "privilege")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("HOSTCTL_PRIVILEGE_OK\n", result.stdout)
        self.assertFalse((self.root / "alias.present").exists())
        self.assertFalse((self.root / "guard.present").exists())

    def test_missing_root_identity_fails_before_any_host_mutation(self):
        binary, _, _ = self.compile_helper(deny_root=True)
        for action in ("privilege", "ensure", "audit", "release", "retire-port-config"):
            with self.subTest(action=action):
                result = self.run_helper(binary, action)
                self.assertEqual(77, result.returncode, result.stderr)
        self.assertFalse((self.root / "alias.present").exists())
        self.assertFalse((self.root / "guard.present").exists())

    def test_retire_port_config_is_noop_when_legacy_file_is_absent(self):
        binary, _, _ = self.compile_helper()

        retired = self.run_helper(binary, "retire-port-config")

        self.assertEqual(0, retired.returncode, retired.stderr)
        self.assertFalse((self.root / "synofirewall.commands").exists())

    def test_retire_port_config_removes_only_exact_legacy_file_and_reloads_firewall(self):
        binary, _, _ = self.compile_helper()
        legacy = self.root / "usr/local/etc/services.d/nut-us3000.sc"
        legacy.write_bytes(LEGACY_PORT_CONFIG)
        legacy.chmod(0o644)

        retired = self.run_helper(binary, "retire-port-config")

        self.assertEqual(0, retired.returncode, retired.stderr)
        self.assertFalse(legacy.exists())
        self.assertEqual("--reload\n", (self.root / "synofirewall.commands").read_text())

    def test_retire_port_config_rejects_changed_file_without_mutation_or_reload(self):
        binary, _, _ = self.compile_helper()
        legacy = self.root / "usr/local/etc/services.d/nut-us3000.sc"
        changed = LEGACY_PORT_CONFIG.replace(b"3493/tcp", b"3494/tcp")
        legacy.write_bytes(changed)

        retired = self.run_helper(binary, "retire-port-config")

        self.assertEqual(1, retired.returncode, retired.stderr)
        self.assertEqual(changed, legacy.read_bytes())
        self.assertFalse((self.root / "synofirewall.commands").exists())

    def test_retire_port_config_rejects_symlink_without_touching_target(self):
        binary, _, _ = self.compile_helper()
        target = self.root / "foreign-service"
        target.write_bytes(LEGACY_PORT_CONFIG)
        legacy = self.root / "usr/local/etc/services.d/nut-us3000.sc"
        legacy.symlink_to(target)

        retired = self.run_helper(binary, "retire-port-config")

        self.assertEqual(1, retired.returncode, retired.stderr)
        self.assertTrue(legacy.is_symlink())
        self.assertEqual(LEGACY_PORT_CONFIG, target.read_bytes())
        self.assertFalse((self.root / "synofirewall.commands").exists())

    def test_retire_port_config_rejects_untrusted_parent_without_mutation(self):
        binary, _, _ = self.compile_helper()
        legacy = self.root / "usr/local/etc/services.d/nut-us3000.sc"
        legacy.write_bytes(LEGACY_PORT_CONFIG)
        legacy.parent.chmod(0o777)

        retired = self.run_helper(binary, "retire-port-config")

        self.assertEqual(1, retired.returncode, retired.stderr)
        self.assertEqual(LEGACY_PORT_CONFIG, legacy.read_bytes())
        self.assertFalse((self.root / "synofirewall.commands").exists())

    def test_retire_port_config_fails_closed_if_firewall_reload_fails(self):
        binary, _, _ = self.compile_helper()
        legacy = self.root / "usr/local/etc/services.d/nut-us3000.sc"
        legacy.write_bytes(LEGACY_PORT_CONFIG)
        (self.root / "synofirewall.fail-reload").write_text("fail\n")

        retired = self.run_helper(binary, "retire-port-config")

        self.assertEqual(1, retired.returncode, retired.stderr)
        self.assertFalse(legacy.exists())
        self.assertEqual("--reload\n", (self.root / "synofirewall.commands").read_text())

    def test_retire_port_config_uses_only_fixed_safe_environment(self):
        binary, _, _ = self.compile_helper()
        legacy = self.root / "usr/local/etc/services.d/nut-us3000.sc"
        legacy.write_bytes(LEGACY_PORT_CONFIG)
        inherited = os.environ | {"NUT_US3000_UNSAFE_TEST_VALUE": "present"}

        retired = self.run_helper(binary, "retire-port-config", env=inherited)

        self.assertEqual(0, retired.returncode, retired.stderr)
        self.assertFalse(legacy.exists())

    def test_network_tools_receive_only_the_fixed_safe_environment(self):
        binary, _, _ = self.compile_helper()
        inherited = os.environ | {"NUT_US3000_UNSAFE_TEST_VALUE": "present"}
        result = self.run_helper(binary, "ensure", env=inherited)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((self.root / "alias.present").is_file())
        self.assertTrue((self.root / "guard.present").is_file())

    def test_ensure_audit_and_release_manage_only_exact_alias_and_guard(self):
        binary, _, _ = self.compile_helper()
        ensured = self.run_helper(binary, "ensure")
        self.assertEqual(0, ensured.returncode, ensured.stderr)
        self.assertTrue((self.root / "alias.present").is_file())
        self.assertEqual("host\n", (self.root / "alias.present").read_text())
        self.assertIn(
            "address add 10.255.255.1/32 dev lo label lo:nutus3000 scope host\n",
            (self.root / "ip.commands").read_text(),
        )
        self.assertTrue((self.root / "guard.present").is_file())
        audited = self.run_helper(binary, "audit")
        self.assertEqual(0, audited.returncode, audited.stderr)
        released = self.run_helper(binary, "release")
        self.assertEqual(0, released.returncode, released.stderr)
        self.assertFalse((self.root / "alias.present").exists())
        self.assertFalse((self.root / "guard.present").exists())

    def test_audit_accepts_dsm_managed_guard_after_transient_rule_is_reloaded(self):
        binary, _, _ = self.compile_helper()
        (self.root / "alias.present").write_text("host\n")
        (self.root / "dsm-guard.present").write_text("present\n")

        audited = self.run_helper(binary, "audit")

        self.assertEqual(0, audited.returncode, audited.stderr)
        self.assertFalse((self.root / "guard.present").exists())

    def test_audit_rejects_when_transient_and_dsm_managed_guards_are_absent(self):
        binary, _, _ = self.compile_helper()
        (self.root / "alias.present").write_text("host\n")

        audited = self.run_helper(binary, "audit")

        self.assertEqual(1, audited.returncode, audited.stderr)

    def test_ensure_keeps_early_transient_guard_when_dsm_managed_guard_exists(self):
        binary, _, _ = self.compile_helper()
        (self.root / "dsm-guard.present").write_text("present\n")

        ensured = self.run_helper(binary, "ensure")

        self.assertEqual(0, ensured.returncode, ensured.stderr)
        self.assertTrue((self.root / "guard.present").is_file())

    def test_release_removes_only_transient_guard_and_preserves_dsm_guard(self):
        binary, _, _ = self.compile_helper()
        ensured = self.run_helper(binary, "ensure")
        self.assertEqual(0, ensured.returncode, ensured.stderr)
        (self.root / "dsm-guard.present").write_text("present\n")

        released = self.run_helper(binary, "release")

        self.assertEqual(0, released.returncode, released.stderr)
        self.assertFalse((self.root / "guard.present").exists())
        self.assertTrue((self.root / "dsm-guard.present").is_file())

    def test_dsm_ip_one_line_escaped_label_is_accepted(self):
        binary, _, _ = self.compile_helper()

        ensured = self.run_helper(binary, "ensure")
        audited = self.run_helper(binary, "audit")

        self.assertEqual(0, ensured.returncode, ensured.stderr)
        self.assertEqual(0, audited.returncode, audited.stderr)

    def test_ensure_rolls_back_alias_if_exact_guard_cannot_be_added(self):
        binary, _, _ = self.compile_helper()
        (self.root / "guard.fail-add").write_text("fail\n")
        result = self.run_helper(binary, "ensure")
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertFalse((self.root / "alias.present").exists())
        self.assertFalse((self.root / "guard.present").exists())

    def test_ensure_removes_just_created_alias_if_post_add_validation_fails(self):
        binary, _, _ = self.compile_helper()
        (self.root / "alias.force-wrong-scope").write_text("global\n")

        result = self.run_helper(binary, "ensure")

        self.assertEqual(1, result.returncode, result.stderr)
        self.assertFalse((self.root / "alias.present").exists())
        self.assertFalse((self.root / "guard.present").exists())

    def test_release_accepts_absent_usb_but_rejects_foreign_interface_driver(self):
        binary, sysfs, _ = self.compile_helper()
        absent = self.run_helper(binary, "release")
        self.assertEqual(0, absent.returncode, absent.stderr)

        device = sysfs / "1-2"
        interface = sysfs / "1-2:1.0"
        device.mkdir()
        interface.mkdir()
        (device / "idVendor").write_text("2b89\n")
        (device / "idProduct").write_text("ffff\n")
        (device / "serial").write_text("DC600\n")
        (interface / "bInterfaceNumber").write_text("00\n")
        (interface / "driver").symlink_to(self.root / "foreign-driver")
        foreign = self.run_helper(binary, "release")
        self.assertEqual(1, foreign.returncode, foreign.stderr)

    def test_release_restores_exact_unbound_usb_interface(self):
        binary, sysfs, bind = self.compile_helper()
        device = sysfs / "1-2"
        interface = sysfs / "1-2:1.0"
        device.mkdir()
        interface.mkdir()
        (device / "idVendor").write_text("2b89\n")
        (device / "idProduct").write_text("ffff\n")
        (device / "serial").write_text("DC600\n")
        (interface / "bInterfaceNumber").write_text("00\n")

        process = subprocess.Popen([str(binary), "release"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for _ in range(100):
            if bind.read_text() == "1-2:1.0":
                break
            import time
            time.sleep(0.01)
        else:
            process.kill()
            self.fail("helper did not write the exact USB interface to usbhid bind")
        (interface / "driver").symlink_to(self.root / "usbhid")
        stdout, stderr = process.communicate(timeout=3)
        self.assertEqual(0, process.returncode, stdout + stderr)


if __name__ == "__main__":
    unittest.main()
