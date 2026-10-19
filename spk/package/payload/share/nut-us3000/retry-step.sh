#!/bin/sh
set -u
[ $# -eq 0 ] || exit 64
[ -n "${SYNOPKG_PKGDEST:-}" ] && [ -n "${SYNOPKG_PKGVAR:-}" ] || exit 1
lib=$SYNOPKG_PKGDEST/share/nut-us3000/lib.sh
hostctl=$SYNOPKG_PKGDEST/libexec/nut/nut-us3000-hostctl
[ -f "$lib" ] && [ ! -L "$lib" ] || exit 1
[ -f "$hostctl" ] && [ ! -L "$hostctl" ] && [ -x "$hostctl" ] || exit 1
. "$lib" || exit 1
nutus3000_description_state=error
trap 'nutus3000_description_finish "$?" "$nutus3000_description_state"' EXIT
nutus3000_init || exit 1
result=$("$hostctl" ram-retry)
rc=$?
case "$rc:$result" in
    0:RAM_STATE=HEALTHY)
        nutus3000_publish_controller_state HEALTHY || exit 1
        nutus3000_description_state=healthy ;;
    0:RAM_STATE=DEGRADED)
        nutus3000_publish_controller_state DEGRADED_1 || exit 1
        nutus3000_description_state=degraded ;;
    75:RAM_STATE=UNAVAILABLE)
        nutus3000_publish_controller_state UNAVAILABLE || exit 1
        nutus3000_description_state=unavailable ;;
    0:RAM_STATE=DISABLED|0:RAM_STATE=PRESERVED)
        nutus3000_description_state=none ;;
    *) exit 1 ;;
esac
exit "$rc"
