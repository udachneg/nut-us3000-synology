from pathlib import Path
import hashlib
import os
import shutil
import stat
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "spk/package/payload/share/nut-us3000/lib.sh"
HEALTH = ROOT / "spk/package/payload/share/nut-us3000/healthcheck.sh"
CONTROL = ROOT / "spk/package/scripts/start-stop-status"
RETRY = ROOT / "spk/package/payload/share/nut-us3000/retry-step.sh"
PREUNINST = ROOT / "spk/package/scripts/preuninst"
POSTUNINST = ROOT / "spk/package/scripts/postuninst"

UPS_CONF = (
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
UPSD_CONF = (
    b"LISTEN 127.0.0.1 3493\n"
    b"LISTEN 10.255.255.1 3493\n"
)
UPSD_USERS = b"[monuser]\n    password = secret\n    upsmon secondary\n"
HEALTHY = (
    "driver.name: usbhid-ups\n"
    "device.mfr: UGREEN\n"
    "device.model: US3000\n"
    "ups.vendorid: 2b89\n"
    "ups.productid: ffff\n"
    "battery.runtime: 65535\n"
    "ups.status: OL\n"
)


FAKE_TOOL = r'''#!/usr/bin/env python3
import hashlib
import os
from pathlib import Path
import shutil
import stat
import sys
import time

name = Path(sys.argv[0]).name
args = sys.argv[1:]
log = Path(os.environ["COMMAND_LOG"])
with log.open("a") as stream:
    stream.write(" ".join((name, *args)) + "\n")

def finish(code=0):
    raise SystemExit(int(code))

def make_process(pid, comm, exe, starttime):
    proc = Path(os.environ["FAKE_PROC"]) / str(pid)
    proc.mkdir(parents=True, exist_ok=True)
    fields = ["S"] + ["0"] * 18 + [str(starttime), "0"]
    (proc / "stat").write_text(f"{pid} ({comm}) {' '.join(fields)}\n")
    (proc / "comm").write_text(comm + "\n")
    link = proc / "exe"
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(exe)

if name == "id":
    if args == ["-u"]:
        print(os.getuid())
        finish()
    if args == ["-g"]:
        print(os.getgid())
        finish()
    finish(64)

if name == "stat":
    if len(args) < 3 or args[0:2] != ["-c", "%a:%u:%g"]:
        finish(64)
    path = Path(args[-1])
    try:
        info = path.lstat()
    except OSError:
        finish(1)
    mode = stat.S_IMODE(info.st_mode)
    uid, gid = info.st_uid, info.st_gid
    if path.name == os.environ.get("FAKE_BAD_MODE_BASENAME"):
        mode = 0o777
    if path.name == os.environ.get("FAKE_BAD_OWNER_BASENAME"):
        uid += 1
    print(f"{mode:o}:{uid}:{gid}")
    finish()

if name == "sha256sum":
    if os.environ.get("FAKE_SHA_FAIL") == "1":
        finish(1)
    if args[:1] == ["-c"] and len(args) == 2:
        manifest = Path(args[1])
        try:
            records = manifest.read_text().splitlines()
        except OSError:
            finish(1)
        for record in records:
            if len(record) <= 66 or record[64:66] != "  ":
                finish(1)
            digest, basename = record[:64], record[66:]
            candidate = Path(os.environ["CONFIG"]) / basename
            try:
                actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
            except OSError:
                finish(1)
            if actual != digest:
                print(f"{basename}: FAILED")
                finish(1)
            print(f"{basename}: OK")
        finish()
    if not args:
        finish(64)
    for value in args:
        path = Path(value)
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            finish(1)
        print(f"{digest}  {value}")
    finish()

if name == "readlink":
    if not args:
        finish(64)
    path = Path(args[-1])
    if path.parent.name == os.environ.get("READLINK_FAIL_PID"):
        finish(1)
    try:
        print(os.readlink(path))
    except OSError:
        finish(1)
    finish()

if name == "uname":
    if args == ["-m"]:
        print(os.environ.get("FAKE_UNAME_M", "x86_64"))
        finish()
    if args == ["-a"]:
        print(os.environ.get(
            "FAKE_UNAME_A",
            "Linux dsm 4.4.302+ synology_epyc7002_72806 SMP x86_64 GNU/Linux",
        ))
        finish()
    finish(64)

if name == "netstat":
    if args != ["-lnt"]:
        finish(64)
    late_pid = os.environ.get("LATE_REFERENCE_PID")
    late_marker = Path(os.environ["FIXTURE_ROOT"]) / "late-reference-created"
    if late_pid and not late_marker.exists():
        run = Path(os.environ["RUN"])
        run.mkdir(parents=True, exist_ok=True)
        run.chmod(0o750)
        (run / "upsd.pid").write_text(late_pid + "\n")
        (Path(os.environ["FAKE_PROC"]) / late_pid).mkdir(parents=True, exist_ok=True)
        late_marker.write_text("created\n")
    mode = os.environ.get("NETSTAT_MODE", "auto")
    if mode == "auto":
        server = Path(os.environ["FAKE_PROC"]) / os.environ["UPSD_PID"]
        mode = "host-local" if server.is_dir() else "free"
    rows = {
        "free": [],
        "loopback": ["tcp 0 0 127.0.0.1:3493 0.0.0.0:* LISTEN"],
        "host-local": [
            "tcp 0 0 127.0.0.1:3493 0.0.0.0:* LISTEN",
            "tcp 0 0 10.255.255.1:3493 0.0.0.0:* LISTEN",
        ],
        "alias-only": ["tcp 0 0 10.255.255.1:3493 0.0.0.0:* LISTEN"],
        "wildcard": ["tcp 0 0 0.0.0.0:3493 0.0.0.0:* LISTEN"],
        "ipv6": ["tcp6 0 0 :::3493 :::* LISTEN"],
        "multi": [
            "tcp 0 0 127.0.0.1:3493 0.0.0.0:* LISTEN",
            "tcp 0 0 0.0.0.0:3493 0.0.0.0:* LISTEN",
        ],
    }.get(mode)
    if rows is None:
        finish(64)
    print("Active Internet connections (only servers)")
    print("Proto Recv-Q Send-Q Local Address Foreign Address State")
    for row in rows:
        print(row)
    finish()

if name == "ip":
    if args != ["-4", "-o", "address", "show", "to", "10.255.255.1/32"]:
        finish(64)
    if os.environ.get("ALIAS_PRESENT", "1") == "1":
        print("1: lo    inet 10.255.255.1/32 scope host lo:nutus3000")
    finish()

if name == "timeout":
    command = list(args)
    if command[:1] == ["-k"]:
        if len(command) < 4:
            finish(64)
        command = command[3:]
    else:
        if len(command) < 2:
            finish(64)
        command = command[1:]
    os.execvpe(command[0], command, os.environ)

if name == "sleep":
    time.sleep(0.05)
    finish()

if name == "rm":
    fail_path = os.environ.get("RM_FAIL_PATH")
    if fail_path and fail_path in args:
        finish(os.environ.get("RM_FAIL_RESULT", "7"))
    os.execv("/bin/rm", ["rm", *args])

if name == "kill":
    if not args or not args[-1].isdigit():
        finish(64)
    pid = args[-1]
    proc_root = Path(os.environ["FAKE_PROC"]).resolve()
    fixture_root = Path(os.environ["FIXTURE_ROOT"]).resolve()
    if proc_root != fixture_root / "proc":
        finish(70)
    if os.environ.get("KILL_RESULT", "0") != "0":
        finish(os.environ["KILL_RESULT"])
    if pid != os.environ.get("KILL_HUNG_PID"):
        shutil.rmtree(proc_root / pid, ignore_errors=True)
    finish()

if name == "upsdrvctl":
    if args == ["start"]:
        if os.environ.get("CONTROLLER_CREATE_ON_START") == "1":
            make_process(
                os.environ["CONTROLLER_PID"], "upsdrvctl",
                str(Path(os.environ["TARGET"]) / "sbin/upsdrvctl"),
                os.environ["CONTROLLER_STARTTIME"],
            )
        if os.environ.get("DRIVER_CREATE_ON_START", "1") == "1":
            run = Path(os.environ["RUN"])
            run.mkdir(parents=True, exist_ok=True)
            make_process(
                os.environ["DRIVER_PID"], "usbhid-ups",
                str(Path(os.environ["TARGET"]) / "libexec/nut/usbhid-ups"),
                os.environ["DRIVER_STARTTIME"],
            )
            native_state = os.environ.get("DRIVER_NATIVE_PID_STATE", "valid")
            if native_state != "missing":
                native_pid = os.environ.get("DRIVER_NATIVE_PID", os.environ["DRIVER_PID"])
                if native_state == "malformed":
                    native_pid = "not-a-pid"
                (run / "usbhid-ups-ups.pid").write_text(native_pid + "\n")
            (run / "usbhid-ups-ups").write_text("fixture socket\n")
        finish(os.environ.get("DRIVER_START_RESULT", "0"))
    if args == ["stop", "ups"]:
        result = os.environ.get("DRIVER_STOP_RESULT", "0")
        if result == "0" and os.environ.get("DRIVER_STOP_HUNG") != "1":
            shutil.rmtree(
                Path(os.environ["FAKE_PROC"]) / os.environ["DRIVER_PID"],
                ignore_errors=True,
            )
        finish(result)
    finish(64)

if name == "upsd":
    result = os.environ.get("UPSD_RESULT", "0")
    if result == "0" or os.environ.get("UPSD_CREATE_ON_FAILURE") == "1":
        run = Path(os.environ["RUN"])
        run.mkdir(parents=True, exist_ok=True)
        make_process(
            os.environ["UPSD_PID"], "upsd",
            str(Path(os.environ["TARGET"]) / "sbin/upsd"),
            os.environ["UPSD_STARTTIME"],
        )
        (run / "upsd.pid").write_text(os.environ["UPSD_PID"] + "\n")
    finish(result)

if name == "upsc":
    if args != ["ups@127.0.0.1"]:
        finish(64)
    output = Path(os.environ["UPSC_OUTPUT"])
    if output.is_file():
        sys.stdout.write(output.read_text())
    finish(os.environ.get("UPSC_RESULT", "0"))

if name == "nut-us3000-hostctl":
    if args not in (["ensure"], ["audit"], ["release"]):
        finish(64)
    result_name = "HOSTCTL_" + args[0].upper() + "_RESULT"
    finish(os.environ.get(result_name, "0"))

if name == "nut-us3000-controller":
    if len(args) != 2 or args[0] != "--first-delay" or not args[1].isdigit():
        finish(64)
    if not 0 <= int(args[1]) <= 600:
        finish(64)
    result = os.environ.get("RETRY_CONTROLLER_RESULT", "0")
    if result == "0":
        make_process(
            os.environ["RETRY_PID"], "nut-us3000-cont",
            str(Path(os.environ["TARGET"]) / "libexec/nut/nut-us3000-controller"),
            os.environ["RETRY_STARTTIME"],
        )
    finish(result)

finish(64)
'''


class LifecycleFixture:
    CONTROLLER_PID = 4100
    DRIVER_PID = 4101
    UPSD_PID = 4102
    RETRY_PID = 4103
    CONTROLLER_START = 90000
    DRIVER_START = 90001
    UPSD_START = 90002
    RETRY_START = 90003

    def __init__(self, case: unittest.TestCase):
        temporary = tempfile.TemporaryDirectory()
        case.addCleanup(temporary.cleanup)
        self.case = case
        self.root = Path(temporary.name).resolve()
        self.target = self.root / "target"
        self.var = self.root / "package-var"
        self.run = self.var / "run"
        self.config = self.root / "var/packages/nut-us3000/etc"
        self.proc = self.root / "proc"
        self.usb = self.root / "sys/bus/usb/devices"
        self.version = self.root / "etc.defaults/VERSION"
        self.fake_bin = self.root / "fake-bin"
        self.log = self.root / "commands.log"
        self.upsc_output = self.root / "upsc.out"
        for path in (self.target, self.var, self.config, self.proc, self.usb, self.fake_bin):
            path.mkdir(parents=True, exist_ok=True)
        self.config.chmod(0o750)
        self.log.write_text("")
        self.upsc_output.write_text(HEALTHY)
        self.proc_uptime = self.proc / "uptime"
        self.proc_uptime.write_text("700.00 0.00\n")
        self._write_platform()
        self._write_config()
        self.add_usb("1-1")
        self._write_fakes()
        self.env = os.environ | {
            "PATH": f"{self.fake_bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "COMMAND_LOG": str(self.log),
            "CONFIG": str(self.config),
            "CONTROLLER_PID": str(self.CONTROLLER_PID),
            "CONTROLLER_STARTTIME": str(self.CONTROLLER_START),
            "DRIVER_PID": str(self.DRIVER_PID),
            "DRIVER_STARTTIME": str(self.DRIVER_START),
            "FAKE_PROC": str(self.proc),
            "FIXTURE_ROOT": str(self.root),
            "RUN": str(self.run),
            "RETRY_PID": str(self.RETRY_PID),
            "RETRY_STARTTIME": str(self.RETRY_START),
            "SYNOPKG_PKGDEST": str(self.target),
            "SYNOPKG_PKGVAR": str(self.var),
            "TARGET": str(self.target),
            "UPSC_OUTPUT": str(self.upsc_output),
            "UPSD_PID": str(self.UPSD_PID),
            "UPSD_STARTTIME": str(self.UPSD_START),
        }
        self._copy_production()
        case.addCleanup(self.assert_safe_log)

    def _write_platform(self):
        self.version.parent.mkdir(parents=True, exist_ok=True)
        self.version.write_text(
            'productversion="7.2.2"\nbuildnumber="72806"\nsmallfixnumber="8"\n'
        )

    def _write_config(self):
        values = {
            "ups.conf": (UPS_CONF, 0o640),
            "upsd.conf": (UPSD_CONF, 0o640),
            "upsd.users": (UPSD_USERS, 0o600),
        }
        for name, (content, mode) in values.items():
            path = self.config / name
            path.write_bytes(content)
            path.chmod(mode)
        manifest = self.var / "config-manifest.sha256"
        manifest.write_text("".join(
            f"{hashlib.sha256(content).hexdigest()}  {name}\n"
            for name, (content, _) in values.items()
        ))
        manifest.chmod(0o600)

    def _write_fakes(self):
        dispatcher = self.fake_bin / "fixture-command"
        dispatcher.write_text(FAKE_TOOL)
        dispatcher.chmod(0o755)
        for name in (
            "id", "ip", "kill", "netstat", "readlink", "sha256sum", "sleep",
            "rm", "stat", "timeout", "uname",
        ):
            (self.fake_bin / name).symlink_to(dispatcher)
        for relative in (
            "bin/upsc", "sbin/upsd", "sbin/upsdrvctl", "libexec/nut/usbhid-ups",
            "libexec/nut/nut-us3000-hostctl", "libexec/nut/nut-us3000-controller",
        ):
            path = self.target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(FAKE_TOOL)
            path.chmod(0o755)

    def _copy(self, source: Path, destination: Path):
        text = source.read_text()
        replacements = (
            ("/var/packages/nut-us3000/etc", str(self.config)),
            ("/sys/bus/usb/devices", str(self.usb)),
            ("/etc.defaults/VERSION", str(self.version)),
            ("/usr/bin/sha256sum", str(self.fake_bin / "sha256sum")),
            ("/usr/bin/readlink", str(self.fake_bin / "readlink")),
            ("/usr/bin/timeout", str(self.fake_bin / "timeout")),
            ("/usr/bin/stat", str(self.fake_bin / "stat")),
            ("/usr/bin/id", str(self.fake_bin / "id")),
            ("/usr/bin/sleep", str(self.fake_bin / "sleep")),
            ("/usr/sbin/ip", str(self.fake_bin / "ip")),
            ("/bin/netstat", str(self.fake_bin / "netstat")),
            ("/bin/uname", str(self.fake_bin / "uname")),
            ("/bin/kill", str(self.fake_bin / "kill")),
            ("/bin/sleep", str(self.fake_bin / "sleep")),
            ("/proc", str(self.proc)),
        )
        for original, fixture in replacements:
            text = text.replace(original, fixture)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text)
        destination.chmod(0o755)

    def _copy_production(self):
        self.lib = self.target / "share/nut-us3000/lib.sh"
        self.health = self.target / "share/nut-us3000/healthcheck.sh"
        self.control = self.root / "start-stop-status"
        self.retry = self.target / "share/nut-us3000/retry-step.sh"
        self._copy(LIB, self.lib)
        self._copy(HEALTH, self.health)
        self._copy(CONTROL, self.control)
        if RETRY.is_file():
            self._copy(RETRY, self.retry)

    def reset_usb(self):
        shutil.rmtree(self.usb)
        self.usb.mkdir(parents=True)

    def use_dsm_package_aliases(self, config_package="nut-us3000", var_package="nut-us3000"):
        volume = self.root / "volume3"
        physical_var = volume / "@appdata" / var_package
        physical_config = volume / "@appconf" / config_package
        physical_var.parent.mkdir(parents=True, exist_ok=True)
        physical_config.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(self.var), physical_var)
        shutil.move(str(self.config), physical_config)

        var_alias = self.config.parent / "var"
        self.config.symlink_to(physical_config, target_is_directory=True)
        var_alias.symlink_to(physical_var, target_is_directory=True)

        self.var = physical_var
        self.run = self.var / "run"
        self.env.update({
            "CONFIG": str(physical_config),
            "RUN": str(self.run),
            "SYNOPKG_PKGVAR": str(var_alias),
        })

    def use_dsm_target_alias(self):
        target_alias = self.config.parent / "target"
        target_alias.symlink_to(self.target, target_is_directory=True)
        self.env["SYNOPKG_PKGDEST"] = str(target_alias)

    def add_usb(self, name, vendor="2b89", product="ffff", serial="DC600", interfaces=("00",)):
        device = self.usb / name
        device.mkdir(parents=True)
        for attribute, value in (
            ("idVendor", vendor), ("idProduct", product), ("serial", serial),
        ):
            (device / attribute).write_text(value + "\n")
        for index, number in enumerate(interfaces):
            interface = self.usb / f"{name}:1.{index}"
            interface.mkdir()
            (interface / "bInterfaceNumber").write_text(number + "\n")

    def add_process(self, pid, comm, exe, starttime, state="S", complete=True):
        directory = self.proc / str(pid)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "comm").write_text(comm + "\n")
        if not complete:
            return
        fields = [state] + ["0"] * 18 + [str(starttime), "0"]
        (directory / "stat").write_text(f"{pid} ({comm}) {' '.join(fields)}\n")
        (directory / "exe").symlink_to(exe)

    def identity(self, basename, pid, starttime, exe):
        self.run.mkdir(parents=True, exist_ok=True)
        self.run.chmod(0o750)
        path = self.run / f"{basename}.identity"
        path.write_text(f"{pid}:{starttime}:{exe}\n")
        path.chmod(0o600)
        native = self.run / ("usbhid-ups-ups.pid" if basename == "usbhid-ups" else "upsd.pid")
        native.write_text(f"{pid}\n")
        native.chmod(0o600)
        if basename == "usbhid-ups":
            (self.run / "usbhid-ups-ups").write_text("fixture socket\n")

    def setup_running(self, driver=True, server=True):
        if driver:
            exe = self.target / "libexec/nut/usbhid-ups"
            self.add_process(self.DRIVER_PID, "usbhid-ups", exe, self.DRIVER_START)
            self.identity("usbhid-ups", self.DRIVER_PID, self.DRIVER_START, exe)
        if server:
            exe = self.target / "sbin/upsd"
            self.add_process(self.UPSD_PID, "upsd", exe, self.UPSD_START)
            self.identity("upsd", self.UPSD_PID, self.UPSD_START, exe)

    def setup_controller(self):
        exe = self.target / "libexec/nut/nut-us3000-controller"
        self.add_process(self.RETRY_PID, "nut-us3000-cont", exe, self.RETRY_START)
        self.run.mkdir(parents=True, exist_ok=True)
        self.run.chmod(0o750)
        identity = self.run / "nut-us3000-controller.identity"
        identity.write_text(f"{self.RETRY_PID}:{self.RETRY_START}:{exe}\n")
        identity.chmod(0o600)

    def run_script(self, path, args=(), env=None):
        try:
            return subprocess.run(
                ["/bin/sh", str(path), *args],
                text=True,
                capture_output=True,
                env=self.env | (env or {}),
                timeout=8,
            )
        except subprocess.TimeoutExpired as error:
            self.case.fail(f"fixture exceeded its bound: {path.name} {args}: {error}")

    def run_control(self, *args, env=None):
        return self.run_script(self.control, args, env)

    def run_health(self, *args, env=None):
        return self.run_script(self.health, args, env)

    def run_retry(self, *args, env=None):
        return self.run_script(self.retry, args, env)

    def run_lib_function(self, function, env=None):
        return subprocess.run(
            ["/bin/sh", "-c", '. "$1"; shift; "$@"', "sh", str(self.lib), function],
            text=True,
            capture_output=True,
            env=self.env | (env or {}),
            timeout=8,
        )

    def run_preuninst(self, env=None):
        return self.run_script(PREUNINST, env=env)

    def commands(self):
        return self.log.read_text().splitlines()

    def assert_no_start_mutation(self):
        joined = "\n".join(self.commands())
        self.case.assertNotIn("upsdrvctl start", joined)
        self.case.assertFalse(any(line.startswith("upsd ") for line in self.commands()))

    def assert_safe_log(self):
        text = "\n".join(self.commands()).lower()
        tokens = text.split()
        for forbidden_path in ("/usr/syno/etc/ups", "/etc/ups"):
            self.case.assertFalse(any(
                token == forbidden_path or token.startswith(forbidden_path + "/")
                for token in tokens
            ))
        for forbidden in (
            "upsdrvctl shutdown", " fsd",
            "upscmd", "load.off", "shutdown.return", "synopoweroff", "poweroff",
            "sudo ", "doas ", "su -",
        ):
            self.case.assertNotIn(forbidden, text)
        self.case.assertFalse(
            any(line.startswith("kill ") and line.split()[-1] == "6000" for line in self.commands()),
            "fixture observed an attempt to signal upsmon",
        )


class SpkLifecycleTest(unittest.TestCase):
    def require_production(self):
        for artifact in (LIB, HEALTH, CONTROL):
            self.assertTrue(
                artifact.is_file(),
                f"missing required Task 3 production artifact: {artifact}",
            )

    def postuninst_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        volume = root / "volume3"
        home = volume / "@apphome/nut-us3000"
        var = volume / "@appdata/nut-us3000"
        config = volume / "@appconf/nut-us3000"
        for target in (home, var, config):
            (target / "nested").mkdir(parents=True)
            (target / "sentinel").write_text(target.name + "\n")
            (target / "nested/leaf").write_text("leaf\n")
        foreign = volume / "foreign-preserve"
        foreign.write_text("keep\n")

        fake_bin = root / "fake-bin"
        fake_bin.mkdir()
        fake_stat = fake_bin / "stat"
        fake_stat.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "[ \"$#\" -eq 3 ] && [ \"$1:$2\" = '-c:%d' ] || exit 64\n"
            "if [ \"$1:$2:${3##*/}\" = '-c:%d:'\"${BAD_DEVICE_BASENAME:-__never__}\" ]; then\n"
            "  printf '999999\\n'\n"
            "  exit 0\n"
            "fi\n"
            "exec \"$REAL_STAT\" -f %d \"$3\"\n"
        )
        fake_stat.chmod(0o755)
        script = root / "postuninst"
        text = POSTUNINST.read_text().replace("/usr/bin/stat", str(fake_stat))
        script.write_text(text)
        script.chmod(0o755)
        env = os.environ | {
            "REAL_STAT": shutil.which("stat"),
            "SYNOPKG_PKGHOME": str(home),
            "SYNOPKG_PKGVAR": str(var),
        }
        return root, volume, home, var, config, foreign, script, env

    @staticmethod
    def snapshot_tree(paths):
        return {
            str(path): sorted(
                (str(item.relative_to(path)), item.is_symlink(), item.is_dir())
                for item in path.rglob("*")
            )
            for path in paths
        }

    def test_postuninst_keeps_by_default_and_deletes_only_exact_data_on_true(self):
        for values in ({}, {"wizard_delete_data": "false", "wizard_keep_data": "true"}):
            with self.subTest(values=values):
                _, _, home, var, config, foreign, script, env = self.postuninst_fixture()
                before = self.snapshot_tree((home, var, config))
                completed = subprocess.run(
                    ["/bin/sh", str(script)], text=True, capture_output=True, env=env | values
                )
                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertEqual(before, self.snapshot_tree((home, var, config)))
                self.assertEqual("keep\n", foreign.read_text())

        _, volume, home, var, config, foreign, script, env = self.postuninst_fixture()
        completed = subprocess.run(
            ["/bin/sh", str(script)],
            text=True,
            capture_output=True,
            env=env | {"wizard_delete_data": "true", "wizard_keep_data": "false"},
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        for target in (home, var, config):
            self.assertTrue(target.is_dir())
            self.assertEqual([], list(target.iterdir()))
        self.assertTrue(volume.is_dir())
        self.assertEqual("keep\n", foreign.read_text())

    def test_postuninst_rejects_every_unsafe_target_before_first_delete(self):
        cases = (
            "invalid-wizard", "inconsistent-wizard", "home-symlink", "wrong-suffix",
            "missing-parent", "filesystem-boundary",
        )
        for mutation in cases:
            with self.subTest(mutation=mutation):
                root, volume, home, var, config, foreign, script, env = self.postuninst_fixture()
                values = {"wizard_delete_data": "true", "wizard_keep_data": "false"}
                tracked = (home, var, config)
                if mutation == "invalid-wizard":
                    values["wizard_delete_data"] = "yes"
                elif mutation == "inconsistent-wizard":
                    values["wizard_keep_data"] = "true"
                elif mutation == "home-symlink":
                    physical = volume / "@apphome/nut-us3000-real"
                    home.rename(physical)
                    home.symlink_to(physical, target_is_directory=True)
                    tracked = (physical, var, config)
                elif mutation == "wrong-suffix":
                    env["SYNOPKG_PKGVAR"] = str(volume / "@appdata/other")
                elif mutation == "missing-parent":
                    env["SYNOPKG_PKGHOME"] = str(root / "missing/@apphome/nut-us3000")
                else:
                    (config / "cross-device").write_text("boundary\n")
                    env["BAD_DEVICE_BASENAME"] = "cross-device"
                before = self.snapshot_tree(tracked)
                completed = subprocess.run(
                    ["/bin/sh", str(script)], text=True, capture_output=True, env=env | values
                )
                self.assertNotEqual(0, completed.returncode, completed.stderr)
                self.assertEqual(before, self.snapshot_tree(tracked))
                self.assertEqual("keep\n", foreign.read_text())

        source = POSTUNINST.read_text().lower()
        for forbidden in ("synouser", "synogroup", "/usr/syno/etc/ups", "iptables"):
            self.assertNotIn(forbidden, source)

    def test_classified_usb_probe_distinguishes_exact_absent_and_unsafe(self):
        self.require_production()

        exact = LifecycleFixture(self)
        self.assertEqual(0, exact.run_lib_function("nutus3000_probe_usb").returncode)

        absent = LifecycleFixture(self)
        absent.reset_usb()
        self.assertEqual(75, absent.run_lib_function("nutus3000_probe_usb").returncode)

        unrelated = LifecycleFixture(self)
        unrelated.reset_usb()
        unrelated.add_usb("2-1", vendor="1234", product="5678", serial="OTHER")
        self.assertEqual(75, unrelated.run_lib_function("nutus3000_probe_usb").returncode)

        for mutation in ("duplicate", "wrong-serial", "wrong-interface"):
            with self.subTest(mutation=mutation):
                fixture = LifecycleFixture(self)
                fixture.reset_usb()
                if mutation == "duplicate":
                    fixture.add_usb("2-1")
                    fixture.add_usb("3-1")
                elif mutation == "wrong-serial":
                    fixture.add_usb("2-1", serial="OTHER")
                else:
                    fixture.add_usb("2-1", interfaces=("01",))
                self.assertEqual(1, fixture.run_lib_function("nutus3000_probe_usb").returncode)

    def test_classified_start_distinguishes_healthy_temporary_and_hard_failure(self):
        healthy = LifecycleFixture(self)
        self.assertEqual(0, healthy.run_lib_function("nutus3000_attempt_start").returncode)

        absent = LifecycleFixture(self)
        absent.reset_usb()
        self.assertEqual(75, absent.run_lib_function("nutus3000_attempt_start").returncode)
        self.assertEqual(1, absent.run_lib_function("nutus3000_start").returncode)

        temporary = LifecycleFixture(self)
        result = temporary.run_lib_function(
            "nutus3000_attempt_start", env={"DRIVER_START_RESULT": "7"}
        )
        self.assertEqual(75, result.returncode, result.stderr)
        self.assertFalse((temporary.proc / str(temporary.DRIVER_PID)).exists())

        hard = LifecycleFixture(self)
        result = hard.run_lib_function(
            "nutus3000_attempt_start",
            env={"DRIVER_START_RESULT": "7", "DRIVER_NATIVE_PID_STATE": "malformed"},
        )
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertTrue((hard.proc / str(hard.DRIVER_PID)).is_dir())

    def test_lifecycle_starts_exact_controller_with_classified_first_delay(self):
        self.require_production()

        connected = LifecycleFixture(self)
        result = connected.run_control("start")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("nut-us3000-hostctl audit", connected.commands())
        self.assertIn("nut-us3000-controller --first-delay 300", connected.commands())
        self.assertTrue((connected.run / "nut-us3000-controller.identity").is_file())
        duplicate = connected.run_control("start")
        self.assertEqual(0, duplicate.returncode, duplicate.stderr)
        self.assertEqual(
            1,
            connected.commands().count("nut-us3000-controller --first-delay 300"),
        )

        for uptime, expected_delay in (("120.00 0.00\n", 480), ("700.00 0.00\n", 0)):
            with self.subTest(uptime=uptime, expected_delay=expected_delay):
                fixture = LifecycleFixture(self)
                fixture.reset_usb()
                fixture.proc_uptime.write_text(uptime)
                result = fixture.run_control("start")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertNotIn("upsdrvctl start", fixture.commands())
                self.assertFalse(any(line.startswith("upsd ") for line in fixture.commands()))
                self.assertIn(
                    f"nut-us3000-controller --first-delay {expected_delay}",
                    fixture.commands(),
                )

        unsafe = LifecycleFixture(self)
        unsafe.add_usb("2-1")
        result = unsafe.run_control("start")
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertFalse(any("nut-us3000-controller" in line for line in unsafe.commands()))

    def test_controller_identity_defines_status_and_is_stopped_before_core(self):
        self.require_production()

        unavailable = LifecycleFixture(self)
        unavailable.reset_usb()
        unavailable.setup_controller()
        status = unavailable.run_control("status")
        self.assertEqual(0, status.returncode, status.stderr)
        stopped = unavailable.run_control("stop")
        self.assertEqual(0, stopped.returncode, stopped.stderr)
        self.assertIn(f"kill -TERM {unavailable.RETRY_PID}", unavailable.commands())
        self.assertIn("nut-us3000-hostctl release", unavailable.commands())

        running = LifecycleFixture(self)
        running.setup_controller()
        running.setup_running()
        stopped = running.run_control("stop")
        self.assertEqual(0, stopped.returncode, stopped.stderr)
        lines = running.commands()
        self.assertLess(
            lines.index(f"kill -TERM {running.RETRY_PID}"),
            lines.index(f"kill -TERM {running.UPSD_PID}"),
        )

        reused = LifecycleFixture(self)
        reused.setup_controller()
        retry_stat = reused.proc / str(reused.RETRY_PID) / "stat"
        retry_stat.write_text(retry_stat.read_text().replace(str(reused.RETRY_START), "99999"))
        stopped = reused.run_control("stop")
        self.assertEqual(1, stopped.returncode, stopped.stderr)
        self.assertNotIn(f"kill -TERM {reused.RETRY_PID}", reused.commands())

    def test_retry_step_state_machine_is_bounded_and_fail_closed(self):
        self.assertTrue(RETRY.is_file(), f"missing retry step: {RETRY}")
        forbidden = ("upsmon", "FSD", "shutdown", "poweroff", "load.off", "sysnotify",
                     "synonotify", "sendmail", "smtp")
        retry_source = RETRY.read_text()
        for token in forbidden:
            self.assertNotIn(token, retry_source)

        healthy = LifecycleFixture(self)
        healthy.setup_controller()
        healthy.setup_running()
        result = healthy.run_retry()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("HEALTHY\n", (healthy.run / "controller-health.state").read_text())
        self.assertNotIn("upsdrvctl stop ups", healthy.commands())

        absent = LifecycleFixture(self)
        absent.reset_usb()
        absent.setup_controller()
        result = absent.run_retry()
        self.assertEqual(75, result.returncode, result.stderr)
        self.assertEqual("UNAVAILABLE\n", (absent.run / "controller-health.state").read_text())
        absent.assert_no_start_mutation()

        recovered = LifecycleFixture(self)
        recovered.setup_controller()
        result = recovered.run_retry()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("HEALTHY\n", (recovered.run / "controller-health.state").read_text())

        degraded = LifecycleFixture(self)
        degraded.setup_controller()
        degraded.setup_running()
        result = degraded.run_retry(env={"UPSC_RESULT": "7"})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("DEGRADED_1\n", (degraded.run / "controller-health.state").read_text())
        self.assertNotIn("upsdrvctl stop ups", degraded.commands())

        second = LifecycleFixture(self)
        second.setup_controller()
        second.setup_running()
        second.run.mkdir(parents=True, exist_ok=True)
        state = second.run / "controller-health.state"
        state.write_text("DEGRADED_1\n")
        state.chmod(0o600)
        result = second.run_retry(env={"UPSC_RESULT": "7"})
        self.assertEqual(75, result.returncode, result.stderr)
        self.assertEqual("UNAVAILABLE\n", state.read_text())
        self.assertEqual(1, second.commands().count("upsdrvctl start"))
        self.assertEqual(1, second.commands().count("nut-us3000-hostctl release"))
        self.assertEqual(2, second.commands().count("nut-us3000-hostctl ensure"))

        for mutation in ("symlink", "mode", "content"):
            with self.subTest(mutation=mutation):
                fixture = LifecycleFixture(self)
                fixture.setup_controller()
                state = fixture.run / "controller-health.state"
                if mutation == "symlink":
                    external = fixture.root / "state"
                    external.write_text("HEALTHY\n")
                    state.symlink_to(external)
                elif mutation == "mode":
                    state.write_text("HEALTHY\n")
                    state.chmod(0o644)
                else:
                    state.write_text("UNKNOWN\n")
                    state.chmod(0o600)
                result = fixture.run_retry()
                self.assertEqual(1, result.returncode, result.stderr)
                fixture.assert_no_start_mutation()

    def test_start_accepts_supported_dsm_72_updates_only(self):
        self.require_production()
        for product, build in (("7.2.2", "72806"), ("7.2.2", "72807"), ("7.2.3", "80000")):
            with self.subTest(product=product, build=build, expected="pass"):
                fixture = LifecycleFixture(self)
                fixture.version.write_text(
                    f'productversion="{product}"\nbuildnumber="{build}"\n'
                )
                completed = fixture.run_control("start")
                self.assertEqual(0, completed.returncode, completed.stderr)

        invalid_versions = (
            ('productversion="7.2.1"\nbuildnumber="80000"\n', {}),
            ('productversion="7.2.3"\nbuildnumber="72805"\n', {}),
            ('productversion="7.3.0"\nbuildnumber="80000"\n', {}),
            ('productversion="8.0.0"\nbuildnumber="90000"\n', {}),
            ('productversion="7.2.02"\nbuildnumber="80000"\n', {}),
            ('productversion="7.2.x"\nbuildnumber="80000"\n', {}),
            ('productversion="7.2.3"\nbuildnumber="not-a-number"\n', {}),
            ('productversion="7.2.3"\nbuildnumber="080000"\n', {}),
            (
                'productversion="7.2.2"\nproductversion="7.2.3"\nbuildnumber="80000"\n',
                {},
            ),
            ('productversion="7.2.3"\nbuildnumber="80000"\n', {"FAKE_UNAME_M": "aarch64"}),
            (
                'productversion="7.2.3"\nbuildnumber="80000"\n',
                {"FAKE_UNAME_A": "Linux dsm synology_broadwellnk_80000 x86_64"},
            ),
            (
                'productversion="7.2.3"\nbuildnumber="80000"\n',
                {
                    "FAKE_UNAME_A": (
                        "Linux dsm synology_epyc7002_80000 "
                        "synology_epyc7002_duplicate x86_64"
                    )
                },
            ),
        )
        for version_text, env in invalid_versions:
            with self.subTest(version=version_text.splitlines()[0], env=env):
                fixture = LifecycleFixture(self)
                fixture.version.write_text(version_text)
                result = fixture.run_control("start", env=env)
                self.assertEqual(1, result.returncode, result.stderr)
                fixture.assert_no_start_mutation()

        for mutation in ("symlink", "missing"):
            with self.subTest(mutation=mutation):
                fixture = LifecycleFixture(self)
                env = {}
                if mutation == "symlink":
                    replacement = fixture.root / "VERSION.replacement"
                    replacement.write_bytes(fixture.version.read_bytes())
                    fixture.version.unlink()
                    fixture.version.symlink_to(replacement)
                else:
                    fixture.version.unlink()
                result = fixture.run_control("start", env=env)
                self.assertEqual(1, result.returncode, result.stderr)
                fixture.assert_no_start_mutation()

    def test_control_orders_native_host_integration_around_nut_lifecycle(self):
        self.require_production()

        started = LifecycleFixture(self)
        start_result = started.run_control("start")
        self.assertEqual(0, start_result.returncode, start_result.stderr)
        start_lines = started.commands()
        self.assertLess(
            start_lines.index("nut-us3000-hostctl ensure"),
            start_lines.index("upsdrvctl start"),
        )

        status_fixture = LifecycleFixture(self)
        status_fixture.setup_controller()
        status_fixture.setup_running()
        status_result = status_fixture.run_control("status")
        self.assertEqual(0, status_result.returncode, status_result.stderr)
        status_lines = status_fixture.commands()
        self.assertLess(
            status_lines.index("nut-us3000-hostctl audit"),
            status_lines.index("uname -m"),
        )

        stopped = LifecycleFixture(self)
        stopped.setup_running()
        stop_result = stopped.run_control("stop")
        self.assertEqual(0, stop_result.returncode, stop_result.stderr)
        stop_lines = stopped.commands()
        self.assertLess(
            stop_lines.index("upsdrvctl stop ups"),
            stop_lines.index("nut-us3000-hostctl release"),
        )

    def test_temporary_start_failure_keeps_retry_controller_but_failed_stop_does_not_release(self):
        self.require_production()

        failed_start = LifecycleFixture(self)
        start_result = failed_start.run_control("start", env={"DRIVER_START_RESULT": "7"})
        self.assertEqual(0, start_result.returncode, start_result.stderr)
        self.assertNotIn("nut-us3000-hostctl release", failed_start.commands())
        self.assertTrue((failed_start.run / "nut-us3000-controller.identity").is_file())

        failed_stop = LifecycleFixture(self)
        failed_stop.setup_running()
        stop_result = failed_stop.run_control("stop", env={"DRIVER_STOP_RESULT": "7"})
        self.assertEqual(1, stop_result.returncode, stop_result.stderr)
        self.assertNotIn("nut-us3000-hostctl release", failed_stop.commands())

    def test_native_host_integration_failures_are_fail_closed(self):
        self.require_production()

        ensure = LifecycleFixture(self)
        ensure_result = ensure.run_control("start", env={"HOSTCTL_ENSURE_RESULT": "7"})
        self.assertEqual(1, ensure_result.returncode, ensure_result.stderr)
        ensure.assert_no_start_mutation()

        audit = LifecycleFixture(self)
        audit.setup_running()
        audit_result = audit.run_control("status", env={"HOSTCTL_AUDIT_RESULT": "7"})
        self.assertEqual(1, audit_result.returncode, audit_result.stderr)
        self.assertNotIn("upsc ups@127.0.0.1", audit.commands())

        release = LifecycleFixture(self)
        release.setup_running()
        release_result = release.run_control("stop", env={"HOSTCTL_RELEASE_RESULT": "7"})
        self.assertEqual(1, release_result.returncode, release_result.stderr)
        self.assertIn("upsdrvctl stop ups", release.commands())

    def test_start_accepts_only_exact_dsm_appconf_appdata_alias_pair(self):
        self.require_production()
        for mutation in ("exact", "wrong-config", "wrong-var"):
            with self.subTest(mutation=mutation):
                fixture = LifecycleFixture(self)
                config_package = "other" if mutation == "wrong-config" else "nut-us3000"
                var_package = "other" if mutation == "wrong-var" else "nut-us3000"
                fixture.use_dsm_package_aliases(config_package, var_package)
                result = fixture.run_control("start")
                self.assertEqual(0 if mutation == "exact" else 1, result.returncode, result.stderr)
                if mutation != "exact":
                    fixture.assert_no_start_mutation()

    def test_start_and_status_canonicalize_dsm_target_alias_to_process_exe(self):
        self.require_production()
        for action in ("start", "status"):
            with self.subTest(action=action):
                fixture = LifecycleFixture(self)
                fixture.use_dsm_target_alias()
                if action == "status":
                    fixture.setup_controller()
                    fixture.setup_running()

                result = fixture.run_control(action)

                self.assertEqual(0, result.returncode, result.stderr)

    def test_start_validates_exact_config_modes_owner_and_manifest_hashes(self):
        self.require_production()
        for mutation in (
            "content", "mode", "owner", "symlink", "manifest-extra",
            "manifest-duplicate", "manifest-missing", "hash-tool",
        ):
            with self.subTest(mutation=mutation):
                fixture = LifecycleFixture(self)
                env = {}
                manifest = fixture.var / "config-manifest.sha256"
                if mutation == "content":
                    (fixture.config / "ups.conf").write_bytes(UPS_CONF + b"changed\n")
                elif mutation == "mode":
                    (fixture.config / "upsd.conf").chmod(0o644)
                elif mutation == "owner":
                    env["FAKE_BAD_OWNER_BASENAME"] = "upsd.users"
                elif mutation == "symlink":
                    target = fixture.config / "ups.conf"
                    replacement = fixture.root / "replacement.conf"
                    replacement.write_bytes(target.read_bytes())
                    target.unlink()
                    target.symlink_to(replacement)
                elif mutation == "manifest-extra":
                    manifest.write_text(manifest.read_text() + "0" * 64 + "  extra\n")
                elif mutation == "manifest-duplicate":
                    lines = manifest.read_text().splitlines(keepends=True)
                    manifest.write_text("".join((lines[0], lines[0], lines[1], lines[2])))
                elif mutation == "manifest-missing":
                    manifest.write_text("".join(manifest.read_text().splitlines(keepends=True)[:2]))
                else:
                    env["FAKE_SHA_FAIL"] = "1"
                result = fixture.run_control("start", env=env)
                self.assertEqual(1, result.returncode, result.stderr)
                fixture.assert_no_start_mutation()

    def test_start_requires_one_exact_usb_and_one_interface_number_zero(self):
        self.require_production()
        for mutation in (
            "valid", "absent", "wrong-serial", "duplicate-device", "no-interface",
            "wrong-interface", "duplicate-interface", "symlink-attribute",
        ):
            with self.subTest(mutation=mutation):
                fixture = LifecycleFixture(self)
                fixture.reset_usb()
                if mutation == "valid":
                    fixture.add_usb("2-1")
                elif mutation == "wrong-serial":
                    fixture.add_usb("2-1", serial="OTHER")
                elif mutation == "duplicate-device":
                    fixture.add_usb("2-1")
                    fixture.add_usb("3-1")
                elif mutation == "no-interface":
                    fixture.add_usb("2-1", interfaces=())
                elif mutation == "wrong-interface":
                    fixture.add_usb("2-1", interfaces=("01",))
                elif mutation == "duplicate-interface":
                    fixture.add_usb("2-1", interfaces=("00", "00"))
                elif mutation == "symlink-attribute":
                    fixture.add_usb("2-1")
                    value = fixture.usb / "vendor-value"
                    value.write_text("2b89\n")
                    attribute = fixture.usb / "2-1/idVendor"
                    attribute.unlink()
                    attribute.symlink_to(value)
                result = fixture.run_control("start")
                expected = 0 if mutation in ("valid", "absent") else 1
                self.assertEqual(expected, result.returncode, result.stderr)
                if expected != 0:
                    fixture.assert_no_start_mutation()

    def test_start_blocks_foreign_driver_server_or_controller_but_ignores_upsmon(self):
        self.require_production()
        for comm in ("usbhid-ups", "upsd", "upsdrvctl", "upsmon"):
            with self.subTest(comm=comm):
                fixture = LifecycleFixture(self)
                fixture.add_process(6000, comm, f"/foreign/{comm}", 777)
                result = fixture.run_control("start")
                self.assertEqual(0 if comm == "upsmon" else 1, result.returncode, result.stderr)
                if comm != "upsmon":
                    fixture.assert_no_start_mutation()
                self.assertTrue((fixture.proc / "6000").is_dir())

    def test_start_fails_closed_for_unreadable_pid_referenced_by_package_state(self):
        self.require_production()
        fixture = LifecycleFixture(self)
        fixture.add_process(6000, "upsmon", "/sbin/upsmon", 777, complete=False)
        fixture.identity("upsd", 6000, 777, fixture.target / "sbin/upsd")
        result = fixture.run_control("start")
        self.assertEqual(1, result.returncode, result.stderr)
        fixture.assert_no_start_mutation()
        self.assertTrue((fixture.run / "upsd.identity").is_file())
        self.assertTrue((fixture.proc / "6000").is_dir())

    def test_start_blocks_any_port_3493_listener_before_mutation(self):
        self.require_production()
        for mode in ("loopback", "wildcard", "ipv6", "multi"):
            with self.subTest(mode=mode):
                fixture = LifecycleFixture(self)
                result = fixture.run_control("start", env={"NETSTAT_MODE": mode})
                self.assertEqual(1, result.returncode, result.stderr)
                fixture.assert_no_start_mutation()

    def test_start_requires_exact_host_local_alias_before_mutation(self):
        self.require_production()
        fixture = LifecycleFixture(self)
        result = fixture.run_control("start", env={"ALIAS_PRESENT": "0"})
        self.assertEqual(1, result.returncode, result.stderr)
        fixture.assert_no_start_mutation()

    def test_start_reloads_late_references_before_reconcile_or_deletion(self):
        self.require_production()
        fixture = LifecycleFixture(self)
        result = fixture.run_control("start", env={"LATE_REFERENCE_PID": "4999"})
        self.assertEqual(1, result.returncode, result.stderr)
        fixture.assert_no_start_mutation()
        self.assertEqual("4999\n", (fixture.run / "upsd.pid").read_text())
        self.assertTrue((fixture.proc / "4999").is_dir())

    def test_failed_driver_command_cleans_its_partial_exact_process_only(self):
        self.require_production()
        fixture = LifecycleFixture(self)
        fixture.add_process(7000, "unrelated", "/foreign/unrelated", 123)
        marker = fixture.run / "unrelated.state"
        fixture.run.mkdir(mode=0o750)
        marker.write_text("preserve\n")
        result = fixture.run_control(
            "start", env={"DRIVER_START_RESULT": "7", "DRIVER_CREATE_ON_START": "1"}
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse((fixture.proc / str(fixture.DRIVER_PID)).exists())
        self.assertTrue((fixture.proc / "7000").is_dir())
        self.assertEqual("preserve\n", marker.read_text())
        self.assertTrue((fixture.run / "nut-us3000-controller.identity").is_file())

    def test_failed_driver_start_scans_malformed_native_state_and_retains_identity(self):
        self.require_production()
        fixture = LifecycleFixture(self)
        result = fixture.run_control(
            "start",
            env={
                "DRIVER_START_RESULT": "7",
                "DRIVER_NATIVE_PID_STATE": "malformed",
            },
        )
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertTrue((fixture.proc / str(fixture.DRIVER_PID)).is_dir())
        identity = fixture.run / "usbhid-ups.identity"
        self.assertTrue(identity.is_file())
        self.assertEqual(
            f"{fixture.DRIVER_PID}:{fixture.DRIVER_START}:"
            f"{fixture.target / 'libexec/nut/usbhid-ups'}\n",
            identity.read_text(),
        )
        self.assertEqual(
            "not-a-pid\n", (fixture.run / "usbhid-ups-ups.pid").read_text()
        )
        self.assertNotIn("upsdrvctl stop ups", fixture.commands())

    def test_upsd_or_health_failure_cleans_current_attempt_server_then_driver(self):
        self.require_production()
        for stage, env in (
            ("upsd", {"UPSD_RESULT": "9"}),
            ("health", {"UPSC_RESULT": "1"}),
        ):
            with self.subTest(stage=stage):
                fixture = LifecycleFixture(self)
                fixture.add_process(7000, "unrelated", "/foreign/unrelated", 123)
                result = fixture.run_control("start", env=env)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertFalse((fixture.proc / str(fixture.DRIVER_PID)).exists())
                self.assertFalse((fixture.proc / str(fixture.UPSD_PID)).exists())
                self.assertTrue((fixture.proc / "7000").is_dir())
                lines = fixture.commands()
                driver_stop = next(i for i, line in enumerate(lines) if line == "upsdrvctl stop ups")
                if stage == "health":
                    server_stop = next(i for i, line in enumerate(lines) if line.startswith("kill "))
                    self.assertLess(server_stop, driver_stop)

    def test_partial_upsd_failure_cleans_server_before_driver(self):
        self.require_production()
        fixture = LifecycleFixture(self)
        result = fixture.run_control(
            "start", env={"UPSD_RESULT": "9", "UPSD_CREATE_ON_FAILURE": "1"}
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse((fixture.proc / str(fixture.UPSD_PID)).exists())
        self.assertFalse((fixture.proc / str(fixture.DRIVER_PID)).exists())
        lines = fixture.commands()
        server_stop = next(i for i, line in enumerate(lines) if line.startswith("kill "))
        driver_stop = next(i for i, line in enumerate(lines) if line == "upsdrvctl stop ups")
        self.assertLess(server_stop, driver_stop)

    def test_health_uses_one_bounded_package_upsc_and_rejects_wrong_or_stale_data(self):
        self.require_production()
        bad_outputs = (
            HEALTHY.replace("driver.name: usbhid-ups", "driver.name: dummy-ups"),
            HEALTHY + "driver.name: dummy-ups\n",
            HEALTHY.replace("device.mfr: UGREEN\n", ""),
            HEALTHY + "ups.status: OL\n",
            HEALTHY.replace("ups.status: OL", "ups.status: OL NOCOMM"),
            HEALTHY.replace("ups.status: OL", "ups.status: STALE"),
            HEALTHY.replace("ups.status: OL", "ups.status:    "),
            HEALTHY.replace("ups.productid: ffff", "ups.productid: 0000"),
        )
        for output in (HEALTHY, *bad_outputs):
            with self.subTest(output=output.splitlines()[-1]):
                fixture = LifecycleFixture(self)
                fixture.upsc_output.write_text(output)
                result = fixture.run_health(env={"NETSTAT_MODE": "host-local"})
                self.assertEqual(0 if output == HEALTHY else 1, result.returncode, result.stderr)
                calls = [line for line in fixture.commands() if line.startswith("upsc ")]
                self.assertEqual(["upsc ups@127.0.0.1"], calls)
                timeout_calls = [line for line in fixture.commands() if line.startswith("timeout ")]
                self.assertEqual(1, len(timeout_calls))
                self.assertIn(str(fixture.target / "bin/upsc"), timeout_calls[0])

    def test_health_accepts_ol_dischrg_and_runtime_65535(self):
        self.require_production()
        fixture = LifecycleFixture(self)
        fixture.upsc_output.write_text(HEALTHY.replace("ups.status: OL", "ups.status: OL DISCHRG"))
        result = fixture.run_health(env={"NETSTAT_MODE": "host-local"})
        self.assertEqual(0, result.returncode, result.stderr)

    def test_status_requires_exact_controller_platform_host_and_valid_optional_state(self):
        self.require_production()
        valid = LifecycleFixture(self)
        valid.setup_controller()
        result = valid.run_control("status")
        self.assertEqual(0, result.returncode, result.stderr)
        for mutation in (
            "missing-identity", "malformed", "zombie", "reused", "wrong-exe",
            "bad-state", "state-symlink", "unsupported-platform", "host-audit",
        ):
            with self.subTest(mutation=mutation):
                fixture = LifecycleFixture(self)
                fixture.setup_controller()
                env = {}
                if mutation == "missing-identity":
                    (fixture.run / "nut-us3000-controller.identity").unlink()
                elif mutation == "malformed":
                    (fixture.run / "nut-us3000-controller.identity").write_text("not-an-identity\n")
                elif mutation == "zombie":
                    stat_path = fixture.proc / str(fixture.RETRY_PID) / "stat"
                    stat_path.write_text(stat_path.read_text().replace(") S ", ") Z ", 1))
                elif mutation == "reused":
                    stat_path = fixture.proc / str(fixture.RETRY_PID) / "stat"
                    stat_path.write_text(stat_path.read_text().replace(str(fixture.RETRY_START), "99999"))
                elif mutation == "wrong-exe":
                    exe = fixture.proc / str(fixture.RETRY_PID) / "exe"
                    exe.unlink()
                    exe.symlink_to("/foreign/controller")
                elif mutation == "bad-state":
                    state = fixture.run / "controller-health.state"
                    state.write_text("UNKNOWN\n")
                    state.chmod(0o600)
                elif mutation == "state-symlink":
                    external = fixture.root / "state"
                    external.write_text("HEALTHY\n")
                    (fixture.run / "controller-health.state").symlink_to(external)
                elif mutation == "unsupported-platform":
                    fixture.version.write_text('productversion="7.3.0"\nbuildnumber="80000"\n')
                else:
                    env["HOSTCTL_AUDIT_RESULT"] = "7"
                failed = fixture.run_control("status", env=env)
                self.assertEqual(1, failed.returncode, failed.stderr)

        degraded_core = LifecycleFixture(self)
        degraded_core.setup_controller()
        degraded_core.setup_running()
        degraded_core.upsc_output.write_text(HEALTHY.replace("ups.status: OL", "ups.status: STALE"))
        self.assertEqual(0, degraded_core.run_control("status").returncode)

    def test_stop_never_signals_missing_zombie_reused_wrong_or_unidentified_pid(self):
        self.require_production()
        for mutation in ("missing", "zombie", "reused", "wrong-exe", "unidentified"):
            with self.subTest(mutation=mutation):
                fixture = LifecycleFixture(self)
                fixture.setup_running()
                server = fixture.proc / str(fixture.UPSD_PID)
                if mutation == "missing":
                    shutil.rmtree(server)
                elif mutation == "zombie":
                    path = server / "stat"
                    path.write_text(path.read_text().replace(") S ", ") Z ", 1))
                elif mutation == "reused":
                    path = server / "stat"
                    path.write_text(path.read_text().replace(str(fixture.UPSD_START), "99999"))
                elif mutation == "wrong-exe":
                    (server / "exe").unlink()
                    (server / "exe").symlink_to("/foreign/upsd")
                else:
                    (fixture.run / "upsd.identity").unlink()
                result = fixture.run_control("stop")
                self.assertNotIn(
                    f"kill -TERM {fixture.UPSD_PID}", fixture.commands(),
                    f"{mutation} PID was signalled",
                )
                if mutation in ("reused", "wrong-exe", "unidentified"):
                    self.assertEqual(1, result.returncode, result.stderr)
                    self.assertNotIn("upsdrvctl stop ups", fixture.commands())
                else:
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertIn("upsdrvctl stop ups", fixture.commands())
                    self.assertFalse((fixture.run / "upsd.identity").exists())
                    self.assertFalse((fixture.run / "usbhid-ups.identity").exists())

    def test_stop_fails_closed_on_malformed_server_process_state(self):
        self.require_production()
        fixture = LifecycleFixture(self)
        fixture.setup_running()
        stat_path = fixture.proc / str(fixture.UPSD_PID) / "stat"
        stat_path.write_text(stat_path.read_text().replace(") S ", ") Q ", 1))

        result = fixture.run_control("stop")

        self.assertEqual(1, result.returncode, result.stderr)
        self.assertTrue((fixture.run / "upsd.identity").is_file())
        self.assertTrue((fixture.run / "usbhid-ups.identity").is_file())
        self.assertNotIn(f"kill -TERM {fixture.UPSD_PID}", fixture.commands())
        self.assertNotIn("upsdrvctl stop ups", fixture.commands())

    def test_start_reconcile_propagates_server_state_removal_failure(self):
        self.require_production()
        fixture = LifecycleFixture(self)
        fixture.run.mkdir(mode=0o750)
        native = fixture.run / "upsd.pid"
        native.write_text("4999\n")

        result = fixture.run_control(
            "start", env={"RM_FAIL_PATH": str(fixture.run / "upsd.identity")}
        )

        self.assertEqual(1, result.returncode, result.stderr)
        self.assertEqual("4999\n", native.read_text())
        self.assertFalse(any("upsdrvctl start" in line for line in fixture.commands()))
        self.assertFalse(any(line.startswith("upsd ") for line in fixture.commands()))

    def test_stop_server_propagates_state_removal_failure(self):
        self.require_production()
        for state in ("no-identity", "missing", "zombie"):
            with self.subTest(state=state):
                fixture = LifecycleFixture(self)
                if state == "no-identity":
                    fixture.setup_running(driver=True, server=False)
                    (fixture.run / "upsd.pid").write_text("4999\n")
                else:
                    fixture.setup_running()
                    server = fixture.proc / str(fixture.UPSD_PID)
                    if state == "missing":
                        shutil.rmtree(server)
                    else:
                        stat_path = server / "stat"
                        stat_path.write_text(
                            stat_path.read_text().replace(") S ", ") Z ", 1)
                        )

                result = fixture.run_control(
                    "stop", env={"RM_FAIL_PATH": str(fixture.run / "upsd.identity")}
                )

                self.assertEqual(1, result.returncode, result.stderr)
                self.assertTrue((fixture.run / "upsd.pid").is_file())
                if state != "no-identity":
                    self.assertTrue((fixture.run / "upsd.identity").is_file())
                self.assertTrue((fixture.run / "usbhid-ups.identity").is_file())
                self.assertNotIn(f"kill -TERM {fixture.UPSD_PID}", fixture.commands())
                self.assertNotIn("upsdrvctl stop ups", fixture.commands())

    def test_stop_driver_propagates_state_removal_failure(self):
        self.require_production()
        for state in ("no-identity", "missing", "zombie", "post-success"):
            with self.subTest(state=state):
                fixture = LifecycleFixture(self)
                if state == "no-identity":
                    fixture.run.mkdir(mode=0o750)
                    (fixture.run / "usbhid-ups-ups.pid").write_text("4999\n")
                    (fixture.run / "usbhid-ups-ups").write_text("fixture socket\n")
                else:
                    fixture.setup_running(driver=True, server=False)
                    driver = fixture.proc / str(fixture.DRIVER_PID)
                    if state == "missing":
                        shutil.rmtree(driver)
                    elif state == "zombie":
                        stat_path = driver / "stat"
                        stat_path.write_text(
                            stat_path.read_text().replace(") S ", ") Z ", 1)
                        )

                result = fixture.run_control(
                    "stop",
                    env={"RM_FAIL_PATH": str(fixture.run / "usbhid-ups.identity")},
                )

                self.assertEqual(1, result.returncode, result.stderr)
                self.assertTrue((fixture.run / "usbhid-ups-ups.pid").is_file())
                self.assertTrue((fixture.run / "usbhid-ups-ups").is_file())
                if state != "no-identity":
                    self.assertTrue((fixture.run / "usbhid-ups.identity").is_file())
                if state == "post-success":
                    self.assertFalse((fixture.proc / str(fixture.DRIVER_PID)).exists())
                    self.assertEqual(1, fixture.commands().count("upsdrvctl stop ups"))

    def test_start_rejects_driver_native_pid_mismatch_and_retains_exact_evidence(self):
        self.require_production()
        fixture = LifecycleFixture(self)
        result = fixture.run_control("start", env={"DRIVER_NATIVE_PID": "4999"})
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertTrue((fixture.proc / str(fixture.DRIVER_PID)).is_dir())
        self.assertTrue((fixture.run / "usbhid-ups.identity").is_file())
        self.assertNotIn("upsdrvctl stop ups", fixture.commands())
        self.assertFalse(any(line.startswith("upsd ") for line in fixture.commands()))

    def test_start_recovers_one_exact_driver_when_native_pidfile_is_missing(self):
        self.require_production()
        fixture = LifecycleFixture(self)
        result = fixture.run_control(
            "start", env={"DRIVER_NATIVE_PID_STATE": "missing"}
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((fixture.run / "usbhid-ups.identity").is_file())
        self.assertTrue((fixture.proc / str(fixture.DRIVER_PID)).is_dir())

    def test_failed_start_cleans_unique_partial_exact_upsdrvctl(self):
        self.require_production()
        fixture = LifecycleFixture(self)
        result = fixture.run_control(
            "start",
            env={
                "CONTROLLER_CREATE_ON_START": "1",
                "DRIVER_CREATE_ON_START": "0",
                "DRIVER_START_RESULT": "7",
            },
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse((fixture.proc / str(fixture.CONTROLLER_PID)).exists())
        self.assertIn(f"kill -TERM {fixture.CONTROLLER_PID}", fixture.commands())
        self.assertNotIn("upsdrvctl stop ups", fixture.commands())

    def test_stop_is_server_first_driver_second_and_every_wait_is_bounded(self):
        self.require_production()
        fixture = LifecycleFixture(self)
        fixture.setup_running()
        result = fixture.run_control("stop")
        self.assertEqual(0, result.returncode, result.stderr)
        lines = fixture.commands()
        server_stop = next(i for i, line in enumerate(lines) if line == f"kill -TERM {fixture.UPSD_PID}")
        driver_stop = next(i for i, line in enumerate(lines) if line == "upsdrvctl stop ups")
        self.assertLess(server_stop, driver_stop)
        bounded_driver = [
            line for line in lines
            if line.startswith("timeout -k 1 3 ") and "upsdrvctl stop ups" in line
        ]
        self.assertEqual(1, len(bounded_driver))
        self.assertLessEqual(sum(line.startswith("sleep ") for line in lines), 6)
        for basename in ("upsd.identity", "usbhid-ups.identity"):
            self.assertFalse((fixture.run / basename).exists())

    def test_hung_exact_server_returns_nonzero_retains_evidence_and_skips_driver(self):
        self.require_production()
        fixture = LifecycleFixture(self)
        fixture.setup_running()
        result = fixture.run_control("stop", env={"KILL_HUNG_PID": str(fixture.UPSD_PID)})
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertTrue((fixture.run / "upsd.identity").is_file())
        self.assertTrue((fixture.run / "usbhid-ups.identity").is_file())
        self.assertNotIn("upsdrvctl stop ups", fixture.commands())
        self.assertLessEqual(sum(line.startswith("sleep ") for line in fixture.commands()), 3)

    def test_stop_stops_valid_server_before_failing_on_malformed_driver_state(self):
        self.require_production()
        fixture = LifecycleFixture(self)
        fixture.setup_running()
        (fixture.run / "usbhid-ups.identity").write_text("malformed\n")
        result = fixture.run_control("stop")
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertFalse((fixture.proc / str(fixture.UPSD_PID)).exists())
        self.assertFalse((fixture.run / "upsd.identity").exists())
        self.assertTrue((fixture.proc / str(fixture.DRIVER_PID)).is_dir())
        self.assertEqual("malformed\n", (fixture.run / "usbhid-ups.identity").read_text())
        self.assertIn(f"kill -TERM {fixture.UPSD_PID}", fixture.commands())
        self.assertNotIn("upsdrvctl stop ups", fixture.commands())

    def test_stop_command_failures_are_nonzero_bounded_and_retain_evidence(self):
        self.require_production()
        server = LifecycleFixture(self)
        server.setup_running()
        server_result = server.run_control("stop", env={"KILL_RESULT": "7"})
        self.assertEqual(1, server_result.returncode, server_result.stderr)
        self.assertTrue((server.run / "upsd.identity").is_file())
        self.assertNotIn("upsdrvctl stop ups", server.commands())

        driver = LifecycleFixture(self)
        driver.setup_running()
        driver_result = driver.run_control("stop", env={"DRIVER_STOP_RESULT": "7"})
        self.assertEqual(1, driver_result.returncode, driver_result.stderr)
        self.assertTrue((driver.run / "usbhid-ups.identity").is_file())
        self.assertEqual(1, driver.commands().count("upsdrvctl stop ups"))

    def test_stop_fails_closed_on_malformed_relevant_native_pid_state(self):
        self.require_production()
        fixture = LifecycleFixture(self)
        fixture.setup_running()
        shutil.rmtree(fixture.proc / str(fixture.UPSD_PID))
        (fixture.run / "upsd.pid").write_text("not-a-pid\n")
        result = fixture.run_control("stop")
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertTrue((fixture.run / "upsd.identity").is_file())
        self.assertEqual("not-a-pid\n", (fixture.run / "upsd.pid").read_text())
        self.assertNotIn("upsdrvctl stop ups", fixture.commands())

    def test_stop_fails_closed_on_unreadable_proc_pid_referenced_only_by_native_state(self):
        self.require_production()
        fixture = LifecycleFixture(self)
        fixture.setup_running(driver=True, server=False)
        fixture.add_process(6100, "upsmon", "/sbin/upsmon", 778, complete=False)
        (fixture.run / "upsd.pid").write_text("6100\n")
        result = fixture.run_control("stop")
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertEqual("6100\n", (fixture.run / "upsd.pid").read_text())
        self.assertTrue((fixture.proc / "6100").is_dir())
        self.assertNotIn("upsdrvctl stop ups", fixture.commands())

    def test_hung_exact_driver_returns_nonzero_and_retains_driver_identity(self):
        self.require_production()
        fixture = LifecycleFixture(self)
        fixture.setup_running()
        result = fixture.run_control("stop", env={"DRIVER_STOP_HUNG": "1"})
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertTrue((fixture.run / "usbhid-ups.identity").is_file())
        self.assertTrue((fixture.proc / str(fixture.DRIVER_PID)).is_dir())
        self.assertEqual(1, fixture.commands().count("upsdrvctl stop ups"))

    def test_real_preuninst_scans_exact_package_processes_and_fails_closed_on_unknown(self):
        self.require_production()
        cases = ("absent", "driver", "server", "controller", "malformed-pid", "unknown-relevant")
        for kind in cases:
            with self.subTest(kind=kind):
                fixture = LifecycleFixture(self)
                if kind == "driver":
                    fixture.add_process(
                        8101, "usbhid-ups", fixture.target / "libexec/nut/usbhid-ups", 11
                    )
                elif kind == "server":
                    fixture.add_process(8102, "upsd", fixture.target / "sbin/upsd", 12)
                elif kind == "controller":
                    fixture.add_process(8103, "upsdrvctl", fixture.target / "sbin/upsdrvctl", 13)
                elif kind == "malformed-pid":
                    fixture.run.mkdir(mode=0o750)
                    (fixture.run / "upsd.pid").write_text("not-a-pid\n")
                elif kind == "unknown-relevant":
                    fixture.add_process(8104, "upsd", "/foreign/upsd", 14, complete=False)
                result = fixture.run_preuninst()
                self.assertEqual(0 if kind == "absent" else 1, result.returncode, result.stderr)

        unrelated = LifecycleFixture(self)
        unrelated.add_process(8200, "unrelated", "/foreign/unrelated", 20, complete=False)
        result = unrelated.run_preuninst()
        self.assertEqual(0, result.returncode, result.stderr)

    def test_bad_argv_is_64_and_executed_commands_stay_inside_safe_boundary(self):
        self.require_production()
        for args in ((), ("bogus",), ("start", "extra")):
            with self.subTest(args=args):
                fixture = LifecycleFixture(self)
                result = fixture.run_control(*args)
                self.assertEqual(64, result.returncode, result.stderr)
        health = LifecycleFixture(self)
        result = health.run_health("unexpected")
        self.assertEqual(64, result.returncode, result.stderr)

        fixture = LifecycleFixture(self)
        fixture.add_process(6000, "upsmon", "/sbin/upsmon", 77)
        started = fixture.run_control("start")
        self.assertEqual(0, started.returncode, started.stderr)
        stopped = fixture.run_control("stop")
        self.assertEqual(0, stopped.returncode, stopped.stderr)
        self.assertTrue((fixture.proc / "6000").is_dir())
        fixture.assert_safe_log()


if __name__ == "__main__":
    unittest.main()
