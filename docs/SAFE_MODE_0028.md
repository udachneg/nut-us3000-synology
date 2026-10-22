# 0028: полный safe-mode тест / full safe-mode test

**PASS — 23.10.2026**, один согласованный цикл на Xpenology/Arc SA6400,
DSM 7.4.1-90080 Update 1, systemd 219, UGREEN US3000.
Публикуется тот же проверенный SPK, без пересборки.

## Результат / Outcome

Входное питание ИБП отключено → полный safe mode → возврат питания →
автоматическая перезагрузка NAS → автоматический запуск NUT.
Ручных start/stop/restart пакета, reboot/reset NAS, переключений USB или
выходов ИБП не было. Это отчёт, а не команда повторять тест.

| Этап / Event | 23.10.2026, MSK (UTC+3) |
| --- | --- |
| Первый OB / first battery sample | 01:14:14.213 |
| Полный safe mode / complete safe mode | 01:17:09.393 — 175.180 s после OB |
| Первый OL / first mains sample | 01:17:53.522 — 219.309 s после OB |
| Новый boot доступен по SSH / new boot reachable | 01:21:34 |
| Автозапуск NUT / automatic systemd start | 01:21:40–01:21:56; Result=success, ExecMainStatus=0 |
| Таймер возвращён / timer restored | 01:24:52 — 300 s (5 min) |
| Исходное здоровье контейнеров восстановлено / baseline health restored | 01:27:12 readback |

Таймер DSM временно составлял одну минуту; полный переход занял ~2 минуты
55 секунд от первого OB. Лимит отсутствия питания пять минут соблюдён:
OL подтверждён через ~3 минуты 39 секунд. Это наблюдаемые значения, не
обещанное время следующего перехода.

## Доказательства / Evidence

Полный safe mode подтверждён двумя свежими последовательными наблюдениями:
цель и служба активны, Result=success, свежий timestamp; data volumes отсутствуют
на хосте и в проверенных mount namespaces, ошибок сканирования нет, очередь
пуста. Пакеты NUT и Container Manager остановлены, но исходная RAM-пара жива
и видит сначала OB, затем OL. Нулевой ExecMainStart не был критерием полноты.

После автоматического reboot системный hook завершился ret=0.
CORE занял ~1.49 s, готовность данных — 599 ms; bridge complete — 5.469 s
от начала его диагностической шкалы. Первый журнал сохранён до возврата
таймера; ручное восстановление не потребовалось.

Оба endpoint вернули OL, DSM подключилась автоматически, native audit=0,
controller=HEALTHY. Все три тома доступны на запись, нового resync нет.
Все 31 исходных контейнера запущены, baseline health восстановлен после
штатных проверок. Хэши настроек NUT, DSM UPS и брандмауэра совпали после
возврата таймера на пять минут.

Временные наблюдатель, unit и загруженные файлы отсутствуют; локальный приёмник
завершён, socket закрыт. Резервные копии и исходные свидетельства сохранены
приватно. Секреты и сырые NAS-журналы не публикуются.

## Ограничение / Limitation

**missing_mask=0**: ожидание неполных полей в этом live-запуске не понадобилось.
Эта ветвь проверена адресными локальными тестами. Один PASS не гарантирует
все будущие загрузки и не распространяется на другое оборудование/DSM.
Старые успешно пройденные тесты не повторялись.

English summary: one full cycle passed, including RAM survival, observed mains
return, automatic reboot and automatic NUT startup without manual recovery.
The temporary one-minute policy was restored to five minutes. Partial-data retry
was tested locally, not exercised by this live boot. Private raw logs are excluded.
