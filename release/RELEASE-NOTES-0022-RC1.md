# NUT US3000 2.8.5-0022 RC1

Pre-release for Xpenology/Arc DSM 7.2.2-72806 / SA6400 / epyc7002
and UGREEN US3000 2b89:ffff / DC600. Maintained by Hevtech.

## Установка / Installation

Читайте [русскую инструкцию](https://github.com/udachneg/nut-us3000-synology/blob/v2.8.5-0022-rc1/README_RU.md)
или [English guide](https://github.com/udachneg/nut-us3000-synology/blob/v2.8.5-0022-rc1/README.md).

- Download `nut-us3000_epyc7002-7.2_2.8.5-0022.spk` and its `.sha256` file.
- SHA-256: `cd3fbec1def596f4048a0280e6734e4d37d66c10c77e84a3763af3988c2ca72f`.
- Keep mains and load connected. Install manually through DSM Package Center.
- DSM UPS: Synology UPS Server, `10.255.255.1`, custom delay **5 minutes**.
- DSM Firewall: persistent **deny TCP 3493**, all sources/interfaces, above allow
  rules. Do not open this port to the network. These host settings remain manual.
- The SPK is unsigned by Synology. Review warnings and licenses before accepting.

## Changes and status

RAM-backed NUT server/USB driver, exact USB recovery, setup/status badges and RU/EN
help. Since 0021 only the selected delay, diagnostics, text and package version
changed. Existing DSM delay is not automatically rewritten.

0022 upgrade and keep-data reinstall passed. **Fresh package install after delete-data
uninstall on a preconfigured DSM host is pending.** Not a final stable release.
The 0021 safe-mode test observed automatic recovery, but its old observer did not
give formal PASS; see [validation](https://github.com/udachneg/nut-us3000-synology/blob/v2.8.5-0022-rc1/docs/VALIDATION.md).
No repeat power test is implied by this publication.

## Sources and verification

Tagged repository source contains native helpers, RAM scripts/units, generator
and build scripts. `PACKAGE-SOURCE-0022.sha256` binds all distributed `spk/` sources
to the original build input (excluding a non-source Python cache). Upstream NUT/libusb sources, NUT signature/key,
provenance, normalized manifest and checksums accompany the SPK.
`SHA256SUMS-0022.txt` checks all release assets (except itself) from one directory.

GPL-2.0-or-later; libusb LGPL-2.1-or-later. No Synology Toolkit, private diagnostics,
NAS credentials, virtual machines or build-cache images are redistributed.
