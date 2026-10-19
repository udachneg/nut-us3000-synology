#!/bin/sh
# LOCAL CANDIDATE, source-only. Requires ram-lifecycle.sh callbacks and trusted
# loaded units, freshly staged RAM payload, acquired USB permissions and alias.
# No ensure/release here: the existing host integration owns those changes.
# Cold start only; not a retry controller or an installed privilege boundary.
nutram_start() (
    [ "$#" -eq 0 ] || exit 64
    PATH=/usr/bin:/bin; LC_ALL=C; export PATH LC_ALL
    [ "$(id -u)" = 0 ] || exit 1
    umask 077
    mkdir /run/nutram-start.lock || exit 1
    started=0
    finish() {
        rc=$?
        trap - 0 HUP INT TERM
        if [ "$rc" -ne 0 ] && [ "$started" = 1 ]; then
            # Even a timed-out start may have queued a job. Stop synchronously;
            # failure is not permission to release USB/alias or erase RAM files.
            nutram_runtime_stop && nutram_runtime_quiescent || rc=1
        fi
        rmdir /run/nutram-start.lock || rc=1
        exit "$rc"
    }
    trap finish 0
    trap 'exit 130' INT
    trap 'exit 143' HUP TERM
    nutram_runtime_quiescent || exit 1
    [ -f /run/nut-us3000-ram/manager/ram-ready.sh ] && \
        [ ! -L /run/nut-us3000-ram/manager/ram-ready.sh ] || exit 1
    /usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C \
        /usr/bin/timeout -s KILL 5 /var/packages/nut-us3000/target/libexec/nut/nut-us3000-hostctl audit \
        >/dev/null 2>&1 || exit 1
    started=1
    for unit in nut-us3000-ram-driver.service nut-us3000-ram-server.service; do
        /usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C SYSTEMD_COLORS=0 \
            /usr/bin/timeout -s KILL 15 /usr/bin/systemctl \
            --system --no-pager --no-ask-password start "$unit" || exit 1
    done
    /usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C \
        /bin/sh /run/nut-us3000-ram/manager/ram-ready.sh || exit 1
    printf '%s\n' RAM_READY
)
