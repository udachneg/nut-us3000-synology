# NUT US3000 2.8.5-0022

Финальный релиз / Final release — 2026-10-20. Maintained by Hevtech.

The SPK is byte-identical to the tested RC1: **no rebuild**, no package-source or
runtime changes. If RC1 0022 is already installed, no reinstall is needed.

## Установка / Installation

Читайте [русскую инструкцию](https://github.com/udachneg/nut-us3000-synology/blob/v2.8.5-0022/README_RU.md)
или [English guide](https://github.com/udachneg/nut-us3000-synology/blob/v2.8.5-0022/README.md).

- Download `nut-us3000_epyc7002-7.2_2.8.5-0022.spk` and its `.sha256` file.
- SHA-256: `cd3fbec1def596f4048a0280e6734e4d37d66c10c77e84a3763af3988c2ca72f`.
- Keep mains and load connected. Install manually through DSM Package Center.
- DSM UPS: Synology UPS Server, `10.255.255.1`, custom delay **5 minutes**.
- DSM Firewall: persistent **deny TCP 3493**, all sources/interfaces, above allow
  rules. Do not open this port to the network. These host settings remain manual.
- Arc Apps & Permissions is not required for the tested normal installation path.
- The SPK is unsigned by Synology. Read warnings and licenses before accepting.

## Проверки и ограничения / Validation and limits

Upgrade, keep-data reinstall and public-guide delete-data clean installation
passed on Xpenology/Arc DSM 7.2.2-72806 / SA6400 / epyc7002 with UGREEN US3000
USB 2b89:ffff / DC600. The clean-install postflight passed **614 seconds** after
DSM setup; fresh package configuration, RAM services, both local endpoints,
DSM connection, 5-minute delay and firewall were verified. No NAS reboot, power
interruption or unrelated container restart occurred during this gate.

Other DSM builds, official Synology hardware and other UPS devices remain
unverified. The 0021 full safe-mode test observed automatic recovery, but the
old observer did not produce a formal PASS. This final release does not claim
a repeat power test or a new formal safe-mode acceptance. See the full
[validation record and limits](https://github.com/udachneg/nut-us3000-synology/blob/v2.8.5-0022/docs/VALIDATION.md).

## Sources and verification

The tagged source contains native helpers, RAM scripts/units, generators and
build scripts. `PACKAGE-SOURCE-0022.sha256` binds the distributed package sources
to the original build inputs. Upstream NUT/libusb sources, NUT signature/key,
provenance, normalized manifest and checksums accompany the SPK. All 11 release
assets are unchanged from RC1; the final tag adds documentation of acceptance.
`SHA256SUMS-0022.txt` verifies the other ten assets in one directory.

GPL-2.0-or-later; libusb LGPL-2.1-or-later. No Synology Toolkit, private diagnostics,
NAS credentials, virtual machines or build-cache images are redistributed.
