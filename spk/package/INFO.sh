#!/bin/sh

. /pkgscripts/include/pkg_util.sh

package="nut-us3000"
version="2.8.5-0025"
displayname="NUT US3000"
description="◆ STATUS: 🟡 not checked yet · Native NUT 2.8.5 for UGREEN US3000 ◆ DSM SETUP: Synology UPS Server · IP 10.255.255.1 · Delay 5 minutes ◆ FIREWALL: deny external TCP 3493 above allow rules ◆ IMPORTANT: Running means the controller is active, not proof of UPS protection ◆ HELP: NUT US3000 in the DSM main menu (RU/EN)"
description_rus="◆ СОСТОЯНИЕ: 🟡 ещё не проверено · Нативный NUT 2.8.5 для UGREEN US3000 ◆ НАСТРОЙКА DSM: Сервер ИБП Synology · IP 10.255.255.1 · Задержка 5 минут ◆ БРАНДМАУЭР: запретить внешний TCP 3493 выше разрешающих правил ◆ ВАЖНО: Выполняется — контроллер активен, не гарантия защиты ИБП ◆ СПРАВКА: NUT US3000 в главном меню DSM · RU/EN"
maintainer="Hevtech"
arch="epyc7002"
os_min_ver="7.2.2-72806"
thirdparty="yes"
offline_install="yes"
ctl_stop="yes"

pkg_dump_info
