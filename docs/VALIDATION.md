# Validation status — 2.8.5-0025 RC1

Status: `RC_TESTED_UPGRADE`, 2026-10-20. Controlled **0022 → 0025** upgrade,
UPS/DSM connection and the package card passed on the tested host. The published
SPK is the same binary installed during that gate, with no publication rebuild.

Artifact: `nut-us3000_epyc7002-7.2_2.8.5-0025.spk`
SHA-256: `e89d90f2c2efb1742077887c4ab5f6aa1caa7827936d0c3a0623745d0ac8e436`

## Tested environment

Xpenology/Arc DSM 7.2.2-72806 **Update 8**, SA6400, epyc7002/x86-64;
UGREEN US3000 USB 2b89:ffff, serial DC600; NUT 2.8.5 / Arduino HID 0.22;
libusb 1.0.29. Other DSM versions, official Synology hardware and other UPS
devices are not covered by this acceptance.

## Current evidence

| Check | Result and scope |
| --- | --- |
| Advisory DSM policy | Actual shell gate tests passed for known/unknown/unreadable metadata and incompatible platform rejection in 0024. The shell is byte-identical in 0025, so those tests were not repeated. |
| Native package-card publisher | Five affected tests passed for captured VERSION without `unique`, bounded uname model detection, alternate/missing/ambiguous identity, unsafe metadata and independent state/settings text. |
| Source closure and documentation | Three targeted checks passed; package sources match `PACKAGE-SOURCE-0025.sha256`. |
| Offline build and artifact audit | Two builds, both SPK audits and normalized comparison passed. Inputs remained unchanged. Relative to 0024, only package version and the presentation helper binary changed. |
| Independent code review | The 0024 advisory change and 0025 model-source correction received ACCEPT with no findings. This is code evidence, not a live DSM 7.4.1 acceptance. |
| Controlled 0022 → 0025 upgrade | All package hooks and installation returned 0; package running. Protected rollback/configuration backup was verified first. |
| Read-only postflight | Both local endpoints reported online state, controller HEALTHY, RAM services active, DSM upsmon connected, helper permissions/audit passed. Package configuration, DSM UPS/firewall settings, NAS boot ID and unrelated container start times were unchanged. |
| Package Center card | Installed version 2.8.5-0025 and Running visible; connection, previously exercised environment, five-minute DSM setup and firewall badges green, with a fresh observation timestamp. |

The pre-install check caught 0024's assumption that installed DSM VERSION
contains `unique`. It does not on the tested NAS; 0024 was not installed.
0025 obtains the model from fixed `/bin/uname -a` and retains advisory handling.

## Inherited evidence and limits

The [0022 validation record](VALIDATION_0022.md) preserves the earlier keep-data
reinstall, public-guide clean install and inherited RAM lifecycle evidence.
Driver/server/controller/hooks and the operational RAM/USB/firewall logic were
not changed for 0025. Those successful gates were not repeated for this release.

No new full safe-mode or power-return test was run for 0025. The earlier 0021
observer did **not** produce a formal PASS, although automatic recovery was
observed; that limitation remains in the historical record. Successful UPS
communication is not proof of the complete shutdown/recovery sequence.

DSM 7.4.1 has only offline firmware/ABI investigation so far. Actual installation,
boot, USB ownership, cgroups and safe-mode recovery on it remain unverified.
See [DSM compatibility policy and evidence](COMPATIBILITY_7_4_1.md).

0025 RC1 is a prerelease. It has controlled-upgrade acceptance, not a new
ordinary-user clean-install acceptance from the public RC. Private logs,
credentials, host backups and infrastructure paths are not distributed.
