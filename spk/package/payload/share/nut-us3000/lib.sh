#!/bin/sh

# This file is sourced by DSM lifecycle scripts.  Keep it side-effect free:
# every public or private helper is namespaced and no shell options are changed.

# Presentation only: fixed helper vocabulary, bounded best-effort call.
nutus3000_description_publish() {
    case ${1:-} in pending|waiting|healthy|degraded|unavailable|error|stopped) ;; *) return 0 ;; esac
    /usr/bin/timeout -k 1 2 "$SYNOPKG_PKGDEST/libexec/nut/nut-us3000-hostctl" \
        "description-$1" >/dev/null 2>&1 || :
    return 0
}

nutus3000_description_finish() {
    # Only called by explicit start/stop/retry EXIT traps, never status.
    trap - EXIT
    nutus3000_description_rc=$1
    nutus3000_description_result=$2
    case $nutus3000_description_rc in 0|75) ;; *) nutus3000_description_result=error ;; esac
    nutus3000_description_publish "$nutus3000_description_result"
    exit "$nutus3000_description_rc"
}

nutus3000_canonical_dir() {
    [ $# -eq 1 ] || return 1
    [ -d "$1" ] || return 1
    (
        CDPATH= cd -P "$1" 2>/dev/null || exit 1
        pwd -P
    )
}

nutus3000_init() {
    [ -n "${SYNOPKG_PKGDEST:-}" ] || return 1
    [ -n "${SYNOPKG_PKGVAR:-}" ] || return 1

    nutus3000_target=$(nutus3000_canonical_dir "$SYNOPKG_PKGDEST") || return 1
    nutus3000_var=$(nutus3000_canonical_dir "$SYNOPKG_PKGVAR") || return 1
    nutus3000_path_is_physical "$nutus3000_target" || return 1
    nutus3000_path_is_physical "$nutus3000_var" || return 1
    nutus3000_config_alias=/var/packages/nut-us3000/etc
    nutus3000_config=$nutus3000_config_alias
    nutus3000_run=$nutus3000_var/run
    nutus3000_proc=/proc
    nutus3000_usb=/sys/bus/usb/devices
    nutus3000_version=/etc.defaults/VERSION
    nutus3000_timeout=/usr/bin/timeout
    nutus3000_netstat=/bin/netstat
    nutus3000_ip=/usr/sbin/ip
    nutus3000_stat=/usr/bin/stat
    nutus3000_id=/usr/bin/id
    nutus3000_sha256sum=/usr/bin/sha256sum
    nutus3000_readlink=/usr/bin/readlink
    nutus3000_uname=/bin/uname
    nutus3000_kill=/bin/kill
    nutus3000_sleep=/bin/sleep
    nutus3000_mv=/bin/mv

    nutus3000_driver_exe=$nutus3000_target/libexec/nut/usbhid-ups
    nutus3000_upsd_exe=$nutus3000_target/sbin/upsd
    nutus3000_upsdrvctl_exe=$nutus3000_target/sbin/upsdrvctl
    nutus3000_upsc_exe=$nutus3000_target/bin/upsc
    nutus3000_health_exe=$nutus3000_target/share/nut-us3000/healthcheck.sh
    nutus3000_controller_exe=$nutus3000_target/libexec/nut/nut-us3000-controller
    nutus3000_driver_identity=$nutus3000_run/usbhid-ups.identity
    nutus3000_upsd_identity=$nutus3000_run/upsd.identity
    nutus3000_driver_pidfile=$nutus3000_run/usbhid-ups-ups.pid
    nutus3000_upsd_pidfile=$nutus3000_run/upsd.pid
    nutus3000_driver_socket=$nutus3000_run/usbhid-ups-ups
    nutus3000_controller_identity=$nutus3000_run/nut-us3000-controller.identity
    nutus3000_controller_state=$nutus3000_run/controller-health.state
    nutus3000_uptime=$nutus3000_proc/uptime
    nutus3000_references_active=0
}

nutus3000_is_decimal() {
    case ${1-} in
        ''|*[!0-9]*) return 1 ;;
        *) return 0 ;;
    esac
}

nutus3000_read_one_line() {
    [ $# -eq 1 ] || return 2
    [ -f "$1" ] && [ ! -L "$1" ] || return 1
    (
        IFS= read -r nutus3000_rol_first || exit 1
        if IFS= read -r nutus3000_rol_extra; then
            exit 1
        fi
        printf '%s\n' "$nutus3000_rol_first"
    ) < "$1"
}

nutus3000_path_is_physical() {
    [ $# -eq 1 ] || return 1
    nutus3000_pip_path=$1
    case $nutus3000_pip_path in
        /*) ;;
        *) return 1 ;;
    esac
    while [ "$nutus3000_pip_path" != / ]; do
        [ ! -L "$nutus3000_pip_path" ] || return 1
        nutus3000_pip_path=${nutus3000_pip_path%/*}
        [ -n "$nutus3000_pip_path" ] || nutus3000_pip_path=/
    done
}

nutus3000_resolve_config() {
    nutus3000_rc_parent=${nutus3000_config_alias%/*}
    nutus3000_path_is_physical "$nutus3000_rc_parent" || return 1
    nutus3000_path_is_physical "$nutus3000_var" || return 1
    if [ -L "$nutus3000_config_alias" ]; then
        nutus3000_config=$(nutus3000_canonical_dir "$nutus3000_config_alias") || return 1
        case $nutus3000_var in
            */@appdata/nut-us3000)
                nutus3000_rc_expected=${nutus3000_var%/@appdata/nut-us3000}/@appconf/nut-us3000
                ;;
            *) return 1 ;;
        esac
        [ "$nutus3000_config" = "$nutus3000_rc_expected" ] || return 1
    fi
    nutus3000_path_is_physical "$nutus3000_config"
}

nutus3000_read_effective_ids() {
    nutus3000_uid=$($nutus3000_id -u) || return 1
    nutus3000_gid=$($nutus3000_id -g) || return 1
    nutus3000_is_decimal "$nutus3000_uid" || return 1
    nutus3000_is_decimal "$nutus3000_gid" || return 1
}

nutus3000_stat_is() {
    [ $# -eq 2 ] || return 1
    nutus3000_si_actual=$(LC_ALL=C "$nutus3000_stat" -c '%a:%u:%g' "$1") || return 1
    [ "$nutus3000_si_actual" = "$2:$nutus3000_uid:$nutus3000_gid" ]
}

nutus3000_validate_platform() {
    nutus3000_init || return 1
    nutus3000_path_is_physical "$nutus3000_version" || return 1
    [ -f "$nutus3000_version" ] && [ ! -L "$nutus3000_version" ] || return 1

    nutus3000_vp_product_count=0
    nutus3000_vp_build_count=0
    nutus3000_vp_nano_count=0
    nutus3000_vp_unique_count=0
    nutus3000_vp_product=
    nutus3000_vp_build=
    nutus3000_vp_nano=
    nutus3000_vp_unique=
    while IFS= read -r nutus3000_vp_line; do
        case $nutus3000_vp_line in
            productversion=*)
                nutus3000_vp_product_count=$((nutus3000_vp_product_count + 1))
                nutus3000_vp_product=$nutus3000_vp_line
                ;;
            buildnumber=*)
                nutus3000_vp_build_count=$((nutus3000_vp_build_count + 1))
                nutus3000_vp_build=$nutus3000_vp_line
                ;;
            smallfixnumber=*)
                nutus3000_vp_nano_count=$((nutus3000_vp_nano_count + 1))
                nutus3000_vp_nano=$nutus3000_vp_line
                ;;
            unique=*)
                nutus3000_vp_unique_count=$((nutus3000_vp_unique_count + 1))
                nutus3000_vp_unique=$nutus3000_vp_line
                ;;
        esac
    done < "$nutus3000_version" || return 1
    [ "$nutus3000_vp_product_count" -eq 1 ] || return 1
    [ "$nutus3000_vp_build_count" -eq 1 ] || return 1
    case $nutus3000_vp_product in
        'productversion="'*'"')
            nutus3000_vp_product=${nutus3000_vp_product#productversion=\"}
            nutus3000_vp_product=${nutus3000_vp_product%\"}
            ;;
        *) return 1 ;;
    esac
    case $nutus3000_vp_product in
        7.2.*)
            # Preserve the existing 7.2 policy, including later patch releases.
            nutus3000_vp_patch=${nutus3000_vp_product#7.2.}
            nutus3000_is_decimal "$nutus3000_vp_patch" || return 1
            case $nutus3000_vp_patch in 0|1|0*) return 1 ;; esac
            ;;
        7.4.1)
            # Narrow opt-in: inspected SA6400 base90080 and Update 1 only.
            [ "$nutus3000_vp_build" = 'buildnumber="90080"' ] || return 1
            [ "$nutus3000_vp_nano_count" -eq 1 ] || return 1
            [ "$nutus3000_vp_unique_count" -eq 1 ] || return 1
            [ "$nutus3000_vp_unique" = 'unique="synology_epyc7002_sa6400"' ] || return 1
            case $nutus3000_vp_nano in
                'smallfixnumber="0"'|'smallfixnumber="1"') ;;
                *) return 1 ;;
            esac
            ;;
        *) return 1 ;;
    esac

    case $nutus3000_vp_build in
        'buildnumber="'*'"')
            nutus3000_vp_build=${nutus3000_vp_build#buildnumber=\"}
            nutus3000_vp_build=${nutus3000_vp_build%\"}
            ;;
        *) return 1 ;;
    esac
    nutus3000_is_decimal "$nutus3000_vp_build" || return 1
    case $nutus3000_vp_build in 0*) return 1 ;; esac
    nutus3000_vp_build_length=${#nutus3000_vp_build}
    [ "$nutus3000_vp_build_length" -le 10 ] || return 1
    if [ "$nutus3000_vp_build_length" -lt 5 ]; then
        return 1
    fi
    if [ "$nutus3000_vp_build_length" -eq 5 ]; then
        [ "$nutus3000_vp_build" -ge 72806 ] || return 1
    fi

    nutus3000_vp_machine=$($nutus3000_uname -m) || return 1
    [ "$nutus3000_vp_machine" = x86_64 ] || return 1
    nutus3000_vp_uname=$($nutus3000_uname -a) || return 1
    nutus3000_vp_platform_count=0
    for nutus3000_vp_token in $nutus3000_vp_uname; do
        case $nutus3000_vp_token in
            synology_epyc7002_*)
                if [ "$nutus3000_vp_product" = 7.4.1 ]; then
                    [ "$nutus3000_vp_token" = synology_epyc7002_sa6400 ] || return 1
                fi
                nutus3000_vp_platform_count=$((nutus3000_vp_platform_count + 1))
                ;;
        esac
    done
    [ "$nutus3000_vp_platform_count" -eq 1 ]
}

nutus3000_validate_manifest_records() {
    nutus3000_vmr_ups=0
    nutus3000_vmr_upsd=0
    nutus3000_vmr_users=0
    while :; do
        nutus3000_vmr_line=
        IFS= read -r nutus3000_vmr_line
        nutus3000_vmr_rc=$?
        if [ "$nutus3000_vmr_rc" -ne 0 ]; then
            [ -z "$nutus3000_vmr_line" ] || return 1
            break
        fi
        nutus3000_vmr_digest=${nutus3000_vmr_line%%  *}
        nutus3000_vmr_rest=${nutus3000_vmr_line#"$nutus3000_vmr_digest"}
        [ "$nutus3000_vmr_rest" != "$nutus3000_vmr_line" ] || return 1
        case $nutus3000_vmr_digest in
            ''|*[!0-9a-f]*) return 1 ;;
        esac
        [ "${#nutus3000_vmr_digest}" -eq 64 ] || return 1
        case $nutus3000_vmr_rest in
            '  ups.conf') nutus3000_vmr_ups=$((nutus3000_vmr_ups + 1)) ;;
            '  upsd.conf') nutus3000_vmr_upsd=$((nutus3000_vmr_upsd + 1)) ;;
            '  upsd.users') nutus3000_vmr_users=$((nutus3000_vmr_users + 1)) ;;
            *) return 1 ;;
        esac
    done < "$nutus3000_var/config-manifest.sha256"
    [ "$nutus3000_vmr_ups" -eq 1 ] || return 1
    [ "$nutus3000_vmr_upsd" -eq 1 ] || return 1
    [ "$nutus3000_vmr_users" -eq 1 ] || return 1
}

nutus3000_validate_config() {
    nutus3000_init || return 1
    nutus3000_read_effective_ids || return 1
    nutus3000_resolve_config || return 1
    [ -d "$nutus3000_config" ] && [ ! -L "$nutus3000_config" ] || return 1
    nutus3000_stat_is "$nutus3000_config" 750 || return 1
    for nutus3000_vc_name in ups.conf upsd.conf upsd.users; do
        nutus3000_vc_path=$nutus3000_config/$nutus3000_vc_name
        [ -f "$nutus3000_vc_path" ] && [ ! -L "$nutus3000_vc_path" ] || return 1
    done
    nutus3000_stat_is "$nutus3000_config/ups.conf" 640 || return 1
    nutus3000_stat_is "$nutus3000_config/upsd.conf" 640 || return 1
    nutus3000_stat_is "$nutus3000_config/upsd.users" 600 || return 1
    nutus3000_vc_manifest=$nutus3000_var/config-manifest.sha256
    [ -f "$nutus3000_vc_manifest" ] && [ ! -L "$nutus3000_vc_manifest" ] || return 1
    nutus3000_stat_is "$nutus3000_vc_manifest" 600 || return 1
    nutus3000_validate_manifest_records || return 1
    (cd -P "$nutus3000_config" && "$nutus3000_sha256sum" -c "$nutus3000_vc_manifest" >/dev/null 2>&1) || return 1
}

nutus3000_probe_usb() {
    nutus3000_init || return 1
    nutus3000_vu_matches=0
    nutus3000_vu_pending=0
    for nutus3000_vu_device in "$nutus3000_usb"/*; do
        [ -d "$nutus3000_vu_device" ] || continue
        nutus3000_vu_vendor=$nutus3000_vu_device/idVendor
        nutus3000_vu_product=$nutus3000_vu_device/idProduct
        nutus3000_vu_serial=$nutus3000_vu_device/serial
        if [ -e "$nutus3000_vu_vendor" ] || [ -L "$nutus3000_vu_vendor" ] \
            || [ -e "$nutus3000_vu_product" ] || [ -L "$nutus3000_vu_product" ] \
            || [ -e "$nutus3000_vu_serial" ] || [ -L "$nutus3000_vu_serial" ]; then
            [ -f "$nutus3000_vu_vendor" ] && [ ! -L "$nutus3000_vu_vendor" ] || return 1
            [ -f "$nutus3000_vu_product" ] && [ ! -L "$nutus3000_vu_product" ] || return 1
        else
            continue
        fi
        nutus3000_vu_vendor_value=$(nutus3000_read_one_line "$nutus3000_vu_vendor") || continue
        nutus3000_vu_product_value=$(nutus3000_read_one_line "$nutus3000_vu_product") || continue
        [ "$nutus3000_vu_vendor_value:$nutus3000_vu_product_value" = 2b89:ffff ] || continue
        nutus3000_vu_matches=$((nutus3000_vu_matches + 1))
        if [ ! -e "$nutus3000_vu_serial" ] && [ ! -L "$nutus3000_vu_serial" ]; then
            nutus3000_vu_pending=1
        else
            [ -f "$nutus3000_vu_serial" ] && [ ! -L "$nutus3000_vu_serial" ] || return 1
            [ "$(nutus3000_read_one_line "$nutus3000_vu_serial")" = DC600 ] || return 1
        fi
        nutus3000_vu_interfaces=0
        for nutus3000_vu_interface in "$nutus3000_vu_device":*; do
            [ -d "$nutus3000_vu_interface" ] || continue
            nutus3000_vu_interfaces=$((nutus3000_vu_interfaces + 1))
            nutus3000_vu_number=$nutus3000_vu_interface/bInterfaceNumber
            if [ ! -e "$nutus3000_vu_number" ] && [ ! -L "$nutus3000_vu_number" ]; then
                nutus3000_vu_pending=1
                continue
            fi
            [ -f "$nutus3000_vu_number" ] && [ ! -L "$nutus3000_vu_number" ] || return 1
            [ "$(nutus3000_read_one_line "$nutus3000_vu_number")" = 00 ] || return 1
        done
        [ "$nutus3000_vu_interfaces" -le 1 ] || return 1
        [ "$nutus3000_vu_interfaces" -ne 0 ] || nutus3000_vu_pending=1
    done
    [ "$nutus3000_vu_matches" -le 1 ] || return 1
    [ "$nutus3000_vu_pending" -eq 0 ] || return 75
    [ "$nutus3000_vu_matches" -eq 1 ] && return 0
    return 75
}

nutus3000_validate_usb() {
    nutus3000_probe_usb
    [ $? -eq 0 ]
}

nutus3000_proc_read() {
    nutus3000_pr_pid=$1
    nutus3000_pr_dir=$nutus3000_proc/$nutus3000_pr_pid
    nutus3000_pr_comm_available=0
    nutus3000_pr_comm=
    nutus3000_pr_state=
    nutus3000_pr_starttime=
    nutus3000_pr_exe=
    [ -d "$nutus3000_pr_dir" ] || return 1
    if nutus3000_pr_comm=$(nutus3000_read_one_line "$nutus3000_pr_dir/comm" 2>/dev/null); then
        nutus3000_pr_comm_available=1
    fi
    nutus3000_pr_stat=$(nutus3000_read_one_line "$nutus3000_pr_dir/stat" 2>/dev/null) || {
        [ -d "$nutus3000_pr_dir" ] || return 1
        return 2
    }
    nutus3000_pr_rest=${nutus3000_pr_stat##*) }
    [ "$nutus3000_pr_rest" != "$nutus3000_pr_stat" ] || return 2
    nutus3000_pr_index=1
    while [ "$nutus3000_pr_index" -le 20 ]; do
        case $nutus3000_pr_rest in
            *' '*)
                nutus3000_pr_token=${nutus3000_pr_rest%% *}
                nutus3000_pr_rest=${nutus3000_pr_rest#* }
                ;;
            *)
                nutus3000_pr_token=$nutus3000_pr_rest
                nutus3000_pr_rest=
                ;;
        esac
        [ -n "$nutus3000_pr_token" ] || return 2
        if [ "$nutus3000_pr_index" -eq 1 ]; then
            nutus3000_pr_state=$nutus3000_pr_token
        elif [ "$nutus3000_pr_index" -eq 20 ]; then
            nutus3000_pr_starttime=$nutus3000_pr_token
        fi
        nutus3000_pr_index=$((nutus3000_pr_index + 1))
    done
    nutus3000_is_decimal "$nutus3000_pr_starttime" || return 2
    case $nutus3000_pr_state in
        R|S|D|T|t|X|x|K|W|P|I) ;;
        Z) return 1 ;;
        *) return 2 ;;
    esac
    nutus3000_pr_exe=$($nutus3000_readlink "$nutus3000_pr_dir/exe" 2>/dev/null) || {
        [ -d "$nutus3000_pr_dir" ] || return 1
        return 2
    }
    case $nutus3000_pr_exe in
        /*) ;;
        *) return 2 ;;
    esac
    nutus3000_pr_tuple=$nutus3000_pr_pid:$nutus3000_pr_starttime:$nutus3000_pr_exe
    return 0
}

nutus3000_read_native_pid() {
    nutus3000_rnp_path=$1
    [ -e "$nutus3000_rnp_path" ] || [ -L "$nutus3000_rnp_path" ] || return 1
    nutus3000_rnp_value=$(nutus3000_read_one_line "$nutus3000_rnp_path") || return 2
    nutus3000_is_decimal "$nutus3000_rnp_value" || return 2
    printf '%s\n' "$nutus3000_rnp_value"
}

nutus3000_read_identity() {
    nutus3000_ri_path=$1
    nutus3000_ri_expected=$2
    [ -e "$nutus3000_ri_path" ] || [ -L "$nutus3000_ri_path" ] || return 1
    [ -f "$nutus3000_ri_path" ] && [ ! -L "$nutus3000_ri_path" ] || return 2
    nutus3000_stat_is "$nutus3000_ri_path" 600 || return 2
    nutus3000_ri_value=$(nutus3000_read_one_line "$nutus3000_ri_path") || return 2
    nutus3000_ri_pid=${nutus3000_ri_value%%:*}
    nutus3000_ri_tail=${nutus3000_ri_value#*:}
    [ "$nutus3000_ri_tail" != "$nutus3000_ri_value" ] || return 2
    nutus3000_ri_start=${nutus3000_ri_tail%%:*}
    nutus3000_ri_exe=${nutus3000_ri_tail#*:}
    [ "$nutus3000_ri_exe" != "$nutus3000_ri_tail" ] || return 2
    nutus3000_is_decimal "$nutus3000_ri_pid" || return 2
    nutus3000_is_decimal "$nutus3000_ri_start" || return 2
    [ "$nutus3000_ri_exe" = "$nutus3000_ri_expected" ] || return 2
    printf '%s\n' "$nutus3000_ri_value"
}

nutus3000_load_references() {
    nutus3000_lr_role=${1-all}
    case $nutus3000_lr_role in all|server|driver|controller) ;; *) return 2 ;; esac
    nutus3000_references_active=0
    nutus3000_ref_driver_identity=
    nutus3000_ref_upsd_identity=
    nutus3000_ref_driver_native=
    nutus3000_ref_upsd_native=
    nutus3000_ref_controller_identity=
    [ -e "$nutus3000_run" ] || [ -L "$nutus3000_run" ] || return 0
    [ -d "$nutus3000_run" ] && [ ! -L "$nutus3000_run" ] || return 2
    nutus3000_read_effective_ids || return 2
    nutus3000_path_is_physical "$nutus3000_run" || return 2
    nutus3000_stat_is "$nutus3000_run" 750 || return 2

    if [ "$nutus3000_lr_role" = all ] || [ "$nutus3000_lr_role" = driver ]; then
        if [ -e "$nutus3000_driver_identity" ] || [ -L "$nutus3000_driver_identity" ]; then
            nutus3000_lr_value=$(nutus3000_read_identity "$nutus3000_driver_identity" "$nutus3000_driver_exe") || return 2
            nutus3000_ref_driver_identity=${nutus3000_lr_value%%:*}
        fi
        if [ -e "$nutus3000_driver_pidfile" ] || [ -L "$nutus3000_driver_pidfile" ]; then
            nutus3000_ref_driver_native=$(nutus3000_read_native_pid "$nutus3000_driver_pidfile") || return 2
        fi
    fi
    if [ "$nutus3000_lr_role" = all ] || [ "$nutus3000_lr_role" = server ]; then
        if [ -e "$nutus3000_upsd_identity" ] || [ -L "$nutus3000_upsd_identity" ]; then
            nutus3000_lr_value=$(nutus3000_read_identity "$nutus3000_upsd_identity" "$nutus3000_upsd_exe") || return 2
            nutus3000_ref_upsd_identity=${nutus3000_lr_value%%:*}
        fi
        if [ -e "$nutus3000_upsd_pidfile" ] || [ -L "$nutus3000_upsd_pidfile" ]; then
            nutus3000_ref_upsd_native=$(nutus3000_read_native_pid "$nutus3000_upsd_pidfile") || return 2
        fi
    fi
    if [ "$nutus3000_lr_role" = all ] || [ "$nutus3000_lr_role" = controller ]; then
        if [ -e "$nutus3000_controller_identity" ] || [ -L "$nutus3000_controller_identity" ]; then
            nutus3000_lr_value=$(nutus3000_read_identity "$nutus3000_controller_identity" "$nutus3000_controller_exe") || return 2
            nutus3000_ref_controller_identity=${nutus3000_lr_value%%:*}
        fi
    fi
    nutus3000_references_active=1
}

nutus3000_pid_is_referenced() {
    [ "$1" = "$nutus3000_ref_driver_identity" ] \
        || [ "$1" = "$nutus3000_ref_upsd_identity" ] \
        || [ "$1" = "$nutus3000_ref_driver_native" ] \
        || [ "$1" = "$nutus3000_ref_upsd_native" ] \
        || [ "$1" = "$nutus3000_ref_controller_identity" ]
}

nutus3000_scan_all_package_processes() {
    nutus3000_scan_found=0
    nutus3000_load_references || return 2
    for nutus3000_sap_entry in "$nutus3000_proc"/*; do
        nutus3000_sap_pid=${nutus3000_sap_entry##*/}
        nutus3000_is_decimal "$nutus3000_sap_pid" || continue
        [ -d "$nutus3000_sap_entry" ] || continue
        nutus3000_proc_read "$nutus3000_sap_pid"
        nutus3000_sap_rc=$?
        if [ "$nutus3000_sap_rc" -eq 1 ]; then
            continue
        elif [ "$nutus3000_sap_rc" -ne 0 ]; then
            if { [ "$nutus3000_pr_comm_available" -eq 1 ] \
                    && { [ "$nutus3000_pr_comm" = usbhid-ups ] \
                        || [ "$nutus3000_pr_comm" = upsd ] \
                        || [ "$nutus3000_pr_comm" = upsdrvctl ] \
                        || [ "$nutus3000_pr_comm" = nut-us3000-cont ]; }; } \
                || nutus3000_pid_is_referenced "$nutus3000_sap_pid"; then
                return 2
            fi
            continue
        fi
        case $nutus3000_pr_exe in
            "$nutus3000_driver_exe"|"$nutus3000_upsd_exe"|"$nutus3000_upsdrvctl_exe"|"$nutus3000_controller_exe")
                nutus3000_scan_found=1
                ;;
        esac
    done
    return 0
}

nutus3000_any_exact_package_pid() {
    nutus3000_init || return 2
    nutus3000_scan_all_package_processes || return 2
    [ "$nutus3000_scan_found" -eq 0 ] || return 0
    return 1
}

nutus3000_preflight_no_foreign() {
    nutus3000_pnf_allow_controller=${1-0}
    case $nutus3000_pnf_allow_controller in 0|1) ;; *) return 1 ;; esac
    nutus3000_load_references || return 1
    for nutus3000_pnf_entry in "$nutus3000_proc"/*; do
        nutus3000_pnf_pid=${nutus3000_pnf_entry##*/}
        nutus3000_is_decimal "$nutus3000_pnf_pid" || continue
        [ -d "$nutus3000_pnf_entry" ] || continue
        nutus3000_proc_read "$nutus3000_pnf_pid"
        nutus3000_pnf_rc=$?
        if [ "$nutus3000_pr_comm_available" -eq 1 ]; then
            case $nutus3000_pr_comm in
                usbhid-ups|upsd|upsdrvctl) return 1 ;;
                nut-us3000-cont)
                    [ "$nutus3000_pnf_allow_controller" -eq 1 ] || return 1
                    ;;
            esac
        fi
        if [ "$nutus3000_pnf_rc" -eq 0 ]; then
            case $nutus3000_pr_exe in
                "$nutus3000_driver_exe"|"$nutus3000_upsd_exe"|"$nutus3000_upsdrvctl_exe") return 1 ;;
                "$nutus3000_controller_exe")
                    [ "$nutus3000_pnf_allow_controller" -eq 1 ] || return 1
                    ;;
            esac
        elif [ "$nutus3000_pnf_rc" -ne 1 ] && nutus3000_pid_is_referenced "$nutus3000_pnf_pid"; then
            return 1
        fi
    done
}

nutus3000_read_port_rows() {
    nutus3000_port_count=0
    nutus3000_port_loopback=0
    nutus3000_port_alias=0
    nutus3000_port_unexpected=0
    nutus3000_pr_output=$($nutus3000_netstat -lnt) || return 1
    while IFS= read -r nutus3000_pr_line; do
        set -- $nutus3000_pr_line
        [ $# -ge 4 ] || continue
        case $1 in tcp|tcp6) ;; *) continue ;; esac
        case $4 in
            *:3493)
                nutus3000_port_count=$((nutus3000_port_count + 1))
                case $4 in
                    127.0.0.1:3493)
                        nutus3000_port_loopback=$((nutus3000_port_loopback + 1))
                        ;;
                    10.255.255.1:3493)
                        nutus3000_port_alias=$((nutus3000_port_alias + 1))
                        ;;
                    *)
                        nutus3000_port_unexpected=$((nutus3000_port_unexpected + 1))
                        ;;
                esac
                ;;
        esac
    done <<EOF
$nutus3000_pr_output
EOF
}

nutus3000_port_is_free() {
    nutus3000_read_port_rows || return 1
    [ "$nutus3000_port_count" -eq 0 ]
}

nutus3000_port_is_host_local_exact() {
    nutus3000_read_port_rows || return 1
    [ "$nutus3000_port_count" -eq 2 ] || return 1
    [ "$nutus3000_port_loopback:$nutus3000_port_alias:$nutus3000_port_unexpected" = 1:1:0 ]
}

nutus3000_alias_is_exact() {
    [ -x "$nutus3000_ip" ] || return 1
    nutus3000_alias_output=$($nutus3000_ip -4 -o address show to 10.255.255.1/32) || return 1
    nutus3000_alias_count=0
    nutus3000_alias_exact=0
    while IFS= read -r nutus3000_alias_line || [ -n "$nutus3000_alias_line" ]; do
        [ -n "$nutus3000_alias_line" ] || continue
        nutus3000_alias_count=$((nutus3000_alias_count + 1))
        set -- $nutus3000_alias_line
        [ "$#" -ge 7 ] || continue
        nutus3000_alias_interface=${2%:}
        [ "$nutus3000_alias_interface:$3:$4" = lo:inet:10.255.255.1/32 ] || continue
        nutus3000_alias_scope=0
        nutus3000_alias_label=0
        nutus3000_alias_previous=
        for nutus3000_alias_token in "$@"; do
            nutus3000_alias_token=${nutus3000_alias_token%\\}
            if [ "$nutus3000_alias_previous" = scope ] && [ "$nutus3000_alias_token" = host ]; then
                nutus3000_alias_scope=$((nutus3000_alias_scope + 1))
            fi
            [ "$nutus3000_alias_token" != lo:nutus3000 ] || \
                nutus3000_alias_label=$((nutus3000_alias_label + 1))
            nutus3000_alias_previous=$nutus3000_alias_token
        done
        [ "$nutus3000_alias_scope:$nutus3000_alias_label" = 1:1 ] || continue
        nutus3000_alias_exact=$((nutus3000_alias_exact + 1))
    done <<EOF
$nutus3000_alias_output
EOF
    [ "$nutus3000_alias_count:$nutus3000_alias_exact" = 1:1 ]
}

nutus3000_prepare_run() {
    nutus3000_read_effective_ids || return 1
    nutus3000_path_is_physical "$nutus3000_var" || return 1
    if [ -e "$nutus3000_run" ] || [ -L "$nutus3000_run" ]; then
        [ -d "$nutus3000_run" ] && [ ! -L "$nutus3000_run" ] || return 1
        nutus3000_path_is_physical "$nutus3000_run" || return 1
        nutus3000_stat_is "$nutus3000_run" 750 || return 1
    else
        (umask 027 && mkdir "$nutus3000_run") || return 1
        chmod 750 "$nutus3000_run" || return 1
        nutus3000_path_is_physical "$nutus3000_run" || return 1
        nutus3000_stat_is "$nutus3000_run" 750 || return 1
    fi
}

nutus3000_scan_exact() {
    nutus3000_se_expected=$1
    nutus3000_se_comm=$2
    nutus3000_scan_count=0
    nutus3000_scan_pid=
    nutus3000_scan_tuple=
    for nutus3000_se_entry in "$nutus3000_proc"/*; do
        nutus3000_se_pid=${nutus3000_se_entry##*/}
        nutus3000_is_decimal "$nutus3000_se_pid" || continue
        [ -d "$nutus3000_se_entry" ] || continue
        nutus3000_proc_read "$nutus3000_se_pid"
        nutus3000_se_rc=$?
        if [ "$nutus3000_se_rc" -eq 1 ]; then
            continue
        elif [ "$nutus3000_se_rc" -ne 0 ]; then
            if { [ "$nutus3000_pr_comm_available" -eq 1 ] \
                    && [ "$nutus3000_pr_comm" = "$nutus3000_se_comm" ]; } \
                || { [ "$nutus3000_references_active" -eq 1 ] \
                    && nutus3000_pid_is_referenced "$nutus3000_se_pid"; }; then
                return 2
            fi
            continue
        fi
        if [ "$nutus3000_pr_exe" = "$nutus3000_se_expected" ]; then
            nutus3000_scan_count=$((nutus3000_scan_count + 1))
            nutus3000_scan_pid=$nutus3000_se_pid
            nutus3000_scan_tuple=$nutus3000_pr_tuple
        fi
    done
}

nutus3000_publish_identity() {
    nutus3000_pi_path=$1
    nutus3000_pi_tuple=$2
    [ ! -e "$nutus3000_pi_path" ] && [ ! -L "$nutus3000_pi_path" ] || return 1
    nutus3000_pi_tmp=$nutus3000_run/.${nutus3000_pi_path##*/}.$$
    [ ! -e "$nutus3000_pi_tmp" ] && [ ! -L "$nutus3000_pi_tmp" ] || return 1
    (umask 077 && set -C && printf '%s\n' "$nutus3000_pi_tuple" > "$nutus3000_pi_tmp") || return 1
    chmod 600 "$nutus3000_pi_tmp" || { rm -f "$nutus3000_pi_tmp"; return 1; }
    if ln "$nutus3000_pi_tmp" "$nutus3000_pi_path"; then
        rm -f "$nutus3000_pi_tmp"
    else
        rm -f "$nutus3000_pi_tmp"
        return 1
    fi
    nutus3000_stat_is "$nutus3000_pi_path" 600
}

nutus3000_capture_identity() {
    nutus3000_ci_kind=$1
    if [ "$nutus3000_ci_kind" = driver ]; then
        nutus3000_ci_expected=$nutus3000_driver_exe
        nutus3000_ci_comm=usbhid-ups
        nutus3000_ci_pidfile=$nutus3000_driver_pidfile
        nutus3000_ci_identity=$nutus3000_driver_identity
    else
        nutus3000_ci_expected=$nutus3000_upsd_exe
        nutus3000_ci_comm=upsd
        nutus3000_ci_pidfile=$nutus3000_upsd_pidfile
        nutus3000_ci_identity=$nutus3000_upsd_identity
    fi
    nutus3000_ci_native_kind=fallback
    nutus3000_ci_pid=
    if [ -e "$nutus3000_ci_pidfile" ] || [ -L "$nutus3000_ci_pidfile" ]; then
        if nutus3000_ci_pid=$(nutus3000_read_native_pid "$nutus3000_ci_pidfile" 2>/dev/null); then
            nutus3000_ci_native_kind=valid
        fi
    fi
    nutus3000_ci_tuple=
    if [ -n "$nutus3000_ci_pid" ]; then
        if nutus3000_proc_read "$nutus3000_ci_pid" && [ "$nutus3000_pr_exe" = "$nutus3000_ci_expected" ]; then
            nutus3000_ci_tuple=$nutus3000_pr_tuple
        fi
    fi
    if [ -z "$nutus3000_ci_tuple" ]; then
        nutus3000_scan_exact "$nutus3000_ci_expected" "$nutus3000_ci_comm" || return 1
        [ "$nutus3000_scan_count" -eq 1 ] || return 1
        nutus3000_ci_tuple=$nutus3000_scan_tuple
    fi
    nutus3000_publish_identity "$nutus3000_ci_identity" "$nutus3000_ci_tuple" || return 1
    nutus3000_ci_captured_pid=${nutus3000_ci_tuple%%:*}
    if [ "$nutus3000_ci_native_kind" = valid ]; then
        [ "$nutus3000_ci_pid" = "$nutus3000_ci_captured_pid" ] || return 1
        nutus3000_ci_native_again=$(nutus3000_read_native_pid "$nutus3000_ci_pidfile" 2>/dev/null) || return 1
        [ "$nutus3000_ci_native_again" = "$nutus3000_ci_captured_pid" ]
        return
    fi
    if nutus3000_ci_native_again=$(nutus3000_read_native_pid "$nutus3000_ci_pidfile" 2>/dev/null); then
        [ "$nutus3000_ci_native_again" = "$nutus3000_ci_captured_pid" ] || return 1
    fi
    return 0
}

nutus3000_tuple_is_live() {
    nutus3000_til_tuple=$1
    nutus3000_til_expected=$2
    nutus3000_til_pid=${nutus3000_til_tuple%%:*}
    nutus3000_proc_read "$nutus3000_til_pid" || return $?
    [ "$nutus3000_pr_exe" = "$nutus3000_til_expected" ] || return 2
    [ "$nutus3000_pr_tuple" = "$nutus3000_til_tuple" ] || return 2
}

nutus3000_wait_absent() {
    nutus3000_wa_tuple=$1
    nutus3000_wa_expected=$2
    nutus3000_wa_count=0
    while [ "$nutus3000_wa_count" -lt 3 ]; do
        nutus3000_tuple_is_live "$nutus3000_wa_tuple" "$nutus3000_wa_expected"
        nutus3000_wa_rc=$?
        [ "$nutus3000_wa_rc" -eq 1 ] && return 0
        [ "$nutus3000_wa_rc" -eq 0 ] || return 1
        "$nutus3000_sleep" 1 || return 1
        nutus3000_wa_count=$((nutus3000_wa_count + 1))
    done
    nutus3000_tuple_is_live "$nutus3000_wa_tuple" "$nutus3000_wa_expected"
    [ $? -eq 1 ]
}

nutus3000_remove_server_state() {
    rm -f "$nutus3000_upsd_identity" "$nutus3000_upsd_pidfile"
}

nutus3000_remove_driver_state() {
    rm -f "$nutus3000_driver_identity" "$nutus3000_driver_pidfile" "$nutus3000_driver_socket"
}

nutus3000_stop_server() {
    nutus3000_load_references server || return 1
    nutus3000_scan_exact "$nutus3000_upsd_exe" upsd || return 1
    nutus3000_ss_count=$nutus3000_scan_count
    nutus3000_ss_scan_tuple=$nutus3000_scan_tuple
    if [ ! -e "$nutus3000_upsd_identity" ] && [ ! -L "$nutus3000_upsd_identity" ]; then
        [ "$nutus3000_ss_count" -eq 0 ] || return 1
        if [ -e "$nutus3000_upsd_pidfile" ] || [ -L "$nutus3000_upsd_pidfile" ]; then
            nutus3000_read_native_pid "$nutus3000_upsd_pidfile" >/dev/null || return 1
        fi
        nutus3000_remove_server_state || return 1
        return 0
    fi
    nutus3000_ss_identity=$(nutus3000_read_identity "$nutus3000_upsd_identity" "$nutus3000_upsd_exe") || return 1
    nutus3000_ss_pid=${nutus3000_ss_identity%%:*}
    nutus3000_ss_native=$(nutus3000_read_native_pid "$nutus3000_upsd_pidfile" 2>/dev/null) || nutus3000_ss_native=
    nutus3000_tuple_is_live "$nutus3000_ss_identity" "$nutus3000_upsd_exe"
    nutus3000_ss_live_rc=$?
    if [ "$nutus3000_ss_live_rc" -ne 0 ]; then
        [ "$nutus3000_ss_live_rc" -eq 1 ] || return 1
        nutus3000_scan_exact "$nutus3000_upsd_exe" upsd || return 1
        [ "$nutus3000_scan_count" -eq 0 ] || return 1
        nutus3000_remove_server_state || return 1
        return 0
    fi
    [ -n "$nutus3000_ss_native" ] && [ "$nutus3000_ss_native" = "$nutus3000_ss_pid" ] || return 1
    [ "$nutus3000_ss_count" -eq 1 ] && [ "$nutus3000_ss_scan_tuple" = "$nutus3000_ss_identity" ] || return 1
    nutus3000_tuple_is_live "$nutus3000_ss_identity" "$nutus3000_upsd_exe" || return 1
    "$nutus3000_kill" -TERM "$nutus3000_ss_pid" || return 1
    nutus3000_wait_absent "$nutus3000_ss_identity" "$nutus3000_upsd_exe" || return 1
    nutus3000_scan_exact "$nutus3000_upsd_exe" upsd || return 1
    [ "$nutus3000_scan_count" -eq 0 ] || return 1
    nutus3000_remove_server_state
}

nutus3000_stop_driver() {
    nutus3000_load_references driver || return 1
    nutus3000_scan_exact "$nutus3000_driver_exe" usbhid-ups || return 1
    nutus3000_sd_count=$nutus3000_scan_count
    nutus3000_sd_scan_tuple=$nutus3000_scan_tuple
    if [ ! -e "$nutus3000_driver_identity" ] && [ ! -L "$nutus3000_driver_identity" ]; then
        [ "$nutus3000_sd_count" -eq 0 ] || return 1
        if [ -e "$nutus3000_driver_pidfile" ] || [ -L "$nutus3000_driver_pidfile" ]; then
            nutus3000_read_native_pid "$nutus3000_driver_pidfile" >/dev/null || return 1
        fi
        nutus3000_remove_driver_state || return 1
        return 0
    fi
    nutus3000_sd_identity=$(nutus3000_read_identity "$nutus3000_driver_identity" "$nutus3000_driver_exe") || return 1
    nutus3000_sd_pid=${nutus3000_sd_identity%%:*}
    nutus3000_sd_native=$(nutus3000_read_native_pid "$nutus3000_driver_pidfile" 2>/dev/null) || nutus3000_sd_native=
    nutus3000_tuple_is_live "$nutus3000_sd_identity" "$nutus3000_driver_exe"
    nutus3000_sd_live_rc=$?
    if [ "$nutus3000_sd_live_rc" -ne 0 ]; then
        [ "$nutus3000_sd_live_rc" -eq 1 ] || return 1
        nutus3000_scan_exact "$nutus3000_driver_exe" usbhid-ups || return 1
        [ "$nutus3000_scan_count" -eq 0 ] || return 1
        nutus3000_remove_driver_state || return 1
        return 0
    fi
    [ -n "$nutus3000_sd_native" ] && [ "$nutus3000_sd_native" = "$nutus3000_sd_pid" ] || return 1
    [ "$nutus3000_sd_count" -eq 1 ] && [ "$nutus3000_sd_scan_tuple" = "$nutus3000_sd_identity" ] || return 1
    nutus3000_sd_native_again=$(nutus3000_read_native_pid "$nutus3000_driver_pidfile") || return 1
    [ "$nutus3000_sd_native_again" = "$nutus3000_sd_pid" ] || return 1
    nutus3000_tuple_is_live "$nutus3000_sd_identity" "$nutus3000_driver_exe" || return 1
    "$nutus3000_timeout" -k 1 3 "$nutus3000_upsdrvctl_exe" stop ups
    nutus3000_sd_command_rc=$?
    if nutus3000_wait_absent "$nutus3000_sd_identity" "$nutus3000_driver_exe"; then
        nutus3000_scan_exact "$nutus3000_driver_exe" usbhid-ups || return 1
        [ "$nutus3000_scan_count" -eq 0 ] || return 1
        nutus3000_remove_driver_state || return 1
        [ "$nutus3000_sd_command_rc" -eq 0 ]
        return
    fi
    return 1
}

nutus3000_cleanup_attempt() {
    nutus3000_load_references || nutus3000_references_active=0
    nutus3000_scan_exact "$nutus3000_upsdrvctl_exe" upsdrvctl || return 1
    if [ "$nutus3000_scan_count" -eq 1 ]; then
        nutus3000_ca_controller_tuple=$nutus3000_scan_tuple
        nutus3000_ca_controller_pid=${nutus3000_ca_controller_tuple%%:*}
        nutus3000_tuple_is_live "$nutus3000_ca_controller_tuple" "$nutus3000_upsdrvctl_exe" || return 1
        "$nutus3000_kill" -TERM "$nutus3000_ca_controller_pid" || return 1
        nutus3000_wait_absent "$nutus3000_ca_controller_tuple" "$nutus3000_upsdrvctl_exe" || return 1
        nutus3000_scan_exact "$nutus3000_upsdrvctl_exe" upsdrvctl || return 1
        [ "$nutus3000_scan_count" -eq 0 ] || return 1
    elif [ "$nutus3000_scan_count" -gt 1 ]; then
        return 1
    fi

    nutus3000_ca_server_state=0
    if [ -e "$nutus3000_upsd_identity" ] || [ -L "$nutus3000_upsd_identity" ] \
        || [ -e "$nutus3000_upsd_pidfile" ] || [ -L "$nutus3000_upsd_pidfile" ]; then
        nutus3000_ca_server_state=1
    fi
    nutus3000_scan_exact "$nutus3000_upsd_exe" upsd || return 1
    if [ "$nutus3000_scan_count" -eq 1 ]; then
        if [ ! -e "$nutus3000_upsd_identity" ]; then
            nutus3000_publish_identity "$nutus3000_upsd_identity" "$nutus3000_scan_tuple" || return 1
        fi
        nutus3000_ca_server_state=1
    elif [ "$nutus3000_scan_count" -gt 1 ]; then
        return 1
    fi
    if [ "$nutus3000_ca_server_state" -eq 1 ]; then
        nutus3000_stop_server || return 1
    fi

    nutus3000_scan_exact "$nutus3000_driver_exe" usbhid-ups || return 1
    if [ "$nutus3000_scan_count" -eq 1 ]; then
        if [ ! -e "$nutus3000_driver_identity" ]; then
            nutus3000_publish_identity "$nutus3000_driver_identity" "$nutus3000_scan_tuple" || return 1
        fi
    elif [ "$nutus3000_scan_count" -gt 1 ]; then
        return 1
    fi
    nutus3000_stop_driver
}

nutus3000_reconcile_start_state() {
    nutus3000_load_references all || return 1
    nutus3000_scan_exact "$nutus3000_upsd_exe" upsd || return 1
    [ "$nutus3000_scan_count" -eq 0 ] || return 1
    nutus3000_scan_exact "$nutus3000_driver_exe" usbhid-ups || return 1
    [ "$nutus3000_scan_count" -eq 0 ] || return 1
    if [ -e "$nutus3000_upsd_identity" ] || [ -L "$nutus3000_upsd_identity" ]; then
        nutus3000_read_identity "$nutus3000_upsd_identity" "$nutus3000_upsd_exe" >/dev/null || return 1
    fi
    if [ -e "$nutus3000_driver_identity" ] || [ -L "$nutus3000_driver_identity" ]; then
        nutus3000_read_identity "$nutus3000_driver_identity" "$nutus3000_driver_exe" >/dev/null || return 1
    fi
    if [ -e "$nutus3000_upsd_pidfile" ] || [ -L "$nutus3000_upsd_pidfile" ]; then
        nutus3000_read_native_pid "$nutus3000_upsd_pidfile" >/dev/null || return 1
    fi
    if [ -e "$nutus3000_driver_pidfile" ] || [ -L "$nutus3000_driver_pidfile" ]; then
        nutus3000_read_native_pid "$nutus3000_driver_pidfile" >/dev/null || return 1
    fi
    nutus3000_remove_server_state || return 1
    nutus3000_remove_driver_state
}

nutus3000_validate_live_identity() {
    nutus3000_vli_identity_path=$1
    nutus3000_vli_pidfile=$2
    nutus3000_vli_expected=$3
    nutus3000_vli_value=$(nutus3000_read_identity "$nutus3000_vli_identity_path" "$nutus3000_vli_expected") || return 1
    nutus3000_vli_pid=${nutus3000_vli_value%%:*}
    nutus3000_vli_native=$(nutus3000_read_native_pid "$nutus3000_vli_pidfile") || return 1
    [ "$nutus3000_vli_native" = "$nutus3000_vli_pid" ] || return 1
    nutus3000_tuple_is_live "$nutus3000_vli_value" "$nutus3000_vli_expected"
}

nutus3000_health() {
    nutus3000_init || return 1
    nutus3000_alias_is_exact || return 1
    nutus3000_port_is_host_local_exact || return 1
    nutus3000_h_output=$($nutus3000_timeout -k 1 3 "$nutus3000_upsc_exe" ups@127.0.0.1) || return 1
    nutus3000_h_driver=0
    nutus3000_h_driver_value=
    nutus3000_h_mfr=0
    nutus3000_h_mfr_value=
    nutus3000_h_model=0
    nutus3000_h_model_value=
    nutus3000_h_vid=0
    nutus3000_h_vid_value=
    nutus3000_h_pid=0
    nutus3000_h_pid_value=
    nutus3000_h_status=0
    nutus3000_h_status_value=
    while IFS= read -r nutus3000_h_line; do
        case $nutus3000_h_line in
            'driver.name: '*)
                nutus3000_h_driver=$((nutus3000_h_driver + 1))
                nutus3000_h_driver_value=${nutus3000_h_line#driver.name: }
                ;;
            'device.mfr: '*)
                nutus3000_h_mfr=$((nutus3000_h_mfr + 1))
                nutus3000_h_mfr_value=${nutus3000_h_line#device.mfr: }
                ;;
            'device.model: '*)
                nutus3000_h_model=$((nutus3000_h_model + 1))
                nutus3000_h_model_value=${nutus3000_h_line#device.model: }
                ;;
            'ups.vendorid: '*)
                nutus3000_h_vid=$((nutus3000_h_vid + 1))
                nutus3000_h_vid_value=${nutus3000_h_line#ups.vendorid: }
                ;;
            'ups.productid: '*)
                nutus3000_h_pid=$((nutus3000_h_pid + 1))
                nutus3000_h_pid_value=${nutus3000_h_line#ups.productid: }
                ;;
            'ups.status: '*)
                nutus3000_h_status=$((nutus3000_h_status + 1))
                nutus3000_h_status_value=${nutus3000_h_line#ups.status: }
                ;;
        esac
    done <<EOF
$nutus3000_h_output
EOF
    [ "$nutus3000_h_driver" -eq 1 ] || return 1
    [ "$nutus3000_h_driver_value" = nutus3000-hid ] || return 1
    [ "$nutus3000_h_mfr" -eq 1 ] || return 1
    [ "$nutus3000_h_mfr_value" = UGREEN ] || return 1
    [ "$nutus3000_h_model" -eq 1 ] || return 1
    [ "$nutus3000_h_model_value" = US3000 ] || return 1
    [ "$nutus3000_h_vid" -eq 1 ] || return 1
    [ "$nutus3000_h_vid_value" = 2b89 ] || return 1
    [ "$nutus3000_h_pid" -eq 1 ] || return 1
    [ "$nutus3000_h_pid_value" = ffff ] || return 1
    [ "$nutus3000_h_status" -eq 1 ] || return 1
    [ -n "$nutus3000_h_status_value" ] || return 1
    nutus3000_h_status_tokens=0
    for nutus3000_h_token in $nutus3000_h_status_value; do
        nutus3000_h_status_tokens=$((nutus3000_h_status_tokens + 1))
        case $nutus3000_h_token in NOCOMM|STALE) return 1 ;; esac
    done
    [ "$nutus3000_h_status_tokens" -gt 0 ]
}

nutus3000_core_state() {
    nutus3000_init || return 1
    nutus3000_read_effective_ids || return 1
    if [ ! -e "$nutus3000_run" ] && [ ! -L "$nutus3000_run" ]; then
        nutus3000_load_references all || return 1
        nutus3000_scan_exact "$nutus3000_upsd_exe" upsd || return 1
        [ "$nutus3000_scan_count" -eq 0 ] || return 1
        nutus3000_scan_exact "$nutus3000_driver_exe" usbhid-ups || return 1
        [ "$nutus3000_scan_count" -eq 0 ] || return 1
        return 75
    fi
    [ -d "$nutus3000_run" ] && [ ! -L "$nutus3000_run" ] || return 1
    nutus3000_path_is_physical "$nutus3000_run" || return 1
    nutus3000_stat_is "$nutus3000_run" 750 || return 1
    nutus3000_load_references all || return 1

    nutus3000_scan_exact "$nutus3000_driver_exe" usbhid-ups || return 1
    nutus3000_cs_driver_count=$nutus3000_scan_count
    nutus3000_cs_driver_tuple=$nutus3000_scan_tuple
    nutus3000_scan_exact "$nutus3000_upsd_exe" upsd || return 1
    nutus3000_cs_server_count=$nutus3000_scan_count
    nutus3000_cs_server_tuple=$nutus3000_scan_tuple

    if [ "$nutus3000_cs_driver_count:$nutus3000_cs_server_count" = 0:0 ]; then
        return 75
    fi
    case $nutus3000_cs_driver_count:$nutus3000_cs_server_count in
        1:0|1:1) ;;
        *) return 1 ;;
    esac
    nutus3000_validate_live_identity "$nutus3000_driver_identity" "$nutus3000_driver_pidfile" "$nutus3000_driver_exe" || return 1
    nutus3000_cs_identity=$(nutus3000_read_identity "$nutus3000_driver_identity" "$nutus3000_driver_exe") || return 1
    [ "$nutus3000_cs_identity" = "$nutus3000_cs_driver_tuple" ] || return 1
    # DSM can terminate upsd while leaving this exact driver alive. The retry
    # step must use validated stop/release before attempting a fresh start;
    # stop_server still rejects a reused or ambiguous saved server identity.
    [ "$nutus3000_cs_server_count" -ne 0 ] || return 76
    nutus3000_validate_live_identity "$nutus3000_upsd_identity" "$nutus3000_upsd_pidfile" "$nutus3000_upsd_exe" || return 1
    nutus3000_cs_identity=$(nutus3000_read_identity "$nutus3000_upsd_identity" "$nutus3000_upsd_exe") || return 1
    [ "$nutus3000_cs_identity" = "$nutus3000_cs_server_tuple" ]
}

nutus3000_attempt_start() {
    nutus3000_init || return 1
    nutus3000_validate_platform || return 1
    nutus3000_validate_config || return 1
    nutus3000_probe_usb
    nutus3000_as_usb_rc=$?
    [ "$nutus3000_as_usb_rc" -ne 75 ] || return 75
    [ "$nutus3000_as_usb_rc" -eq 0 ] || return 1
    nutus3000_alias_is_exact || return 1
    nutus3000_preflight_no_foreign 1 || return 1
    nutus3000_port_is_free || return 1
    nutus3000_prepare_run || return 1
    nutus3000_reconcile_start_state || return 1

    "$nutus3000_timeout" -k 1 3 "$nutus3000_upsdrvctl_exe" start
    nutus3000_start_rc=$?
    if [ "$nutus3000_start_rc" -ne 0 ]; then
        nutus3000_cleanup_attempt >/dev/null 2>&1 || return 1
        return 75
    fi
    if ! nutus3000_capture_identity driver; then
        nutus3000_cleanup_attempt >/dev/null 2>&1 || return 1
        return 75
    fi

    "$nutus3000_timeout" -k 1 3 "$nutus3000_upsd_exe"
    nutus3000_start_rc=$?
    if [ "$nutus3000_start_rc" -ne 0 ]; then
        nutus3000_cleanup_attempt >/dev/null 2>&1 || return 1
        return 75
    fi
    if ! nutus3000_capture_identity server; then
        nutus3000_cleanup_attempt >/dev/null 2>&1 || return 1
        return 75
    fi

    nutus3000_start_attempt=1
    while [ "$nutus3000_start_attempt" -le 6 ]; do
        if "$nutus3000_health_exe"; then
            return 0
        fi
        [ "$nutus3000_start_attempt" -eq 6 ] || "$nutus3000_sleep" 2 || break
        nutus3000_start_attempt=$((nutus3000_start_attempt + 1))
    done
    nutus3000_cleanup_attempt >/dev/null 2>&1 || return 1
    return 75
}

nutus3000_start() {
    nutus3000_attempt_start
    [ $? -eq 0 ]
}

nutus3000_read_controller_state() {
    nutus3000_init || return 1
    [ -e "$nutus3000_controller_state" ] || [ -L "$nutus3000_controller_state" ] || return 75
    [ -f "$nutus3000_controller_state" ] && [ ! -L "$nutus3000_controller_state" ] || return 1
    nutus3000_read_effective_ids || return 1
    nutus3000_stat_is "$nutus3000_controller_state" 600 || return 1
    nutus3000_rcs_value=$(nutus3000_read_one_line "$nutus3000_controller_state") || return 1
    case $nutus3000_rcs_value in HEALTHY|DEGRADED_1|UNAVAILABLE) ;; *) return 1 ;; esac
    printf '%s\n' "$nutus3000_rcs_value"
}

nutus3000_publish_controller_state() {
    case ${1-} in HEALTHY|DEGRADED_1|UNAVAILABLE) ;; *) return 1 ;; esac
    nutus3000_pcs_value=$1
    nutus3000_init || return 1
    nutus3000_prepare_run || return 1
    nutus3000_read_controller_state >/dev/null 2>&1
    nutus3000_pcs_existing_rc=$?
    [ "$nutus3000_pcs_existing_rc" -eq 0 ] || [ "$nutus3000_pcs_existing_rc" -eq 75 ] || return 1
    nutus3000_pcs_tmp=$nutus3000_run/.controller-health.state.$$
    [ ! -e "$nutus3000_pcs_tmp" ] && [ ! -L "$nutus3000_pcs_tmp" ] || return 1
    (umask 077 && set -C && printf '%s\n' "$nutus3000_pcs_value" > "$nutus3000_pcs_tmp") || return 1
    chmod 600 "$nutus3000_pcs_tmp" || { rm -f "$nutus3000_pcs_tmp"; return 1; }
    nutus3000_stat_is "$nutus3000_pcs_tmp" 600 || { rm -f "$nutus3000_pcs_tmp"; return 1; }
    nutus3000_read_controller_state >/dev/null 2>&1
    nutus3000_pcs_existing_rc=$?
    [ "$nutus3000_pcs_existing_rc" -eq 0 ] || [ "$nutus3000_pcs_existing_rc" -eq 75 ] \
        || { rm -f "$nutus3000_pcs_tmp"; return 1; }
    "$nutus3000_mv" -f "$nutus3000_pcs_tmp" "$nutus3000_controller_state" || {
        rm -f "$nutus3000_pcs_tmp"
        return 1
    }
    nutus3000_read_controller_state >/dev/null
}

nutus3000_controller_status() {
    nutus3000_init || return 1
    nutus3000_validate_platform || return 1
    nutus3000_read_effective_ids || return 1
    [ -d "$nutus3000_run" ] && [ ! -L "$nutus3000_run" ] || return 1
    nutus3000_path_is_physical "$nutus3000_run" || return 1
    nutus3000_stat_is "$nutus3000_run" 750 || return 1
    nutus3000_load_references controller || return 1
    nutus3000_cs_identity=$(nutus3000_read_identity "$nutus3000_controller_identity" "$nutus3000_controller_exe") || return 1
    nutus3000_scan_exact "$nutus3000_controller_exe" nut-us3000-cont || return 1
    [ "$nutus3000_scan_count" -eq 1 ] && [ "$nutus3000_scan_tuple" = "$nutus3000_cs_identity" ] || return 1
    nutus3000_tuple_is_live "$nutus3000_cs_identity" "$nutus3000_controller_exe" || return 1
    nutus3000_read_controller_state >/dev/null 2>&1
    nutus3000_cs_state_rc=$?
    [ "$nutus3000_cs_state_rc" -eq 0 ] || [ "$nutus3000_cs_state_rc" -eq 75 ]
}

nutus3000_status() {
    nutus3000_controller_status
}

nutus3000_controller_start() {
    nutus3000_cstart_delay=${1-}
    nutus3000_is_decimal "$nutus3000_cstart_delay" || return 1
    [ "$nutus3000_cstart_delay" -le 600 ] || return 1
    nutus3000_init || return 1
    [ -f "$nutus3000_controller_exe" ] && [ ! -L "$nutus3000_controller_exe" ] \
        && [ -x "$nutus3000_controller_exe" ] || return 1
    nutus3000_prepare_run || return 1
    [ ! -e "$nutus3000_controller_identity" ] && [ ! -L "$nutus3000_controller_identity" ] || return 1
    nutus3000_load_references controller || return 1
    nutus3000_scan_exact "$nutus3000_controller_exe" nut-us3000-cont || return 1
    [ "$nutus3000_scan_count" -eq 0 ] || return 1
    "$nutus3000_controller_exe" --first-delay "$nutus3000_cstart_delay" >/dev/null 2>&1 &
    nutus3000_cstart_attempt=0
    while [ "$nutus3000_cstart_attempt" -lt 6 ]; do
        "$nutus3000_sleep" 1 || return 1
        nutus3000_scan_exact "$nutus3000_controller_exe" nut-us3000-cont || return 1
        if [ "$nutus3000_scan_count" -eq 1 ]; then
            nutus3000_publish_identity "$nutus3000_controller_identity" "$nutus3000_scan_tuple" || return 1
            nutus3000_controller_status
            return
        fi
        [ "$nutus3000_scan_count" -eq 0 ] || return 1
        nutus3000_cstart_attempt=$((nutus3000_cstart_attempt + 1))
    done
    return 1
}

nutus3000_wait_controller_absent() {
    nutus3000_wca_tuple=$1
    nutus3000_wca_count=0
    while [ "$nutus3000_wca_count" -lt 30 ]; do
        nutus3000_tuple_is_live "$nutus3000_wca_tuple" "$nutus3000_controller_exe"
        nutus3000_wca_rc=$?
        [ "$nutus3000_wca_rc" -eq 1 ] && return 0
        [ "$nutus3000_wca_rc" -eq 0 ] || return 1
        "$nutus3000_sleep" 1 || return 1
        nutus3000_wca_count=$((nutus3000_wca_count + 1))
    done
    return 1
}

nutus3000_controller_stop() {
    nutus3000_init || return 1
    nutus3000_read_effective_ids || return 1
    if [ ! -e "$nutus3000_run" ] && [ ! -L "$nutus3000_run" ]; then
        nutus3000_load_references controller || return 1
        nutus3000_scan_exact "$nutus3000_controller_exe" nut-us3000-cont || return 1
        [ "$nutus3000_scan_count" -eq 0 ]
        return
    fi
    [ -d "$nutus3000_run" ] && [ ! -L "$nutus3000_run" ] || return 1
    nutus3000_path_is_physical "$nutus3000_run" || return 1
    nutus3000_stat_is "$nutus3000_run" 750 || return 1
    nutus3000_load_references controller || return 1
    nutus3000_scan_exact "$nutus3000_controller_exe" nut-us3000-cont || return 1
    nutus3000_cstop_count=$nutus3000_scan_count
    nutus3000_cstop_scan_tuple=$nutus3000_scan_tuple
    if [ ! -e "$nutus3000_controller_identity" ] && [ ! -L "$nutus3000_controller_identity" ]; then
        [ "$nutus3000_cstop_count" -eq 0 ] || return 1
        rm -f "$nutus3000_controller_state"
        return
    fi
    nutus3000_cstop_identity=$(nutus3000_read_identity "$nutus3000_controller_identity" "$nutus3000_controller_exe") || return 1
    nutus3000_tuple_is_live "$nutus3000_cstop_identity" "$nutus3000_controller_exe"
    nutus3000_cstop_live_rc=$?
    if [ "$nutus3000_cstop_live_rc" -eq 1 ]; then
        nutus3000_scan_exact "$nutus3000_controller_exe" nut-us3000-cont || return 1
        [ "$nutus3000_scan_count" -eq 0 ] || return 1
        rm -f "$nutus3000_controller_identity" "$nutus3000_controller_state"
        return
    fi
    [ "$nutus3000_cstop_live_rc" -eq 0 ] || return 1
    [ "$nutus3000_cstop_count" -eq 1 ] && [ "$nutus3000_cstop_scan_tuple" = "$nutus3000_cstop_identity" ] || return 1
    nutus3000_cstop_pid=${nutus3000_cstop_identity%%:*}
    nutus3000_tuple_is_live "$nutus3000_cstop_identity" "$nutus3000_controller_exe" || return 1
    "$nutus3000_kill" -TERM "$nutus3000_cstop_pid" || return 1
    nutus3000_wait_controller_absent "$nutus3000_cstop_identity" || return 1
    nutus3000_scan_exact "$nutus3000_controller_exe" nut-us3000-cont || return 1
    [ "$nutus3000_scan_count" -eq 0 ] || return 1
    rm -f "$nutus3000_controller_identity" "$nutus3000_controller_state"
}

nutus3000_initial_preflight() {
    nutus3000_init || return 1
    nutus3000_validate_platform || return 1
    nutus3000_validate_config || return 1
    nutus3000_probe_usb
    nutus3000_ipf_usb_rc=$?
    [ "$nutus3000_ipf_usb_rc" -eq 0 ] || [ "$nutus3000_ipf_usb_rc" -eq 75 ] || return 1
    nutus3000_preflight_no_foreign 0 || return 1
    nutus3000_port_is_free || return 1
    nutus3000_prepare_run || return 1
    nutus3000_reconcile_start_state
}

nutus3000_first_delay_after_unavailable() {
    nutus3000_init || return 1
    nutus3000_fd_line=$(nutus3000_read_one_line "$nutus3000_uptime") || return 1
    case $nutus3000_fd_line in *' '*) nutus3000_fd_first=${nutus3000_fd_line%% *} ;; *) return 1 ;; esac
    case $nutus3000_fd_first in
        *.*)
            nutus3000_fd_seconds=${nutus3000_fd_first%%.*}
            nutus3000_fd_fraction=${nutus3000_fd_first#*.}
            ;;
        *) return 1 ;;
    esac
    nutus3000_is_decimal "$nutus3000_fd_seconds" || return 1
    nutus3000_is_decimal "$nutus3000_fd_fraction" || return 1
    case $nutus3000_fd_seconds in 0|[1-9][0-9]*) ;; *) return 1 ;; esac
    if [ "$nutus3000_fd_seconds" -lt 600 ]; then
        printf '%s\n' $((600 - nutus3000_fd_seconds))
    else
        printf '0\n'
    fi
}

nutus3000_stop() {
    nutus3000_init || return 1
    nutus3000_read_effective_ids || return 1
    if [ ! -e "$nutus3000_run" ] && [ ! -L "$nutus3000_run" ]; then
        nutus3000_scan_exact "$nutus3000_upsd_exe" upsd || return 1
        [ "$nutus3000_scan_count" -eq 0 ] || return 1
        nutus3000_scan_exact "$nutus3000_driver_exe" usbhid-ups || return 1
        [ "$nutus3000_scan_count" -eq 0 ] || return 1
        return 0
    fi
    [ -d "$nutus3000_run" ] && [ ! -L "$nutus3000_run" ] || return 1
    nutus3000_path_is_physical "$nutus3000_run" || return 1
    nutus3000_stat_is "$nutus3000_run" 750 || return 1
    nutus3000_stop_server || return 1
    nutus3000_stop_driver || return 1
    return 0
}
