# NUT US3000 2.8.5-0028

Финальный релиз / Final release — 2026-10-23.

## Изменения / Changes

Сохранена ограниченная диагностика запуска из 0026 и окно готовности CORE
20 секунд из 0027 (не фиксированная задержка). В 0028 корректно оформленные
неполные данные ИБП повторно проверяются только при старте в существующем
20-секундном окне готовности данных. Неполнота не считается успехом;
неверная идентичность и другие фатальные ошибки не маскируются.
missing_mask фиксирует отсутствующие поля без записи значений.
Обычный HEALTH остаётся строгим; новых служб и зависимостей нет.

Retains bounded diagnostics and a 20-second CORE convergence window.
Startup-only retry handles well-formed incomplete UPS data; present identity
fields are validated before retry. Fatal errors and strict HEALTH remain.

## Проверено / Verified

Controlled 0027 → 0028 upgrade and one full safe-mode → power return →
automatic reboot → automatic NUT start passed on Xpenology/Arc SA6400,
DSM 7.4.1-90080 Update 1, UGREEN US3000. No manual recovery.
Settings and five-minute timer restored; volumes and baseline containers recovered.
Targeted tests and independent Muse review passed before publication.

[Отчёт / Test report](https://github.com/udachneg/nut-us3000-synology/blob/v2.8.5-0028/docs/SAFE_MODE_0028.md)
· [Validation scope](https://github.com/udachneg/nut-us3000-synology/blob/v2.8.5-0028/docs/VALIDATION.md)

One successful cycle is not a guarantee for every boot. Live missing_mask=0;
partial-data retry is covered by local tests, not this live observation.
Clean install/uninstall and USB tests were not repeated. Other hardware/DSM
remain untested. The embedded compatibility badge can remain yellow on 7.4.1
despite newer documented evidence.

## Установка / Installation

[Русская инструкция](https://github.com/udachneg/nut-us3000-synology/blob/v2.8.5-0028/README_RU.md)
· [English guide](https://github.com/udachneg/nut-us3000-synology/blob/v2.8.5-0028/README.md)

- SPK: `nut-us3000_epyc7002-7.2_2.8.5-0028.spk`
- SHA-256: `dca870d0b94bc1ebacfbb395788a00539af1e618e4c33cd2e32d2918b61d4452`
- **Тот же проверенный SPK, без пересборки. Если установлен — переустановка не нужна.**
- DSM UPS: Synology UPS Server, `10.255.255.1`, custom delay **5 minutes**.
- DSM Firewall: persistent **deny TCP 3493**, all sources/interfaces, above allow
  rules. Do not open this port to the network.
- Minimum DSM 7.2.2-72806, epyc7002/x86-64. Keep mains/load connected during install.

## Sources and integrity

The tag contains package sources, native helpers, generators, scripts and tests.
PACKAGE-SOURCE-0028.sha256 binds package sources to build inputs.
Assets include exact NUT/libusb archives, NUT signature/key, provenance and
normalized manifest. SHA256SUMS-0028.txt covers all other release assets.
No Synology Toolkit/PAT, private logs, secrets or backups are redistributed.
No rebuild, repeated runtime tests or NAS changes for publication.

GPL-2.0-or-later; libusb LGPL-2.1-or-later. Maintained by Hevtech.
