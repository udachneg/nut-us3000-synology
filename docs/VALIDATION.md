# Validation status — 2.8.5-0022 RC1

Status: `RC_PENDING_PUBLIC_CLEAN_INSTALL` — not a final stable release.

Artifact: `nut-us3000_epyc7002-7.2_2.8.5-0022.spk`
SHA-256: `cd3fbec1def596f4048a0280e6734e4d37d66c10c77e84a3763af3988c2ca72f`

## Tested matrix

Xpenology/Arc DSM 7.2.2-72806, SA6400, epyc7002/x86-64;
UGREEN US3000 USB 2b89:ffff, serial DC600; NUT 2.8.5 / Arduino HID 0.22;
libusb 1.0.29. Arc Apps & Permissions was not required for the normal path.
Other DSM builds, official Synology hardware and other UPS devices are unverified.

## Evidence available before publication

| Check | Result and scope |
| --- | --- |
| 0022 offline builds, 2026-10-19 | Two builds with network disabled; normalized manifests identical; source inputs unchanged; canonical SPK audited. No rebuild for publication. |
| 0022 delay diagnostics | Actual INFO writer checked for 300 seconds, other/missing delay, unchanged boot/freshness timers. Three checks passed. |
| 0021 → 0022 upgrade, 2026-10-19 | Passed; version/running state, preserved NUT configuration, local endpoints, DSM connection and 300-second delay verified. No NAS reboot or power interruption. |
| 0022 keep-data uninstall/reinstall, 2026-10-19 | Passed through Package Center. Removal stopped RAM services and removed listeners/alias; exact USB interface restored. Reinstall preserved configuration bytes/modes, restored service and DSM connection with 300 seconds. NAS boot and unrelated container start times unchanged. |
| Inherited RAM lifecycle evidence | Isolated Linux/systemd VM tests, DSM-like stop ordering and queue inspection, plus 0021 ordinary stop/start and live recovery observations. Runtime server/driver/controller/hooks are unchanged between 0021 and 0022. These were not rerun for text/version changes. |

Private logs and infrastructure identifiers are deliberately not distributed.
This is a summary of recorded evidence, not a claim of testing every host.

## Full safe-mode observation and limitation

On 0021, with a temporary **one-minute DSM delay** for that test (not the new
five-minute setting), the recorded sequence was battery power at 18:03:31, data volumes absent
by 18:06:25, restored mains at 18:07:09, and SSH available after an automatic reboot
at 18:12:54 (one local clock, 2026-10-19). RAM runtime was observed alive while
data volumes were absent. DSM recovery was observed on this host. SSH was verified
5m45s after mains restoration, outside the planned five-minute observation window;
this is an upper bound on availability, not its exact first instant.

The old temporary observer gate did **not** produce a formal PASS: it used an
ExecMain timestamp that remained zero. The observer was corrected and checked
locally, but no second full power test was run with it. The observer is not part
of the SPK. Do not interpret this RC as a new formal safe-mode acceptance for 0022,
nor as a guarantee of reboot/recovery on arbitrary DSM installations.

## Pending public gate

Download this RC from GitHub, verify its checksum, perform delete-data uninstall
and manual reinstall through Package Center using README_RU.md or README.md.
Keep mains, UPS load and NAS running. No power test or NAS reboot is part of this gate.

It is a fresh package install on a preconfigured host: persistent DSM Firewall
deny and DSM UPS form values are host settings, not package data. Confirm them
explicitly; do not mistake inherited host settings for automatic provisioning.

After setup and at least 10 minutes observation, verify version/status, fresh
package data, exact USB identity/permissions, RAM process identities, both local
NUT endpoints and exact listeners/alias, native helper audit, DSM connection,
5-minute delay and persistent firewall deny. Confirm ordinary NAS workloads stayed
running. Green package badges alone are insufficient evidence for the whole gate.

Promotion to a final release requires completion of this gate and explicit approval.
The promoted SPK must retain this exact RC hash; any changed runtime requires its
own relevant checks, not a silent asset replacement.
