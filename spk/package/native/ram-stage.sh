#!/bin/sh
# LOCAL CANDIDATE, NOT an installed root interface. Source has no effects.
# Caller must serialize the entire lifecycle, authenticate the installed payload,
# config and embedded control directory before entering, and load units separately. No NAS writes
# are part of the local test runner. Never replace an existing runtime here.
nutram_stage() (
    [ "$#" -eq 0 ] || exit 64
    PATH=/usr/bin:/bin; LC_ALL=C; export PATH LC_ALL
    umask 077
    [ "$(id -u)" = 0 ] || exit 1
    [ ! -L /run ] && [ "$(readlink -f /run)" = /run ] || exit 1
    [ "$(stat -f -c %T /run)" = tmpfs ] || exit 1
    dest=/run/nut-us3000-ram
    [ ! -e "$dest" ] && [ ! -L "$dest" ] || exit 1
    uid=$(id -u "nutus3000") && gid=$(id -g "nutus3000") || exit 1
    case $uid:$gid in *[!0-9:]*|0:*|*:0|:*|*:) exit 1 ;; esac
    src=/var/packages/nut-us3000/target
    cfg=/var/packages/nut-us3000/etc
    control=/run/nut-us3000-control
    stage=$(mktemp -d /run/nutram-stage.XXXXXX) || exit 1
    finish() {
        rc=$?
        trap - 0 HUP INT TERM
        # Only this invocation's newly allocated private staging tree.
        if [ -n "$stage" ]; then rm -rf -- "$stage" || rc=1; fi
        exit "$rc"
    }
    trap finish 0
    trap 'exit 130' INT
    trap 'exit 143' HUP TERM
    for dir in bin lib conf manager units state; do mkdir "$stage/$dir" || exit 1; done
    copy_file() {
        [ -f "$1" ] && [ ! -L "$1" ] && [ -r "$1" ] || return 1
        bytes=$(stat -c %s "$1") || return 1
        [ "$bytes" -le 4194304 ] || return 1
        cp -- "$1" "$2" || return 1
        chmod "$3" "$2"
    }
    copy_file "$src/sbin/upsd" "$stage/bin/nutus3000-srv" 750 || exit 1
    copy_file "$src/libexec/nut/usbhid-ups" "$stage/bin/nutus3000-hid" 750 || exit 1
    copy_file "$src/bin/upsc" "$stage/bin/upsc" 750 || exit 1
    for lib in libusb-1.0.so.0.5.0 libupsclient.so.7.1.0; do
        copy_file "$src/lib/$lib" "$stage/lib/$lib" 640 || exit 1
    done
    ln -s libusb-1.0.so.0.5.0 "$stage/lib/libusb-1.0.so.0" || exit 1
    ln -s libupsclient.so.7.1.0 "$stage/lib/libupsclient.so.7" || exit 1
    for file in ups.conf upsd.conf upsd.users; do
        copy_file "$cfg/$file" "$stage/conf/$file" 640 || exit 1
    done
    # Supported package configuration only. Reject custom state paths, another
    # UPS/driver or extra settings rather than silently dropping their semantics.
    normalized=$(sed 's/#.*//;s/[[:space:]]//g;/^$/d' "$stage/conf/ups.conf") || exit 1
    [ "$normalized" = '[ups]
driver=usbhid-ups
port=auto
vendorid=2b89
productid=ffff
serial=DC600
subdriver="ArduinoHID0.22"
usb_hid_rep_index=0
usb_hid_ep_in=1
usb_hid_ep_out=1
pollonly' ] || exit 1
    listeners=$(awk '
        {sub(/#.*/, "")}
        NF {if (NF!=3 || $1!="LISTEN") exit 1; print $1 " " $2 " " $3}
    ' "$stage/conf/upsd.conf") || exit 1
    listeners=$(printf '%s\n' "$listeners" | sort) || exit 1
    [ "$listeners" = 'LISTEN 10.255.255.1 3493
LISTEN 127.0.0.1 3493' ] || exit 1
    # NUT uses argv[0] both for driver= validation and its Unix socket basename.
    sed 's/\(driver[[:space:]]*=[[:space:]]*\)usbhid-ups/\1nutus3000-hid/' \
        "$stage/conf/ups.conf" > "$stage/conf/ups.conf.new" || exit 1
    mv "$stage/conf/ups.conf.new" "$stage/conf/ups.conf" || exit 1
    chmod 640 "$stage/conf/ups.conf" || exit 1
    # Privileged control code/units must come from bridge-authenticated embedded
    # bytes, never from a package-user-writable installation tree. No fallback.
    for file in hook-policy.sh queue-reader.sh queue-parser.sh ram-manager.sh \
                ram-lifecycle.sh ram-start.sh ram-ready.sh; do
        copy_file "$control/$file" "$stage/manager/$file" 640 || exit 1
    done
    for file in nutus3000_ram.slice nut-us3000-ram-driver.service nut-us3000-ram-server.service; do
        copy_file "$control/$file.in" "$stage/units/$file" 640 || exit 1
    done
    # Code and credentials remain root-owned and read-only to the package user.
    chown -R "0:$gid" "$stage" || exit 1
    chmod 750 "$stage" "$stage/bin" "$stage/lib" "$stage/conf" "$stage/manager" "$stage/units" "$stage/state" || exit 1
    chown "$uid:$gid" "$stage/state" || exit 1
    # Atomic publication; no replacement even if another bootstrap published.
    mv -T -n "$stage" "$dest" || exit 1
    [ ! -e "$stage" ] || exit 1
    stage=
)
