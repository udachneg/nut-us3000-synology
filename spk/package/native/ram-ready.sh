#!/bin/sh
# Local candidate. Read-only protocol gate, no authentication secret in output.
# Success means fresh NUT data for the expected USB identity at BOTH endpoints;
# it does not attest native PID/cgroup ownership or DSM safe-mode survival.
PATH=/usr/bin:/bin; LC_ALL=C; export PATH LC_ALL
case $#:$* in
    0:) exec /usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C \
        /usr/bin/timeout -k 1 -s TERM 20 /bin/sh /run/nut-us3000-ram/manager/ram-ready.sh --poll ;;
    1:once|1:--poll) ;;
    *) exit 64 ;;
esac
umask 077
tmp=$(mktemp -d /run/nutram-ready.XXXXXX) || exit 1
cleanup() { rc=$?; trap - 0 HUP INT TERM; rm -rf -- "$tmp" || rc=1; exit "$rc"; }
trap cleanup 0
trap 'exit 130' INT
trap 'exit 143' HUP TERM
query() {
    # Bash units are KiB on this target; each regular output file <=32KiB.
    /bin/bash -c 'ulimit -f 32 || exit 1; exec "$@"' limit \
        /usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C \
        LD_LIBRARY_PATH=/run/nut-us3000-ram/lib \
        /usr/bin/timeout -s KILL 3 /run/nut-us3000-ram/bin/upsc "ups@$1:3493" \
        > "$tmp/out" 2> "$tmp/err" || return 1
    [ "$(wc -c < "$tmp/out")" -lt 32768 ] && [ "$(wc -c < "$tmp/err")" -lt 32768 ] || return 1
    awk -F': ' '
        $1 ~ /^(driver.name|device.mfr|device.model|ups.vendorid|ups.productid|ups.status)$/ {
            if (NF!=2 || seen[$1]++) bad=1
            v[$1]=$2; n++
        }
        END {
            if (bad || n!=6 || v["driver.name"]!="nutus3000-hid" ||
                v["device.mfr"]!="UGREEN" || v["device.model"]!="US3000" ||
                v["ups.vendorid"]!="2b89" || v["ups.productid"]!="ffff") exit 1
            count=split(v["ups.status"], tokens, /[[:space:]]+/)
            for (i=1; i<=count; i++) {
                if (tokens[i]=="NOCOMM" || tokens[i]=="STALE") exit 1
                if (tokens[i]=="OL" || tokens[i]=="OB") power=1
            }
            exit !power
        }
    ' "$tmp/out"
}
while :; do
    if query 127.0.0.1 && query 10.255.255.1; then exit 0; fi
    [ "$1" = --poll ] || exit 1
    sleep 1 || exit 1
done
