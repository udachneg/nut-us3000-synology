#!/bin/sh
set -u

[ $# -eq 0 ] || exit 64
[ -n "${SYNOPKG_PKGDEST:-}" ] || exit 1
nutus3000_health_library=$SYNOPKG_PKGDEST/share/nut-us3000/lib.sh
[ -f "$nutus3000_health_library" ] && [ ! -L "$nutus3000_health_library" ] || exit 1
. "$nutus3000_health_library" || exit 1
nutus3000_health
exit $?
