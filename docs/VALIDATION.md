# Validation status — 2.8.5-0028

**FINAL — one full safe-mode/power-return cycle passed**, 2026-10-23.
Publication reuses the tested SPK without rebuilding or repeating tests.

Artifact: `nut-us3000_epyc7002-7.2_2.8.5-0028.spk`

SHA-256: `dca870d0b94bc1ebacfbb395788a00539af1e618e4c33cd2e32d2918b61d4452`

## Environment and existing evidence

Xpenology/Arc SA6400, epyc7002/x86-64, DSM 7.4.1-90080 Update 1,
Linux 5.10.55+, systemd 219; UGREEN US3000 USB 2b89:ffff;
NUT 2.8.5, Arduino HID 0.22, libusb 1.0.29.

| Check | Result reused for publication |
| --- | --- |
| Partial-data regression | Six targeted methods passed: missing fields on both endpoints, WAIT-to-complete, persistent partial data, fatal mixed cases, strict quiet HEALTH and closed stderr. Real C runtime; external operations/time replaced. |
| Diagnostics | Eight targeted methods passed; bounded diagnostics, missing_mask contains field bits, not values. |
| Independent review | Muse ACCEPT, no findings. Source/tests and sanitized local evidence, not live NAS certification. |
| Build and audit | One offline 0028 build and SPK audit passed; input snapshots match. Relative to 0027 only version and native helper hash differ in normalized manifests. |
| Controlled 0027 → 0028 upgrade | Install/hooks returned 0; both endpoints online, DSM connected, HEALTHY. Rollback retained; configuration/firewall/timer, NAS boot and unrelated containers unchanged. |
| Full safe-mode cycle | PASS: data volumes unmounted, RAM pair survived, battery then mains observed, automatic NAS reboot and NUT start rc0. No manual recovery. |
| Postflight | Both endpoints online, DSM connected, audit 0, HEALTHY; three volumes writable, all 31 baseline containers running with baseline health restored. Settings hashes matched after restoring five minutes. |
| Cleanup | Temporary observer/unit/upload removed, local receiver stopped. Backups and private evidence retained. |

[Sanitized test report](SAFE_MODE_0028.md) · [Change contract](STARTUP_PARTIAL_DATA_0028.md).

## Limits and history

One successful cycle is not a guarantee for all boots. This boot had
**missing_mask=0**: partial-data retry was tested locally, not exercised live.

Clean install, keep/delete-data uninstall, USB reconnect and other completed
tests were not repeated for 0028. [0022 evidence](VALIDATION_0022.md) retains its
original scope. The [0025 record](VALIDATION_0025.md) preserves its failed
update-time startup; the exact original cause was not captured. In 0027,
data_missing_field failed after CORE passed; the missing fields/raw response
were not captured. Do not assign that cause to every historical failure.

Other DSM builds, official Synology hardware and other UPS units are untested.
Unknown DSM remains advisory; the systemd 219 contract and independent safety
checks still apply. The unchanged embedded compatibility matrix can show yellow
on 7.4.1; documentation records new evidence without recoloring the binary.

Package sources are bound by release/PACKAGE-SOURCE-0028.sha256.
Raw private NAS logs, credentials, backups and infrastructure paths are excluded.
