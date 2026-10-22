"""0028: real runtime/parser, simulated executor and clock; no NAS or USB.

Breaks caught: fatal initial partial replies, false readiness on partial data,
hidden wrong identity, changed normal HEALTH, or an unbounded readiness wait.
The upstream WAIT-only reply is possible before its initial DUMPALL completes;
the exact failed NAS reply was not captured and is not claimed as a fixture.
"""
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

from test_start_diagnostics import HARNESS, NATIVE

INJECT = r'''
        int index=0, use_alias=0, permanent=0, health_case=0;
        int partial=sscanf(fault,"partial_%d_%d_%d_%d",&index,&use_alias,&permanent,&health_case)==4;
        if(partial && (health_case || permanent || queries==(use_alias?2:1)) &&
           op==(use_alias?NUTRAM_QUERY_ALIAS:NUTRAM_QUERY_LOCAL)) {
            const char *lines[]={"driver.name: nutus3000-hid\n","device.mfr: UGREEN\n",
                "device.model: US3000\n","ups.vendorid: 2b89\n",
                "ups.productid: ffff\n","ups.status: OL\n"};
            output(r,"");
            for(int i=0;i<6;i++)if(i!=index)strcat(r->out,lines[i]);
            r->out_size=strlen(r->out);
        }
        if(queries==1 && !strcmp(fault,"wait_then_ready"))output(r,"ups.status: WAIT\n");
        if(queries==1 && !strcmp(fault,"wrong_and_missing"))output(r,"driver.name: SECRET_DO_NOT_LOG\nups.status: WAIT\n");
        if(queries==1 && !strcmp(fault,"duplicate_and_missing"))output(r,"ups.status: WAIT\nups.status: OL\n");
        if(queries==1 && !strcmp(fault,"malformed_and_missing"))output(r,"ups.status: WAIT\nbroken\n");
        if(queries==1 && !strcmp(fault,"contradictory_and_missing"))output(r,"ups.status: OL OB\n");
        if(queries==1 && !strcmp(fault,"transport_and_missing")) {
            output(r,"ups.status: WAIT\n");return NUTRAM_EXEC_TIMEOUT;
        }
        if(queries==1 && !strcmp(fault,"denied_and_missing")) {
            output(r,"ups.status: WAIT\n");r->exit_code=1;
            strcpy(r->err,"Error: Access denied\n");r->err_size=strlen(r->err);
        }
'''


class PartialStartupData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="nut-0028-partial-")
        cls.addClassCleanup(cls.tmp.cleanup)
        source = pathlib.Path(cls.tmp.name) / "fixture.c"
        anchor = '        if(!strcmp(fault,"query_timeout"))return NUTRAM_EXEC_TIMEOUT;'
        assert HARNESS.count(anchor) == 1
        text = HARNESS.replace(anchor, INJECT + anchor)
        text = text.replace('!strcmp(fault,"health_only")?NUTRAM_HEALTH:NUTRAM_START',
                            '(argc>2 && !strcmp(argv[2],"health"))?NUTRAM_HEALTH:NUTRAM_START')
        text = text.replace('if(argc>2)close(2);', 'if(argc>2 && !strcmp(argv[2],"closed"))close(2);')
        source.write_text(text)
        cls.exe = pathlib.Path(cls.tmp.name) / "fixture"
        subprocess.run([shutil.which("cc"), "-std=c99", "-D_POSIX_C_SOURCE=200809L",
                        "-Wall", "-Wextra", "-Werror", "-I", str(NATIVE),
                        str(source), "-o", str(cls.exe)], check=True, capture_output=True)

    def case(self, name, mode=None):
        p = subprocess.run([str(self.exe), name] + ([mode] if mode else []),
                           capture_output=True, text=True, check=True, timeout=5)
        self.assertNotIn("SECRET_DO_NOT_LOG", p.stderr)
        fields = dict((k, int(v)) for k, v in re.findall(r"(\w+)=(\d+)", p.stdout))
        return p, fields

    def test_each_missing_field_retries_on_both_endpoints_before_ready(self):
        for endpoint in (0, 1):
            for field in range(6):
                with self.subTest(endpoint=endpoint, field=field):
                    p, f = self.case(f"partial_{field}_{endpoint}_0_0")
                    self.assertEqual(f, dict(rc=0, scans=1, queries=4, stops=0, elapsed=1010))
                    self.assertRegex(p.stderr, rf"reason=data_missing_field .*missing_mask={1 << field}(?:\s|$)")
                    self.assertNotIn("stage=unwind", p.stderr)

    def test_upstream_wait_only_reply_converges(self):
        p, f = self.case("wait_then_ready")
        self.assertEqual(f, dict(rc=0, scans=1, queries=4, stops=0, elapsed=1010))
        self.assertRegex(p.stderr, r"reason=data_missing_field .*missing_mask=31(?:\s|$)")

    def test_permanent_partial_uses_existing_budget_then_unwinds_not_usb_absence(self):
        p, f = self.case("partial_2_1_1_0")
        self.assertEqual(f, dict(rc=1, scans=1, queries=40, stops=2, elapsed=20010))
        self.assertIn("reason=data_deadline", p.stderr)
        self.assertIn("stage=unwind", p.stderr)

    def test_partial_does_not_hide_fatal_errors(self):
        for name, reason in [("wrong_and_missing", "data_identity"),
                             ("duplicate_and_missing", "data_duplicate_field"),
                             ("malformed_and_missing", "data_syntax"),
                             ("contradictory_and_missing", "power_status"),
                             ("transport_and_missing", "exec_transport"),
                             ("denied_and_missing", "query_response")]:
            with self.subTest(name=name):
                p, f = self.case(name)
                self.assertEqual(f, dict(rc=1, scans=1, queries=1, stops=2, elapsed=10))
                self.assertIn("reason=" + reason, p.stderr)

    def test_normal_health_stays_strict_and_quiet(self):
        for endpoint in (0, 1):
            for field in range(6):
                with self.subTest(endpoint=endpoint, field=field):
                    p, f = self.case(f"partial_{field}_{endpoint}_1_1", "health")
                    self.assertEqual(f, dict(rc=2, scans=0, queries=endpoint + 1, stops=0, elapsed=0))
                    self.assertEqual(p.stderr, "")

    def test_missing_diagnostics_are_optional_not_part_of_readiness(self):
        self.assertEqual(self.case("wait_then_ready")[1],
                         self.case("wait_then_ready", "closed")[1])


if __name__ == "__main__":
    unittest.main()
