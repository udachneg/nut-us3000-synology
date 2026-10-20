# NUT US3000 2.8.5-0025 RC1

Предварительный релиз / Prerelease — 2026-10-20.

## Изменения / Changes

- Неизвестная DSM теперь вызывает предупреждение, а не запрет запуска
  только из-за номера версии, сборки или Update.
- В карточке пакета появился отдельный RU/EN блок совместимости. Он не подменяет
  состояние связи с ИБП, настройки DSM и брандмауэра.
- Исправлено определение модели NAS: в установленной DSM файл VERSION может
  не содержать `unique`; модель берётся из ограниченного вызова `/bin/uname -a`.
- Проверки архитектуры, прав и безопасности runtime сохранены. Драйвер USB,
  сервер NUT, контроллер, hooks и логика RAM/safe mode не менялись.

Unknown DSM versions are advisory, not a version-based startup ban. The package
card distinguishes environment evidence from live UPS health. The existing
binary-platform and runtime safety checks remain enforced.

## Установка / Installation

[Русская инструкция](https://github.com/udachneg/nut-us3000-synology/blob/v2.8.5-0025-rc1/README_RU.md)
· [English guide](https://github.com/udachneg/nut-us3000-synology/blob/v2.8.5-0025-rc1/README.md)

- SPK: `nut-us3000_epyc7002-7.2_2.8.5-0025.spk`.
- SHA-256: `e89d90f2c2efb1742077887c4ab5f6aa1caa7827936d0c3a0623745d0ac8e436`.
- If this exact 0025 SPK is already installed, no reinstall is needed.
- DSM UPS: Synology UPS Server, `10.255.255.1`, custom delay **5 minutes**.
- DSM Firewall: persistent **deny TCP 3493**, all sources/interfaces, above
  allow rules. Do not open this port to the network.
- Package Center minimum: DSM 7.2.2-72806, epyc7002/x86-64.
- Keep mains and load connected. Preserve configuration/backup before upgrading.

## Проверки и ограничения / Validation and limits

The published SPK is byte-identical to the locally built and installed 0025:
**no rebuild for publication**. Two offline builds and artifact audits,
targeted tests and independent code review passed.

Controlled 0022 → 0025 upgrade passed on Xpenology/Arc DSM 7.2.2-72806 Update 8,
SA6400/epyc7002 with UGREEN US3000 USB 2b89:ffff/DC600. UPS/DSM connection,
five-minute delay, firewall and the package card were verified. NAS boot and
unrelated containers were unchanged.

**DSM 7.4.1 is not yet runtime-validated.** Offline firmware/ABI investigation
and removing a version ban are not proof of live compatibility. The queue
reader still requires its implemented systemd 219 contract.
Clean-install, USB reconnect and full safe-mode/power tests were not repeated
for 0025. Prior evidence applies only to unchanged components and its documented
environment. This RC is not a new full safe-mode acceptance.

[Validation record](https://github.com/udachneg/nut-us3000-synology/blob/v2.8.5-0025-rc1/docs/VALIDATION.md)
· [DSM compatibility details](https://github.com/udachneg/nut-us3000-synology/blob/v2.8.5-0025-rc1/docs/COMPATIBILITY_7_4_1.md)

## Sources and checksums

The tag contains complete package sources, native helpers, RAM scripts/units,
generators and build scripts. `PACKAGE-SOURCE-0025.sha256` binds them to the
build inputs. NUT/libusb source archives, NUT signature/key, provenance and
normalized manifests accompany the SPK.
`SHA256SUMS-0025.txt` verifies the other ten release assets.

GPL-2.0-or-later; libusb LGPL-2.1-or-later. No Synology Toolkit/PAT, private
diagnostics, credentials, VM or build-cache image is redistributed.

Maintained by Hevtech.
