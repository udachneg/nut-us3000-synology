"""New bridge journal checks, ONLY inside the task's disposable Linux container.

Real bridge/files/locks and generated payload; phase effects are fixed stubs.
No systemd, USB, NAS, existing lifecycle suite or privileges on the host.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "spk/package/native"
CONTROL = Path("/run/nut-us3000-control")
PROBE = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ram-bridge.h"
static int fail_phase=-1;
static int binding(enum nutram_phase p) {return (int)p==fail_phase?19:0;}
int main(int argc,char **argv) {
    fail_phase=argc>1?atoi(argv[1]):-1;
    char *args[]={argv[0],argc>2?argv[2]:"ram-start",NULL};
    return nutram_bridge_dispatch(2,args,binding);
}
'''


class BridgeDiagnostics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("NUT_DIAG_ISOLATED") != "0026-disposable-container":
            raise RuntimeError("Run only in the disposable diagnostic container")
        if CONTROL.exists():
            raise RuntimeError("Refusing pre-existing control directory")
        cls.tmp = tempfile.TemporaryDirectory(prefix="nut-0026-bridge-")
        cls.addClassCleanup(cls.tmp.cleanup)
        work = Path(cls.tmp.name)
        (work / "ram-payload.h").write_bytes(subprocess.check_output(
            ["python3", "-B", str(NATIVE / "embed_ram_payload.py")]))
        (work / "probe.c").write_text(PROBE)
        cls.exe = work / "probe"
        subprocess.run(["cc", "-std=c99", "-D_GNU_SOURCE", "-Wall", "-Wextra", "-Werror",
                        "-I" + str(NATIVE), "-I" + str(work), str(NATIVE / "ram-bridge.c"),
                        str(work / "probe.c"), "-o", str(cls.exe)], check=True, capture_output=True)

    def setUp(self):
        self.assertFalse(CONTROL.exists())
        self.addCleanup(lambda: shutil.rmtree(CONTROL) if CONTROL.exists() else None)

    def call(self, phase=-1, verb="ram-start"):
        return subprocess.run([str(self.exe), str(phase), verb], text=True,
                              capture_output=True, timeout=10)

    def test_failed_phase_and_protocol(self):
        for phase, name in [(0, "prepare"), (1, "ensure"), (2, "audit"), (5, "start")]:
            with self.subTest(phase=name):
                p = self.call(phase)
                self.assertEqual((p.returncode, p.stdout), (1, ""), p.stderr)
                self.assertIn(f"stage={name} event=result rc=19", p.stderr)
                self.assertIn(f"stage={name} event=complete rc=1", p.stderr)
                shutil.rmtree(CONTROL)

    def test_success_and_retry_quiet(self):
        p = self.call()
        self.assertEqual((p.returncode, p.stdout), (0, "RAM_STATE=HEALTHY\n"), p.stderr)
        self.assertIn("layer=bridge", p.stderr)
        self.assertIn("event=complete rc=0", p.stderr)
        p = self.call(verb="ram-retry")
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "RAM_STATE=HEALTHY\n", ""))

    def test_unrecognized_root_is_reported_not_adopted(self):
        CONTROL.mkdir(mode=0o700)
        (CONTROL / "sentinel").write_text("SECRET_DO_NOT_LOG")
        p = self.call()
        self.assertEqual((p.returncode, p.stdout), (1, ""))
        self.assertIn("stage=bootstrap event=complete rc=1", p.stderr)
        self.assertNotIn("SECRET_DO_NOT_LOG", p.stderr)
        self.assertEqual([p.name for p in CONTROL.iterdir()], ["sentinel"])


if __name__ == "__main__":
    unittest.main()
