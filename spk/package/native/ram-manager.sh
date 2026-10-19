#!/bin/sh
# LOCAL STOP-ENTRY PROTOTYPE ONLY. No actions when sourced, no installed root API.
# Trusted bootstrap must source hook-policy.sh and bind its lifecycle callbacks.
# Deployment must make this code, reader/parser and their parents root-owned,
# non-writable by package callers. Fixed paths alone do not establish trust.
# Only STATUS is accepted here, never a caller-supplied path/snapshot/preserve.
nutram_manager_stop() {
    [ "$#" -eq 1 ] || return 64
    # Explicit operations do not wait for a queue read and cannot preserve RAM.
    if [ -n "$1" ]; then
        nutram_package_stop "$1" unknown unknown
        return $?
    fi
    nutram_manager_reader=/run/nut-us3000-ram/manager/queue-reader.sh
    if [ -f "$nutram_manager_reader" ] && [ ! -L "$nutram_manager_reader" ] &&
        [ -r "$nutram_manager_reader" ]; then
        # Fresh bounded reader owns capture/cleanup; no intent from environment.
        if nutram_manager_intent=$(/bin/sh "$nutram_manager_reader" 2>/dev/null); then
            if [ "$nutram_manager_intent" = SAFE_ENTRY_PENDING ]; then
                nutram_package_stop "$1" current absent
                return $?
            fi
        fi
    fi
    # Reader failure/missing/UNKNOWN/terminal: ordinary stop. Lifecycle failures
    # must propagate; neither successful observation nor fallback means success.
    nutram_package_stop "$1" unknown unknown
}
