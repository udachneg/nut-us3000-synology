#!/bin/sh
# OFFLINE ADAPTER, NOT INSTALLED OR SOURCED BY THE SPK.
# No process, filesystem, systemctl or hardware operations at source time.
# 'current' is a contract for trusted, fresh observation, NOT a marker/env flag.
# The DSM observation producer is not implemented; never supply 'current' in
# production on the basis of an empty SYNOPKG_PKG_STATUS or /tmp/ups.safedown.

nutram_stop_decision() {
    [ "$#" -eq 3 ] || return 64
    # Explicit package operations always win, even during safe shutdown.
    case "$1" in
        STOP|UNINSTALL|UPGRADE) printf '%s\n' stop; return 0 ;;
        '') ;;
        *) printf '%s\n' stop; return 0 ;;
    esac
    # Only proven safe intent + proven absence of terminal shutdown can preserve.
    # Unknown observations keep normal stop semantics, never silently opt in.
    if [ "$2" = current ] && [ "$3" = absent ]; then
        printf '%s\n' preserve
    else
        printf '%s\n' stop
    fi
}

nutram_package_stop() {
    [ "$#" -eq 3 ] || return 64
    nutram_stop_choice=$(nutram_stop_decision "$@") || return 1
    # Required bindings are supplied only by the local harness for now.
    # The ordinary package controller must not restart or retain volume handles.
    nutram_controller_stop || return 1
    case "$nutram_stop_choice" in
        preserve) return 0 ;;
        stop)
            nutram_runtime_stop || return 1
            # Requires exact identity/cgroup and closed sockets, not status alone.
            nutram_runtime_quiescent || return 1
            nutram_host_release || return 1
            ;;
        *) return 1 ;;
    esac
}

# Local binding only: STATUS PARSER_PATH PROFILE RC CAPTURE_STATE STDOUT STDERR.
# PARSER_PATH and snapshots are trusted harness inputs, NOT a privileged API.
# A future installed manager must bind fixed code and fresh capture internally;
# it must not accept this path, metadata or preserve intent from package callers.
nutram_package_stop_from_queue() {
    [ "$#" -eq 7 ] || return 64
    # Explicit/unknown actions need no queue read; old policy remains authoritative.
    if [ -n "$1" ]; then
        nutram_package_stop "$1" unknown unknown
        return $?
    fi
    if [ -f "$2" ] && [ ! -L "$2" ] && [ -r "$2" ]; then
        if nutram_queue_intent=$(/bin/sh "$2" "$3" "$4" "$5" "$6" "$7" 2>/dev/null); then
            if [ "$nutram_queue_intent" = SAFE_ENTRY_PENDING ]; then
                nutram_package_stop "$1" current absent
                return $?
            fi
        fi
    fi
    # Missing parser, nonzero status, UNKNOWN, terminal or malformed output:
    # choose normal stop, but never suppress an error from the lifecycle itself.
    nutram_package_stop "$1" unknown unknown
}

nutram_property() {
    [ "$#" -eq 1 ] || return 64
    # For `systemctl show UNIT -p KEY`, supported by 219. No --value dependency.
    case "$1" in LoadState|ActiveState|SubState|Job|MainPID) ;; *) return 64 ;; esac
    awk -v key="$1" '
        index($0, key "=") == 1 { count++; value=substr($0, length(key)+2) }
        END {
            if (count != 1 || value == "") exit 1
            print value
        }
    '
}
