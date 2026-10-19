from pathlib import Path
import os
import signal
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "spk/package/native/nut-us3000-controller.c"


class RetryControllerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name).resolve()
        cls.step = cls.root / "retry-step.sh"
        cls.control = cls.root / "control"
        cls.calls = cls.root / "calls"
        cls.events = cls.root / "events"
        cls.environment = cls.root / "environment"
        cls.target = cls.root / "target"
        cls.var = cls.root / "var"
        cls.target.mkdir()
        cls.var.mkdir()
        cls.step.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            f"mode=$(/bin/cat {cls.control})\n"
            f"printf '%s\\n' \"$$\" >> {cls.calls}\n"
            "case $mode in\n"
            "  ok) exit 0 ;;\n"
            "  temp) exit 75 ;;\n"
            "  hard) exit 1 ;;\n"
            "  environment)\n"
            "    printf 'DEST=%s\\nVAR=%s\\nPATH=%s\\nEVIL=%s\\n' "
            "\"${SYNOPKG_PKGDEST-}\" \"${SYNOPKG_PKGVAR-}\" \"${PATH-}\" "
            f"\"${{EVIL-}}\" > {cls.environment}\n"
            "    exit 1\n"
            "    ;;\n"
            "  wait)\n"
            f"    printf 'started\\n' >> {cls.events}\n"
            "    /bin/sleep 1\n"
            f"    printf 'finished\\n' >> {cls.events}\n"
            "    exit 0\n"
            "    ;;\n"
            "  *) exit 64 ;;\n"
            "esac\n"
        )
        cls.step.chmod(0o755)
        cls.binary = cls.root / "nut-us3000-controller"
        if not SOURCE.is_file():
            raise AssertionError(f"missing production source: {SOURCE}")
        common_compile = [
            os.environ.get("CC", "cc"),
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-O2",
            "-D_POSIX_C_SOURCE=200809L",
            f'-DNUT_US3000_STEP_PATH="{cls.step}"',
            f'-DNUT_US3000_PKGDEST="{cls.target}"',
            f'-DNUT_US3000_PKGVAR="{cls.var}"',
            "-DNUT_US3000_INTERVAL_SECONDS=1",
            str(SOURCE),
        ]
        for binary, step_uid, step_gid in (
            (cls.binary, os.getuid(), os.getgid()),
            (cls.root / "nut-us3000-controller-build-owner-mismatch", 4294967294, 4294967294),
        ):
            completed = subprocess.run(
                [
                    *common_compile,
                    f"-DNUT_US3000_STEP_UID={step_uid}",
                    f"-DNUT_US3000_STEP_GID={step_gid}",
                    "-o",
                    str(binary),
                ],
                text=True,
                capture_output=True,
            )
            if completed.returncode != 0:
                raise AssertionError(completed.stdout + completed.stderr)
        cls.build_owner_mismatch_binary = cls.root / "nut-us3000-controller-build-owner-mismatch"

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        for path in (self.calls, self.events, self.environment):
            if path.exists() or path.is_symlink():
                path.unlink()
        self.control.write_text("ok\n")

    def run_controller(self, *args, timeout=4, env=None):
        return subprocess.run(
            [str(self.binary), *args],
            text=True,
            capture_output=True,
            timeout=timeout,
            env=(os.environ | (env or {})),
        )

    @staticmethod
    def wait_for(path: Path, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists() and predicate(path.read_text()):
                return
            time.sleep(0.01)
        raise AssertionError(f"timed out waiting for {path}")

    def test_rejects_invalid_cli_before_running_step(self):
        for args in ((), ("--first-delay",), ("--first-delay", "-1"),
                     ("--first-delay", "601"), ("--first-delay", "1x"),
                     ("--wrong", "0"), ("--first-delay", "0", "extra")):
            with self.subTest(args=args):
                completed = self.run_controller(*args)
                self.assertEqual(64, completed.returncode, completed.stderr)
        self.assertFalse(self.calls.exists())

    def test_hard_step_failure_stops_controller(self):
        self.control.write_text("hard\n")
        completed = self.run_controller("--first-delay", "0")
        self.assertEqual(1, completed.returncode, completed.stderr)
        self.assertEqual(1, len(self.calls.read_text().splitlines()))

    def test_step_owner_follows_runtime_package_identity_not_build_host_constants(self):
        self.control.write_text("hard\n")
        completed = subprocess.run(
            [str(self.build_owner_mismatch_binary), "--first-delay", "0"],
            text=True,
            capture_output=True,
            timeout=4,
        )
        self.assertEqual(1, completed.returncode, completed.stderr)
        self.assertEqual(1, len(self.calls.read_text().splitlines()))

    def test_success_and_temporary_failure_continue_at_fixed_interval(self):
        for mode in ("ok", "temp"):
            with self.subTest(mode=mode):
                self.setUp()
                self.control.write_text(mode + "\n")
                process = subprocess.Popen(
                    [str(self.binary), "--first-delay", "0"],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self.wait_for(self.calls, lambda value: len(value.splitlines()) >= 2)
                process.send_signal(signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=3)
                self.assertEqual(0, process.returncode, stdout + stderr)
                self.assertGreaterEqual(len(self.calls.read_text().splitlines()), 2)

    def test_signal_interrupts_sleep_without_another_step(self):
        process = subprocess.Popen(
            [str(self.binary), "--first-delay", "1"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(0.1)
        started = time.monotonic()
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=2)
        elapsed = time.monotonic() - started
        self.assertEqual(0, process.returncode, stdout + stderr)
        self.assertLess(elapsed, 0.5)
        self.assertFalse(self.calls.exists())

    def test_signal_during_step_waits_for_exact_child_completion(self):
        self.control.write_text("wait\n")
        process = subprocess.Popen(
            [str(self.binary), "--first-delay", "0"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.wait_for(self.events, lambda value: value == "started\n")
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=3)
        self.assertEqual(0, process.returncode, stdout + stderr)
        self.assertEqual("started\nfinished\n", self.events.read_text())
        self.assertEqual(1, len(self.calls.read_text().splitlines()))

    def test_step_receives_only_fixed_environment(self):
        self.control.write_text("environment\n")
        completed = self.run_controller(
            "--first-delay", "0", env={"EVIL": "inherited-secret"}
        )
        self.assertEqual(1, completed.returncode, completed.stderr)
        self.assertEqual(
            f"DEST={self.target}\nVAR={self.var}\nPATH=/bin:/usr/bin\nEVIL=\n",
            self.environment.read_text(),
        )

    def test_rejects_symlink_or_writable_step_before_execution(self):
        original = self.step.read_bytes()
        self.step.unlink()
        replacement = self.root / "replacement-step"
        replacement.write_bytes(original)
        replacement.chmod(0o755)
        self.step.symlink_to(replacement)
        try:
            completed = self.run_controller("--first-delay", "0")
            self.assertEqual(77, completed.returncode, completed.stderr)
            self.assertFalse(self.calls.exists())
        finally:
            self.step.unlink()
            self.step.write_bytes(original)
            self.step.chmod(0o777)
        try:
            completed = self.run_controller("--first-delay", "0")
            self.assertEqual(77, completed.returncode, completed.stderr)
            self.assertFalse(self.calls.exists())
        finally:
            self.step.chmod(0o755)

    def test_binary_has_no_shell_or_socket_execution_dependencies(self):
        completed = subprocess.run(
            ["nm", "-u", str(self.binary)],
            text=True,
            capture_output=True,
            check=True,
        )
        undefined = completed.stdout.lower()
        for forbidden in ("system", "popen", "socket", "connect"):
            self.assertNotIn(forbidden, undefined)


if __name__ == "__main__":
    unittest.main()
