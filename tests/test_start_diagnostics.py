"""Only the new startup diagnostics; no USB, systemd or NAS operations.

Deterministic clocks exercise existing deadlines without real waiting.
Temporary executables and fake package trees are removed even on failure.
"""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
NATIVE = ROOT / "spk/package/native"
HARNESS = r'''
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include "ram-exec.h"
#include "ram-runtime.h"
static long long ticks=100000;
static int driver,server,scans,queries,stops;
static const char *fault;
static int fake_clock(clockid_t c,struct timespec *t) {
    (void)c;t->tv_sec=ticks/1000;t->tv_nsec=ticks%1000*1000000;return 0;
}
static int fake_sleep(const struct timespec *t,struct timespec *rest) {
    (void)rest;ticks+=t->tv_sec*1000+t->tv_nsec/1000000;return 0;
}
#define clock_gettime fake_clock
#define nanosleep fake_sleep
#include "ram-runtime.c"
#undef clock_gettime
#undef nanosleep
static void output(struct nutram_exec_result *r,const char *fmt,...) {
    va_list a;va_start(a,fmt);r->out_size=vsnprintf(r->out,sizeof(r->out),fmt,a);va_end(a);
}
int nutram_exec(enum nutram_operation op,struct nutram_exec_result *r) {
    memset(r,0,sizeof(*r));
    if(op==NUTRAM_START_DRIVER) {
        driver=1;
        if(!strcmp(fault,"driver_exit"))r->exit_code=42;
    } else if(op==NUTRAM_START_SERVER) {
        server=1;
        if(!strcmp(fault,"server_timeout"))return NUTRAM_EXEC_TIMEOUT;
    } else if(op==NUTRAM_STOP_DRIVER) {driver=0;stops++;}
    else if(op==NUTRAM_STOP_SERVER) {
        stops++;
        if(!strcmp(fault,"unwind"))return NUTRAM_EXEC_SETUP;
        server=0;
    } else if(op==NUTRAM_SHOW_DRIVER || op==NUTRAM_SHOW_SERVER) {
        int live=op==NUTRAM_SHOW_DRIVER?driver:server;
        const char *role=op==NUTRAM_SHOW_DRIVER?"driver":"server";
        char group[128]="";
        if(live)snprintf(group,sizeof(group),"/nutus3000_ram.slice/nut-us3000-ram-%s.service",role);
        output(r,"Id=nut-us3000-ram-%s.service\nLoadState=loaded\nActiveState=%s\nSubState=%s\nMainPID=%d\nControlPID=0\nControlGroup=%s\n",
            role,live?"active":"inactive",live?"running":"dead",live?(op==NUTRAM_SHOW_DRIVER?43:42):0,group);
        if(!strcmp(fault,"unit_parse"))output(r,"Id=SECRET_DO_NOT_LOG\n");
        if(!strcmp(fault,"unit_rc1"))r->exit_code=1;
    } else if(op==NUTRAM_CORE_INVENTORY) {
        scans++;
        if(!strcmp(fault,"inventory_exit")) {ticks+=1600;r->exit_code=7;}
        else if(!strcmp(fault,"inventory_mismatch")) {ticks+=1600;output(r,"SECRET_DO_NOT_LOG\n");}
        else if((!strcmp(fault,"recover_after_two") && scans<=2) ||
                ((!strcmp(fault,"recover_after_eleven") || !strcmp(fault,"slow_core_stale")) && scans<=11)) {
            ticks+=1600;r->exit_code=7;
        }
        else {ticks+=10;output(r,"server=42\ndriver=43\n");}
    } else if(op==NUTRAM_QUERY_LOCAL || op==NUTRAM_QUERY_ALIAS) {
        queries++;
        output(r,"driver.name: nutus3000-hid\ndevice.mfr: UGREEN\ndevice.model: US3000\nups.vendorid: 2b89\nups.productid: ffff\nups.status: OL DISCHRG\n");
        if(!strcmp(fault,"query_timeout"))return NUTRAM_EXEC_TIMEOUT;
        if(!strcmp(fault,"identity") || !strcmp(fault,"unwind"))output(r,"driver.name: SECRET_DO_NOT_LOG\ndevice.mfr: UGREEN\ndevice.model: US3000\nups.vendorid: 2b89\nups.productid: ffff\nups.status: OL\n");
        if(!strcmp(fault,"unavailable") || !strcmp(fault,"slow_core_stale")) {
            r->out[0]=0;r->out_size=0;r->exit_code=1;
            strcpy(r->err,"Error: Data stale\n");r->err_size=strlen(r->err);
        }
    } else if(op!=NUTRAM_KERNEL_QUIESCENT)return NUTRAM_EXEC_SETUP;
    return NUTRAM_EXEC_OK;
}
int nutram_query_until(enum nutram_operation op,long long deadline,struct nutram_exec_result *r) {
    if(ticks>=deadline)return NUTRAM_EXEC_TIMEOUT;
    return nutram_exec(op,r);
}
static int remaining(enum nutram_phase p) {return p==NUTRAM_USB_PRESENT?(!strcmp(fault,"usb_absent")?75:0):1;}
int main(int argc,char **argv) {
    fault=argc>1?argv[1]:"success";
    if(argc>2)close(2);
    int rc=nutram_runtime_phase(!strcmp(fault,"health_only")?NUTRAM_HEALTH:NUTRAM_START,remaining);
    printf("rc=%d scans=%d queries=%d stops=%d elapsed=%lld\n",rc,scans,queries,stops,ticks-100000);
    return 0;
}
'''


class RuntimeDiagnostics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="nut-0027-runtime-")
        cls.addClassCleanup(cls.tmp.cleanup)
        source = pathlib.Path(cls.tmp.name) / "fixture.c"
        source.write_text(HARNESS)
        cls.exe = pathlib.Path(cls.tmp.name) / "fixture"
        subprocess.run([shutil.which("cc"), "-std=c99", "-D_POSIX_C_SOURCE=200809L",
                        "-Wall", "-Wextra", "-Werror", "-I", str(NATIVE), str(source),
                        "-o", str(cls.exe)], check=True, capture_output=True)

    def run_case(self, case, closed=False):
        p = subprocess.run([str(self.exe), case] + (["closed"] if closed else []),
                           capture_output=True, text=True, check=True)
        self.assertNotIn("SECRET_DO_NOT_LOG", p.stderr)
        return p

    def test_core_window_records_original_cause_before_unwind(self):
        p = self.run_case("inventory_exit")
        self.assertEqual(p.stdout, "rc=1 scans=13 queries=0 stops=2 elapsed=21400\n")
        self.assertIn("stage=core_wait reason=exec_exit op=core_inventory transport=0 child=7", p.stderr)
        self.assertIn("reason=core_deadline", p.stderr)
        self.assertLess(p.stderr.index("reason=core_deadline"), p.stderr.index("stage=unwind"))

    def test_transient_core_can_recover_after_three_and_ten_seconds(self):
        for case, expected in [
            ("recover_after_two", "rc=0 scans=3 queries=2 stops=0 elapsed=3310\n"),
            ("recover_after_eleven", "rc=0 scans=12 queries=2 stops=0 elapsed=18160\n"),
        ]:
            with self.subTest(case=case):
                p = self.run_case(case)
                self.assertEqual(p.stdout, expected)
                self.assertIn("stage=core_wait reason=exec_exit", p.stderr)
                self.assertIn("reason=complete", p.stderr)
                self.assertNotIn("reason=core_deadline", p.stderr)
                self.assertNotIn("stage=unwind", p.stderr)

    def test_slow_core_does_not_consume_separate_data_budget(self):
        p = self.run_case("slow_core_stale")
        self.assertEqual(p.stdout, "rc=75 scans=12 queries=40 stops=2 elapsed=38160\n")
        self.assertNotIn("reason=core_deadline", p.stderr)
        self.assertIn("reason=data_deadline", p.stderr)

    def test_distinct_failures(self):
        for case, expected in [
            ("inventory_mismatch", "reason=inventory_mismatch"),
            ("unit_parse", "reason=unit_missing_field"),
            ("unit_rc1", "op=show_server transport=0 child=1"),
            ("driver_exit", "op=start_driver transport=0 child=42"),
            ("server_timeout", "op=start_server transport=1 child=-1"),
            ("query_timeout", "op=query_local transport=1 child=-1"),
            ("identity", "reason=data_identity"),
            ("unwind", "stage=unwind reason=exec_transport"),
        ]:
            with self.subTest(case=case):
                p = self.run_case(case)
                self.assertTrue(p.stdout.startswith("rc=1 "))
                self.assertIn(expected, p.stderr)

    def test_data_deadline_unchanged(self):
        p = self.run_case("unavailable")
        self.assertEqual(p.stdout, "rc=75 scans=1 queries=40 stops=2 elapsed=20010\n")
        self.assertIn("reason=data_deadline", p.stderr)

    def test_success_and_absent(self):
        p = self.run_case("success")
        self.assertEqual(p.stdout, "rc=0 scans=1 queries=2 stops=0 elapsed=10\n")
        self.assertIn("reason=complete", p.stderr)
        p = self.run_case("usb_absent")
        self.assertEqual(p.stdout, "rc=75 scans=0 queries=0 stops=0 elapsed=0\n")
        self.assertIn("stage=usb_probe", p.stderr)

    def test_logging_does_not_change_result_and_health_stays_quiet(self):
        for case in ("success", "inventory_exit", "unit_parse", "unavailable"):
            with self.subTest(case=case):
                self.assertEqual(self.run_case(case).stdout, self.run_case(case, True).stdout)
        self.assertEqual(self.run_case("health_only").stderr, "")


class HookDiagnostics(unittest.TestCase):
    def test_start_stages_and_unchanged_return(self):
        functions = ["init", "validate_platform", "validate_config", "prepare_run",
                     "publish_controller_state", "controller_start"]
        with tempfile.TemporaryDirectory(prefix="nut-0026-hook-") as tmp:
            root = pathlib.Path(tmp)
            lib = root / "share/nut-us3000/lib.sh"
            helper = root / "libexec/nut/nut-us3000-hostctl"
            lib.parent.mkdir(parents=True)
            helper.parent.mkdir(parents=True)
            helper.write_text("#!/bin/sh\n[ \"$1\" = ram-start ] && echo RAM_STATE=HEALTHY\nexit 0\n")
            helper.chmod(0o755)
            for failure in functions + ["none"]:
                with self.subTest(failure=failure):
                    text = "nutus3000_description_publish() { :; }\nnutus3000_description_finish() { trap - EXIT; exit \"$1\"; }\nnutus3000_controller_status() { return 1; }\n"
                    text += "\n".join(f"nutus3000_{name}() {{ return {9 if name == failure else 0}; }}" for name in functions)
                    lib.write_text(text + "\n")
                    p = subprocess.run(["/bin/sh", str(ROOT / "spk/package/scripts/start-stop-status"), "start"],
                                       env={"PATH": "/usr/bin:/bin", "SYNOPKG_PKGDEST": tmp}, capture_output=True, text=True)
                    self.assertEqual(p.returncode, 0 if failure == "none" else 1)
                    self.assertEqual(p.stdout, "")
                    self.assertIn(f"layer=hook stage={failure if failure != 'none' else 'complete'}", p.stderr)
                    self.assertIn(f"operation_rc={0 if failure == 'none' else 9}", p.stderr)


if __name__ == "__main__":
    unittest.main()
