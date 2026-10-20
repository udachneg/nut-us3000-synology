SPK_NAME = nut-us3000
SPK_VERS = 2.8.5
SPK_REV = 0023
SPK_ICON = src/icon-256.png

DEPENDS = cross/nut

MAINTAINER = Hevtech
MAINTAINER_URL = https://github.com/udachneg/nut-us3000-synology
DESCRIPTION = ◆ STATUS: 🟡 not checked yet · Native NUT 2.8.5 for UGREEN US3000 ◆ DSM SETUP: Synology UPS Server · IP 10.255.255.1 · Delay 5 minutes ◆ FIREWALL: deny external TCP 3493 above allow rules ◆ IMPORTANT: Running means the controller is active, not proof of UPS protection ◆ HELP: NUT US3000 in the DSM main menu (RU/EN)
DESCRIPTION_RUS = ◆ СОСТОЯНИЕ: 🟡 ещё не проверено · Нативный NUT 2.8.5 для UGREEN US3000 ◆ НАСТРОЙКА DSM: Сервер ИБП Synology · IP 10.255.255.1 · Задержка 5 минут ◆ БРАНДМАУЭР: запретить внешний TCP 3493 выше разрешающих правил ◆ ВАЖНО: Выполняется — контроллер активен, не гарантия защиты ИБП ◆ СПРАВКА: NUT US3000 в главном меню DSM · RU/EN
DISPLAY_NAME = NUT US3000
HOMEPAGE = https://github.com/udachneg/nut-us3000-synology
LICENSE = GPL-2.0-or-later AND LGPL-2.1-or-later
LICENSE_FILE = src/LICENSE

OS_MIN_VER = 7.2.2-72806
REQUIRED_MIN_DSM = 7.2
REQUIRED_MAX_DSM = 7.2
STARTABLE = yes
DSM_UI_CONFIG = src/payload/app/config
DSM_APP_NAME = com.synocommunity.packages.nut-us3000
DISABLE_GITHUB_MAINTAINER = 1

SSS_SCRIPT = src/start-stop-status
CONF_DIR = src/conf
WIZARDS_DIR = src/wizard
POST_SERVICE_TARGET = nut_us3000_service_finalize
POST_STRIP_TARGET = nut_us3000_extra_install

PLIST_TRANSFORM = grep -E '^(bin:(bin/upsc|sbin/upsd|sbin/upsdrvctl|libexec/nut/usbhid-ups)|lib:lib/(libupsclient[.]so[.]7[.]1[.]0|libusb-1[.]0[.]so[.]0[.]5[.]0)|lnk:lib/(libupsclient[.]so[.]7|libusb-1[.]0[.]so[.]0))$$'

include ../../mk/spksrc.common.mk
include ../../mk/spksrc.spk.mk

.PHONY: nut_us3000_service_finalize nut_us3000_extra_install

nut_us3000_service_finalize:
	install -m 755 -d $(DSM_SCRIPTS_DIR)
	for hook in preinst postinst preuninst postuninst preupgrade postupgrade; do \
		install -m 755 src/hooks/$${hook} $(DSM_SCRIPTS_DIR)/$${hook}; \
	done

nut_us3000_extra_install:
	$(TC_PATH)$(TC_PREFIX)gcc -D_GNU_SOURCE -std=c11 -Wall -Wextra -Werror -Os src/native/ram-hostctl.c src/native/ram-bridge.c src/native/ram-exec.c src/native/ram-runtime.c src/native/ram-platform.c src/native/ram-files.c -o $(STAGING_DIR)/libexec/nut/nut-us3000-hostctl
	$(TC_PATH)$(TC_PREFIX)gcc -std=c11 -Wall -Wextra -Werror -Os -D_POSIX_C_SOURCE=200809L src/native/nut-us3000-controller.c -o $(STAGING_DIR)/libexec/nut/nut-us3000-controller
	chmod 750 $(STAGING_DIR)/libexec/nut/nut-us3000-hostctl
	chmod 750 $(STAGING_DIR)/libexec/nut/nut-us3000-controller
	for elf in bin/upsc sbin/upsd sbin/upsdrvctl libexec/nut/usbhid-ups lib/libupsclient.so.7.1.0 lib/libusb-1.0.so.0.5.0; do \
		patchelf --set-rpath /var/packages/nut-us3000/target/lib $(STAGING_DIR)/$${elf}; \
	done
	chmod 644 $(STAGING_DIR)/lib/libupsclient.so.7.1.0 $(STAGING_DIR)/lib/libusb-1.0.so.0.5.0
	install -m 755 -d $(STAGING_DIR)/share/nut-us3000/templates \
		$(STAGING_DIR)/app/help/enu $(STAGING_DIR)/app/help/rus \
		$(STAGING_DIR)/app/texts/enu $(STAGING_DIR)/app/texts/rus
	install -m 755 src/payload/share/nut-us3000/lib.sh $(STAGING_DIR)/share/nut-us3000/lib.sh
	install -m 755 src/payload/share/nut-us3000/healthcheck.sh $(STAGING_DIR)/share/nut-us3000/healthcheck.sh
	install -m 755 src/payload/share/nut-us3000/retry-step.sh $(STAGING_DIR)/share/nut-us3000/retry-step.sh
	install -m 644 src/templates/ups.conf $(STAGING_DIR)/share/nut-us3000/templates/ups.conf
	install -m 644 src/templates/upsd.conf $(STAGING_DIR)/share/nut-us3000/templates/upsd.conf
	install -m 644 src/payload/app/helptoc.conf $(STAGING_DIR)/app/helptoc.conf
	install -m 644 src/payload/app/index.html $(STAGING_DIR)/app/index.html
	install -m 644 src/payload/app/help/enu/nut-us3000.html $(STAGING_DIR)/app/help/enu/nut-us3000.html
	install -m 644 src/payload/app/help/rus/nut-us3000.html $(STAGING_DIR)/app/help/rus/nut-us3000.html
	install -m 644 src/payload/app/texts/enu/strings $(STAGING_DIR)/app/texts/enu/strings
	install -m 644 src/payload/app/texts/rus/strings $(STAGING_DIR)/app/texts/rus/strings
