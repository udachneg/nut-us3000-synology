#!/bin/sh
# OFFLINE adapter only. No systemctl, lifecycle or privilege operations.
# Usage: sh queue-parser.sh PROFILE RC CAPTURE_STATE STDOUT_FILE STDERR_FILE
# Caller must supply immutable, fresh, bounded snapshots from the fixed command:
# LC_ALL=C SYSTEMD_COLORS=0 systemctl --system --no-pager --full list-jobs
# 'dsm219' and 'complete' are caller contracts, not authentication or live probes.
# Result rc0: NORMAL_STOP | SAFE_ENTRY_PENDING | TERMINAL_STOP. rc1: UNKNOWN.
# SAFE_ENTRY_PENDING is queue evidence only, NOT permission to preserve runtime.
set -u
LC_ALL=C
export LC_ALL

unknown() { printf '%s\n' UNKNOWN; exit 1; }
[ "$#" -eq 5 ] || unknown
[ "$1" = dsm219 ] && [ "$3" = complete ] || unknown
case "$2" in 0|1) ;; *) unknown ;; esac
for input in "$4" "$5"; do
    [ -f "$input" ] && [ ! -L "$input" ] && [ -r "$input" ] || unknown
done
[ ! -s "$5" ] || unknown
bytes=$(wc -c < "$4") || unknown
[ "$bytes" -gt 0 ] && [ "$bytes" -le 65536 ] || unknown
# Reject ANSI, NUL, CR and non-ASCII rather than let awk silently discard them.
plain_bytes=$(tr -cd '\11\12\40-\176' < "$4" | wc -c) || unknown
[ "$bytes" -eq "$plain_bytes" ] || unknown

result=$(awk '
    function invalid() { bad=1; exit }
    BEGIN { phase=0; count=0 }
    {
        if (phase == 3) invalid()
        if (phase == 0) {
            if ($0 == "No jobs running.") { phase=3; next }
            if (NF != 4 || $1 != "JOB" || $2 != "UNIT" ||
                $3 != "TYPE" || $4 != "STATE") invalid()
            phase=1; next
        }
        if (phase == 2) {
            if (NF != 3 || $1 !~ /^[1-9][0-9]*$/ || $1+0 != count ||
                $2 != "jobs" || $3 != "listed.") invalid()
            phase=3; next
        }
        if (NF == 0) {
            if (!count) invalid()
            phase=2; next
        }
        if (NF != 4 || $1 !~ /^[1-9][0-9]*$/ || $1+0 > 4294967295 ||
            $2 !~ /^[A-Za-z0-9_@:.\\-]+$/ || index($2, "...") ||
            $3 !~ /^(start|stop|reload|restart|try-restart|reload-or-start|verify-active|nop)$/ ||
            $4 !~ /^(waiting|running)$/) invalid()
        if (ids[$1]++ || units[$2]++) invalid()
        count++
        if ($2 ~ /^(reboot|poweroff|halt)\.target$/ ||
            $2 ~ /^systemd-(reboot|poweroff|halt)\.service$/) {
            if ($3 == "start" || $3 == "restart") terminal=1
            else ambiguous=1
        }
        if ($2 == "pkgctl-nut-us3000.service" && $3 == "stop" && $4 == "running") own=1
        if ($2 == "shutdown.target" && $3 == "start" && $4 == "waiting") shutdown=1
        if ($2 == "safe-shutdown.target" && $3 == "start" && $4 == "waiting") safe=1
    }
    END {
        if (bad || phase != 3 || ambiguous) { print "UNKNOWN"; exit 1 }
        if (terminal) print "TERMINAL_STOP"
        else if (own && shutdown && safe) print "SAFE_ENTRY_PENDING"
        else print "NORMAL_STOP"
    }
' < "$4" 2>/dev/null) || result=UNKNOWN
case "$result" in
    NORMAL_STOP|SAFE_ENTRY_PENDING|TERMINAL_STOP) printf '%s\n' "$result" ;;
    *) unknown ;;
esac
