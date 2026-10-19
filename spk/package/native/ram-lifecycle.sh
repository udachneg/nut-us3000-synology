#!/bin/sh
# LOCAL CANDIDATE ONLY. Fixed stop callbacks for hook-policy/ram-manager.
# Trusted root bootstrap required; source has no effects. No caller command/PID
# paths, no killall, no systemctl stop of the package unit from its own hook.
# Installing/loading the units, RAM payload/start/recovery and root IPC remain
# separate work. No environment variable is an authorization boundary here.

nutram_controller_stop() (
    [ "$#" -eq 0 ] || return 64
    cd / || return 1
    # Existing controller identity files belong to nutus3000, not root.
    /usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C \
        /usr/bin/timeout -s KILL 40 /bin/su -s /bin/sh nutus3000 -c '
            SYNOPKG_PKGDEST=/var/packages/nut-us3000/target
            SYNOPKG_PKGVAR=/var/packages/nut-us3000/var
            export SYNOPKG_PKGDEST SYNOPKG_PKGVAR
            lib=$SYNOPKG_PKGDEST/share/nut-us3000/lib.sh
            [ -f "$lib" ] && [ ! -L "$lib" ] && [ -r "$lib" ] || exit 1
            . "$lib" || exit 1
            nutus3000_controller_stop
        '
)

nutram_runtime_stop() {
    [ "$#" -eq 0 ] || return 64
    # Server first, then USB driver. Wait for each job; do not use --no-block.
    # Unit TimeoutStopSec=10 is below the 15s client deadline. A client timeout
    # does not cancel the job; failure blocks host release, not a claim of stop.
    for nutram_unit in nut-us3000-ram-server.service nut-us3000-ram-driver.service; do
        /usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C SYSTEMD_COLORS=0 \
            /usr/bin/timeout -s KILL 15 /usr/bin/systemctl \
            --system --no-pager --no-ask-password stop "$nutram_unit" || return 1
    done
}

nutram_unit_is_dead() {
    [ "$#" -eq 1 ] || return 64
    case "$1" in nut-us3000-ram-server.service|nut-us3000-ram-driver.service) ;; *) return 64 ;; esac
    nutram_properties=$(/usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C SYSTEMD_COLORS=0 \
        /usr/bin/timeout -s KILL 3 /usr/bin/systemctl \
        --system --no-pager --no-ask-password show -p Id -p LoadState \
        -p ActiveState -p SubState -p MainPID -p ControlPID -p ControlGroup "$1") || return 1
    # rc1 exception belongs to list-jobs only; never apply it to show/stop.
    printf '%s\n' "$nutram_properties" | LC_ALL=C awk -F= -v unit="$1" '
        NF != 2 {bad=1; next}
        $1 !~ /^(Id|LoadState|ActiveState|SubState|MainPID|ControlPID|ControlGroup)$/ {bad=1; next}
        {if (seen[$1]++) bad=1; value[$1]=$2; n++}
        END {exit (bad || n!=7 || value["Id"]!=unit || value["LoadState"]!="loaded" ||
            value["ActiveState"]!="inactive" || value["SubState"]!="dead" ||
            value["MainPID"]!="0" || value["ControlPID"]!="0" ||
            (value["ControlGroup"]!="" && value["ControlGroup"]!="/nutus3000_ram.slice/" unit))}
    '
}

nutram_cgroup_is_clear() {
    # Internal read-only helper, not an external path API. DSM219 cgroup v1.
    LC_ALL=C awk -F: '
        $2=="name=systemd" {
            seen++
            if ($3 ~ /^\/nutus3000_ram\.slice\/nut-us3000-ram-(server|driver)\.service(\/|$)/) busy=1
        }
        END {exit (seen!=1 || busy)}
    ' "$1"
}

nutram_runtime_quiescent() {
    [ "$#" -eq 0 ] || return 64
    nutram_unit_is_dead nut-us3000-ram-server.service || return 1
    nutram_unit_is_dead nut-us3000-ram-driver.service || return 1
    nutram_kernel_quiescent
}

nutram_kernel_quiescent() {
    [ "$#" -eq 0 ] || return 64
    # Shared kernel-only half. Native runtime validates unit state itself, then
    # invokes this fixed function from the authenticated embedded control copy.
    # It is not sufficient by itself to authorize host release.
    # Unit state alone is not proof. Detect descendants and escaped/renamed RAM
    # executables too; no dependence on a stale PID file or exact cgroup mount.
    nutram_cgroup_is_clear /proc/self/cgroup || return 1
    for nutram_pid_dir in /proc/[0-9]*; do
        [ -d "$nutram_pid_dir" ] || continue
        if ! nutram_cgroup_is_clear "$nutram_pid_dir/cgroup" 2>/dev/null; then
            [ ! -d "$nutram_pid_dir" ] && continue
            return 1
        fi
        if nutram_exe=$(/usr/bin/readlink "$nutram_pid_dir/exe" 2>/dev/null); then
            case "$nutram_exe" in
                /run/nut-us3000-ram/bin/nutus3000-srv|/run/nut-us3000-ram/bin/nutus3000-hid|\
                '/run/nut-us3000-ram/bin/nutus3000-srv (deleted)'|\
                '/run/nut-us3000-ram/bin/nutus3000-hid (deleted)') return 1 ;;
            esac
        else
            [ ! -d "$nutram_pid_dir" ] && continue
            nutram_comm=$(cat "$nutram_pid_dir/comm" 2>/dev/null) || return 1
            case "$nutram_comm" in nutus3000-srv|nutus3000-hid) return 1 ;; esac
        fi
    done
    # Closed listeners, including IPv6; TIME_WAIT after close is not a listener.
    for nutram_tcp in /proc/net/tcp /proc/net/tcp6; do
        LC_ALL=C awk '
            NR==1 {if ($2!="local_address" || $4!="st") bad=1; next}
            NF<4 {bad=1; next}
            $2 ~ /:0DA5$/ && $4=="0A" {busy=1}
            END {exit (!NR || bad || busy)}
        ' "$nutram_tcp" || return 1
    done
    # Check kernel socket table, not just stale filesystem socket entries.
    LC_ALL=C awk '
        NR==1 {if ($1!="Num" || $8!="Path") bad=1; next}
        NF<7 {bad=1; next}
        index($8,"/run/nut-us3000-ram/state/")==1 {busy=1}
        END {exit (!NR || bad || busy)}
    ' /proc/net/unix
}

nutram_host_release() {
    [ "$#" -eq 0 ] || return 64
    # Internal callback: policy must have completed quiescence first. Reuse the
    # existing compiled helper; no new firewall/USB restore implementation.
    /usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C \
        /var/packages/nut-us3000/target/libexec/nut/nut-us3000-hostctl release
}

# Read-only inventory for the native CORE phase, always under its bounded
# executor. No PID or command is accepted from the caller. A successful scan
# returns two PIDs, not permission to signal them: systemd owns lifecycle.
nutram_proc_stamp() {
    LC_ALL=C awk -v pid="${1##*/}" '
        NR!=1 {bad=1}
        {
            if ($0 !~ ("^" pid " \\(.*\\) ")) {bad=1; next}
            sub(/^[0-9]+ \(.*\) /, "")
            if (NF<20 || $1 !~ /^(R|S|D|I)$/ || $20 !~ /^[1-9][0-9]*$/) bad=1
            stamp=$20
        }
        END {if (NR!=1 || bad) exit 1; print stamp}
    ' "$1/stat"
}

nutram_proc_group() {
    LC_ALL=C awk -F: '
        $2=="name=systemd" {n++; if (NF!=3 || $3 !~ /^\//) bad=1; g=$3}
        END {if (n!=1 || bad) exit 1; print g}
    ' "$1/cgroup"
}

nutram_core_inventory() (
    [ "$#" -eq 0 ] || return 64
    nutram_uid=$(/usr/bin/id -u nutus3000) || return 1
    nutram_gid=$(/usr/bin/id -g nutus3000) || return 1
    case "$nutram_uid:$nutram_gid" in *[!0-9:]*|:*|*:|0:*|*:0) return 1 ;; esac
    nutram_cgroup_is_clear /proc/self/cgroup || return 1
    nutram_server=0 nutram_driver=0 nutram_server_stamp= nutram_driver_stamp=
    for nutram_dir in /proc/[0-9]*; do
        [ -d "$nutram_dir" ] || continue
        nutram_group=$(nutram_proc_group "$nutram_dir" 2>/dev/null) || {
            [ ! -d "$nutram_dir" ] && continue
            return 1
        }
        nutram_exe=$(/usr/bin/readlink "$nutram_dir/exe" 2>/dev/null) || nutram_exe=
        nutram_comm=$(cat "$nutram_dir/comm" 2>/dev/null) || {
            [ ! -d "$nutram_dir" ] && continue
            return 1
        }
        case "$nutram_group:$nutram_exe:$nutram_comm" in
            /nutus3000_ram.slice/nut-us3000-ram-server.service:*|\
            /nutus3000_ram.slice/nut-us3000-ram-server.service/*|\
            /nutus3000_ram.slice/nut-us3000-ram-driver.service:*|\
            /nutus3000_ram.slice/nut-us3000-ram-driver.service/*|\
            *:/run/nut-us3000-ram/bin/nutus3000-srv:*|\
            *:/run/nut-us3000-ram/bin/nutus3000-hid:*|\
            *:'/run/nut-us3000-ram/bin/nutus3000-srv (deleted)':*|\
            *:'/run/nut-us3000-ram/bin/nutus3000-hid (deleted)':*|\
            *:nutus3000-srv|*:nutus3000-hid) ;;
            *) continue ;;
        esac
        nutram_stamp=$(nutram_proc_stamp "$nutram_dir") || return 1
        # The first reads select candidates; revalidate their identity inside
        # the starttime bracket, not against a stale pre-bracket observation.
        [ "$(nutram_proc_group "$nutram_dir")" = "$nutram_group" ] || return 1
        [ "$(/usr/bin/readlink "$nutram_dir/exe")" = "$nutram_exe" ] || return 1
        [ "$(cat "$nutram_dir/comm")" = "$nutram_comm" ] || return 1
        case "$nutram_group:$nutram_exe:$nutram_comm" in
            /nutus3000_ram.slice/nut-us3000-ram-server.service:/run/nut-us3000-ram/bin/nutus3000-srv:nutus3000-srv)
                [ "$nutram_server" = 0 ] || return 1
                nutram_server=${nutram_dir##*/}; nutram_server_stamp=$nutram_stamp ;;
            /nutus3000_ram.slice/nut-us3000-ram-driver.service:/run/nut-us3000-ram/bin/nutus3000-hid:nutus3000-hid)
                [ "$nutram_driver" = 0 ] || return 1
                nutram_driver=${nutram_dir##*/}; nutram_driver_stamp=$nutram_stamp ;;
            *) return 1 ;;
        esac
        LC_ALL=C awk -v uid="$nutram_uid" -v gid="$nutram_gid" '
            $1=="Uid:" {u++; if (NF!=5) bad=1; for(i=2;i<=5;i++) if ($i !~ /^[0-9]+$/ || $i!=uid) bad=1}
            $1=="Gid:" {g++; if (NF!=5) bad=1; for(i=2;i<=5;i++) if ($i !~ /^[0-9]+$/ || $i!=gid) bad=1}
            END {exit (bad || u!=1 || g!=1)}
        ' "$nutram_dir/status" || return 1
        [ "$(nutram_proc_stamp "$nutram_dir")" = "$nutram_stamp" ] || return 1
    done
    # A PID disappearing/reused while we scanned later entries is ambiguous.
    if [ "$nutram_server" != 0 ]; then
        [ "$(nutram_proc_stamp "/proc/$nutram_server")" = "$nutram_server_stamp" ] || return 1
    fi
    if [ "$nutram_driver" != 0 ]; then
        [ "$(nutram_proc_stamp "/proc/$nutram_driver")" = "$nutram_driver_stamp" ] || return 1
    fi
    printf 'server=%s\ndriver=%s\n' "$nutram_server" "$nutram_driver"
)
