PKG_NAME = nut
PKG_VERS = 2.8.5
PKG_EXT = tar.gz
PKG_DIST_NAME = $(PKG_NAME)-$(PKG_VERS).$(PKG_EXT)
PKG_DIST_SITE = https://networkupstools.org/source/2.8
PKG_DIR = $(PKG_NAME)-$(PKG_VERS)

DEPENDS = cross/libusb

HOMEPAGE = https://networkupstools.org/
COMMENT = Network UPS Tools
LICENSE = GPL-2.0-or-later

GNU_CONFIGURE = 1
CONFIGURE_ARGS += --prefix=/var/packages/nut-us3000/target
CONFIGURE_ARGS += --sysconfdir=/var/packages/nut-us3000/etc
CONFIGURE_ARGS += --with-statepath=/var/packages/nut-us3000/var/run
CONFIGURE_ARGS += --with-altpidpath=/var/packages/nut-us3000/var/run
CONFIGURE_ARGS += --with-drvpath=/var/packages/nut-us3000/target/libexec/nut
CONFIGURE_ARGS += --with-user=nutus3000
CONFIGURE_ARGS += --with-group=nutus3000
CONFIGURE_ARGS += --with-drivers=usbhid-ups
CONFIGURE_ARGS += --with-usb=yes
CONFIGURE_ARGS += --without-openssl
CONFIGURE_ARGS += --without-snmp
CONFIGURE_ARGS += --without-neon
CONFIGURE_ARGS += --without-avahi
CONFIGURE_ARGS += --without-powerman
CONFIGURE_ARGS += --without-freeipmi
CONFIGURE_ARGS += --without-modbus
CONFIGURE_ARGS += --without-cgi

include ../../mk/spksrc.cross-cc.mk
