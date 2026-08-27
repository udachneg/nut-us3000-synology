#!/bin/sh
set -u

[ $# -eq 0 ] || exit 64
[ -n "${SYNOPKG_PKGDEST:-}" ] || exit 1
[ -n "${SYNOPKG_PKGVAR:-}" ] || exit 1

nutus3000_retry_library=$SYNOPKG_PKGDEST/share/nut-us3000/lib.sh
nutus3000_retry_hostctl=$SYNOPKG_PKGDEST/libexec/nut/nut-us3000-hostctl
[ -f "$nutus3000_retry_library" ] && [ ! -L "$nutus3000_retry_library" ] || exit 1
[ -f "$nutus3000_retry_hostctl" ] && [ ! -L "$nutus3000_retry_hostctl" ] \
    && [ -x "$nutus3000_retry_hostctl" ] || exit 1
. "$nutus3000_retry_library" || exit 1

nutus3000_init || exit 1
nutus3000_retry_previous=$(nutus3000_read_controller_state 2>/dev/null)
nutus3000_retry_state_rc=$?
if [ "$nutus3000_retry_state_rc" -eq 75 ]; then
    nutus3000_retry_previous=
elif [ "$nutus3000_retry_state_rc" -ne 0 ]; then
    exit 1
fi

"$nutus3000_retry_hostctl" ensure || exit 1
"$nutus3000_retry_hostctl" audit || exit 1

nutus3000_core_state
nutus3000_retry_core_rc=$?
if [ "$nutus3000_retry_core_rc" -eq 0 ]; then
    if nutus3000_health; then
        nutus3000_publish_controller_state HEALTHY || exit 1
        exit 0
    fi
    if [ "$nutus3000_retry_previous" != DEGRADED_1 ]; then
        nutus3000_publish_controller_state DEGRADED_1 || exit 1
        exit 0
    fi

    nutus3000_stop || exit 1
    "$nutus3000_retry_hostctl" release || exit 1
    "$nutus3000_retry_hostctl" ensure || exit 1
    "$nutus3000_retry_hostctl" audit || exit 1
elif [ "$nutus3000_retry_core_rc" -ne 75 ]; then
    exit 1
fi

nutus3000_attempt_start
nutus3000_retry_start_rc=$?
if [ "$nutus3000_retry_start_rc" -eq 0 ]; then
    nutus3000_publish_controller_state HEALTHY || exit 1
    exit 0
fi
if [ "$nutus3000_retry_start_rc" -eq 75 ]; then
    nutus3000_publish_controller_state UNAVAILABLE || exit 1
    exit 75
fi
exit 1
