#!/bin/sh
# LOCAL PROTOTYPE ONLY, not installed or called by the SPK.
# No arguments: fresh fixed-command observation, never cached/caller snapshots.
# Requires GNU timeout and bash (DSM has both); /run must be writable by manager.
# stdout/rc: parser's three intents/0, otherwise UNKNOWN/1. No lifecycle actions.
set -u
PATH=/usr/bin:/bin
LC_ALL=C
export PATH LC_ALL
umask 077
snapshot=
worker=
unknown() { printf '%s\n' UNKNOWN; exit 1; }
cleanup() {
    if [ -n "$worker" ]; then
        # GNU timeout owns its process group. Kill children too, not just shell.
        /bin/kill -KILL -- "-$worker" 2>/dev/null || :
        /bin/kill -KILL "$worker" 2>/dev/null || :
        wait "$worker" 2>/dev/null || :
        worker=
    fi
    if [ -n "$snapshot" ]; then
        rm -f -- "$snapshot/version.out" "$snapshot/version.err" \
            "$snapshot/queue.out" "$snapshot/queue.err" "$snapshot/result" || return 1
        rmdir -- "$snapshot" || return 1
        snapshot=
    fi
}
trap 'cleanup >/dev/null 2>&1' 0
trap 'unknown' HUP INT TERM
[ "$#" -eq 0 ] || unknown
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) || unknown
parser="$here/queue-parser.sh"
[ -f "$parser" ] && [ ! -L "$parser" ] && [ -r "$parser" ] || unknown
snapshot=$(/usr/bin/mktemp -d /run/nutram-queue.XXXXXX) || unknown

# One deadline for version + queue + parse, no retries. Setup/cleanup are outside
# it; scheduling or an uninterruptible kernel wait cannot be a realtime guarantee.
# Clear remote-systemctl/DBus/pager/locale/POSIXLY_CORRECT overrides before bash.
/usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C SYSTEMD_COLORS=0 \
    /usr/bin/timeout -s KILL 3 /bin/bash -s -- "$snapshot" "$parser" \
    >/dev/null 2>/dev/null <<'WORKER' &
set -u
umask 077
ulimit -c 0 || exit 1
# Bash uses 1024-byte blocks with POSIXLY_CORRECT unset: 32 KiB per file.
# Covers both queue streams, version streams and parser result. No unbounded pipe.
ulimit -f 32 || exit 1
cd -- "$1" || exit 1
/usr/bin/systemctl --version >version.out 2>version.err || exit 1
[ ! -s version.err ] || exit 1
[ "$(wc -c < version.out)" -lt 32768 ] || exit 1
IFS= read -r version <version.out || exit 1
[ "$version" = 'systemd 219' ] || exit 1
/usr/bin/systemctl --system --no-pager --full list-jobs >queue.out 2>queue.err
queue_rc=$?
# A writer that catches SIGXFSZ may return rc1: reject the cap, not just its rc.
[ "$(wc -c < queue.out)" -lt 32768 ] || exit 1
[ "$(wc -c < queue.err)" -lt 32768 ] || exit 1
/bin/sh "$2" dsm219 "$queue_rc" complete "$1/queue.out" "$1/queue.err" >result
WORKER
worker=$!
if wait "$worker"; then
    worker=
else
    # Timeout or abnormal completion must never consume a partial/stale result.
    unknown
fi
intent=$(cat -- "$snapshot/result") || unknown
case "$intent" in NORMAL_STOP|SAFE_ENTRY_PENDING|TERMINAL_STOP) ;; *) unknown ;; esac
cleanup || unknown
printf '%s\n' "$intent"
