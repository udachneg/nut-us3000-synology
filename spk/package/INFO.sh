#!/bin/sh

. /pkgscripts/include/pkg_util.sh

package="nut-us3000"
version="2.8.5-0016"
displayname="NUT US3000"
description="Native USB driver and host-local NUT 2.8.5 endpoint for UGREEN US3000."
description_rus="Нативный USB-драйвер и локальный NUT 2.8.5 для UGREEN US3000."
maintainer="Hevtech"
arch="epyc7002"
os_min_ver="7.2.2-72806"
thirdparty="yes"
offline_install="yes"
ctl_stop="yes"

pkg_dump_info
