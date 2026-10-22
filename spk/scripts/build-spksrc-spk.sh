#!/bin/sh
set -eu

CP=/bin/cp
GIT=/usr/bin/git
MAKE=/usr/bin/make
MKDIR=/bin/mkdir
MKTEMP=/usr/bin/mktemp
PYTHON=/usr/bin/python3
RM=/bin/rm

fail() {
    printf '%s\n' "ERROR: $*" >&2
    exit 1
}

canonical_directory() {
    [ -d "$1" ] && [ ! -L "$1" ] || return 1
    canonical=$(CDPATH= cd -- "$1" && pwd -P) || return 1
    [ "$canonical" = "$1" ]
}

hash_file() {
    if [ -x /usr/bin/sha256sum ]; then
        hash_line=$(/usr/bin/sha256sum "$1") || return 1
    elif [ -x /usr/bin/shasum ]; then
        hash_line=$(/usr/bin/shasum -a 256 "$1") || return 1
    else
        return 1
    fi
    hash_value=${hash_line%% *}
    case "$hash_value" in ''|*[!0-9a-f]*) return 1 ;; esac
    [ "${#hash_value}" -eq 64 ] || return 1
    printf '%s\n' "$hash_value"
}

[ "$#" -eq 3 ] || exit 64
project_root=$1
spksrc_root=$2
output_dir=$3

case "$project_root:$spksrc_root:$output_dir" in
    *'\n'*|*'\r'*) exit 64 ;;
esac
case "$project_root" in /*) ;; *) exit 64 ;; esac
case "$spksrc_root" in /*) ;; *) exit 64 ;; esac
case "$output_dir" in /*) ;; *) exit 64 ;; esac
canonical_directory "$project_root" || exit 64
canonical_directory "$spksrc_root" || exit 64
canonical_directory "$output_dir" || exit 64
[ -f "$spksrc_root/mk/spksrc.spk.mk" ] && [ ! -L "$spksrc_root/mk/spksrc.spk.mk" ] || \
    fail 'spksrc root is incomplete'
toolchain_recipe=$spksrc_root/toolchain/syno-epyc7002-7.2
[ -f "$toolchain_recipe/Makefile" ] && [ ! -L "$toolchain_recipe/Makefile" ] || \
    fail 'epyc7002-7.2 toolchain recipe is unavailable'

lock=$project_root/spk/sources/spksrc.lock
[ -f "$lock" ] && [ ! -L "$lock" ] || fail 'spksrc lock is unavailable'
{
    IFS= read -r lock_url
    IFS= read -r lock_commit
    IFS= read -r lock_platform
    IFS= read -r lock_image
    if IFS= read -r lock_extra; then exit 1; fi
} < "$lock" || fail 'spksrc lock is malformed'
[ "$lock_url" = 'SPKSRC_URL=https://github.com/SynoCommunity/spksrc.git' ] || fail 'spksrc URL lock mismatch'
[ "$lock_commit" = 'SPKSRC_COMMIT=5c3cc7da1d4221d7e081ed2a31ba820b0455d4de' ] || fail 'spksrc commit lock mismatch'
[ "$lock_platform" = 'BUILDER_PLATFORM=linux/amd64' ] || fail 'builder platform lock mismatch'
[ "$lock_image" = 'BUILDER_IMAGE=ghcr.io/synocommunity/spksrc@sha256:deeef1a01210c914c43a7c18a40aee62885eeee041cc70e7bd1907153561cc94' ] || \
    fail 'builder image lock mismatch'

actual_commit=$($GIT -C "$spksrc_root" rev-parse HEAD) || fail 'cannot identify spksrc commit'
[ "$actual_commit" = 5c3cc7da1d4221d7e081ed2a31ba820b0455d4de ] || fail 'spksrc checkout does not match lock'

overlay=$project_root/spk/spksrc-overlay
for relative in cross/nut/Makefile cross/nut/digests cross/nut/PLIST \
    spk/nut-us3000/Makefile; do
    [ -f "$overlay/$relative" ] && [ ! -L "$overlay/$relative" ] || fail "overlay input is unavailable: $relative"
done
for target in "$spksrc_root/cross/nut" "$spksrc_root/spk/nut-us3000"; do
    [ ! -e "$target" ] && [ ! -L "$target" ] || fail "spksrc overlay target already exists: $target"
done

manifest=$project_root/spk/sources/source-manifest.sha256
nut_artifact=$project_root/artifacts/nut-2.8.5.tar.gz
libusb_artifact=$project_root/artifacts/libusb-1.0.29.tar.bz2
signature=$project_root/spk/sources/nut-2.8.5.tar.gz.sig
keyring=$project_root/spk/sources/nut-key.gpg
for source in "$manifest" "$nut_artifact" "$libusb_artifact" "$signature" "$keyring"; do
    [ -f "$source" ] && [ ! -L "$source" ] || fail "verified source evidence is unavailable: $source"
done
[ "$(hash_file "$nut_artifact")" = 18bf32e59eb764b13da3c4fa70384926d7fa584cb31d2fe7f137a570633eeec1 ] || \
    fail 'NUT source archive hash mismatch'
[ "$(hash_file "$libusb_artifact")" = 5977fc950f8d1395ccea9bd48c06b3f808fd3c2c961b44b0c2e6e29fc3a70a85 ] || \
    fail 'libusb source archive hash mismatch'
[ "$(hash_file "$signature")" = 3211f48f7a312ae13770828d768a5e4d95c6866bfd96bf79df44665c8e6c85fb ] || \
    fail 'NUT signature hash mismatch'
[ "$(hash_file "$keyring")" = c12ead62f833ad128266c1a812d0b487a62929adf1e28859a2783c8dc1c7f2a0 ] || \
    fail 'NUT keyring hash mismatch'
[ "$(/usr/bin/awk 'END {print NR+0}' "$manifest")" -eq 4 ] || fail 'source manifest entry count mismatch'
/usr/bin/grep -Fx '18bf32e59eb764b13da3c4fa70384926d7fa584cb31d2fe7f137a570633eeec1  artifacts/nut-2.8.5.tar.gz' "$manifest" >/dev/null || \
    fail 'NUT source manifest mismatch'
/usr/bin/grep -Fx '3211f48f7a312ae13770828d768a5e4d95c6866bfd96bf79df44665c8e6c85fb  spk/sources/nut-2.8.5.tar.gz.sig' "$manifest" >/dev/null || \
    fail 'NUT signature manifest mismatch'
/usr/bin/grep -Fx 'c12ead62f833ad128266c1a812d0b487a62929adf1e28859a2783c8dc1c7f2a0  spk/sources/nut-key.gpg' "$manifest" >/dev/null || \
    fail 'NUT keyring manifest mismatch'
/usr/bin/grep -Fx '5977fc950f8d1395ccea9bd48c06b3f808fd3c2c961b44b0c2e6e29fc3a70a85  artifacts/libusb-1.0.29.tar.bz2' "$manifest" >/dev/null || \
    fail 'libusb source manifest mismatch'

"$MKDIR" -p "$spksrc_root/cross" "$spksrc_root/spk" "$spksrc_root/distrib"
"$CP" -R "$overlay/cross/nut" "$spksrc_root/cross/nut"
"$CP" -R "$overlay/spk/nut-us3000" "$spksrc_root/spk/nut-us3000"

recipe_source=$spksrc_root/spk/nut-us3000/src
"$MKDIR" -p "$recipe_source/hooks" "$recipe_source/conf" "$recipe_source/native" \
    "$recipe_source/wizard" \
    "$recipe_source/payload/share/nut-us3000" "$recipe_source/templates" \
    "$recipe_source/payload/app/help/enu" "$recipe_source/payload/app/help/rus" \
    "$recipe_source/payload/app/texts/enu" "$recipe_source/payload/app/texts/rus"
for name in preinst postinst preuninst postuninst preupgrade postupgrade; do
    "$CP" "$project_root/spk/package/scripts/$name" "$recipe_source/hooks/$name"
    /bin/chmod 755 "$recipe_source/hooks/$name"
done
"$CP" "$project_root/spk/package/scripts/start-stop-status" "$recipe_source/start-stop-status"
"$CP" "$project_root/spk/package/conf/privilege" "$recipe_source/conf/privilege"
"$CP" "$project_root/spk/package/native/nut-us3000-controller.c" "$recipe_source/native/nut-us3000-controller.c"
"$CP" "$project_root/spk/package/native/nut-us3000-hostctl.c" "$recipe_source/native/nut-us3000-hostctl.c"
for name in ram-hostctl.c ram-bridge.c ram-bridge.h ram-exec.c ram-exec.h \
    ram-runtime.c ram-runtime.h ram-platform.c ram-files.c; do
    "$CP" "$project_root/spk/package/native/$name" "$recipe_source/native/$name"
done
"$PYTHON" "$project_root/spk/package/native/embed_ram_payload.py" > "$recipe_source/native/ram-payload.h"
for name in install_uifile install_uifile_rus upgrade_uifile upgrade_uifile_rus \
    uninstall_uifile uninstall_uifile_rus; do
    "$CP" "$project_root/spk/package/wizard/$name" "$recipe_source/wizard/$name"
done
"$CP" "$project_root/spk/package/payload/share/nut-us3000/lib.sh" "$recipe_source/payload/share/nut-us3000/lib.sh"
"$CP" "$project_root/spk/package/payload/share/nut-us3000/healthcheck.sh" "$recipe_source/payload/share/nut-us3000/healthcheck.sh"
"$CP" "$project_root/spk/package/payload/share/nut-us3000/retry-step.sh" "$recipe_source/payload/share/nut-us3000/retry-step.sh"
"$CP" "$project_root/spk/package/payload/app/helptoc.conf" "$recipe_source/payload/app/helptoc.conf"
"$CP" "$project_root/spk/package/payload/app/config" "$recipe_source/payload/app/config"
"$CP" "$project_root/spk/package/payload/app/index.html" "$recipe_source/payload/app/index.html"
"$CP" "$project_root/spk/package/payload/app/help/enu/nut-us3000.html" "$recipe_source/payload/app/help/enu/nut-us3000.html"
"$CP" "$project_root/spk/package/payload/app/help/rus/nut-us3000.html" "$recipe_source/payload/app/help/rus/nut-us3000.html"
"$CP" "$project_root/spk/package/payload/app/texts/enu/strings" "$recipe_source/payload/app/texts/enu/strings"
"$CP" "$project_root/spk/package/payload/app/texts/rus/strings" "$recipe_source/payload/app/texts/rus/strings"
"$CP" "$project_root/spk/package/templates/ups.conf" "$recipe_source/templates/ups.conf"
"$CP" "$project_root/spk/package/templates/upsd.conf" "$recipe_source/templates/upsd.conf"
/bin/chmod 755 "$recipe_source/start-stop-status" "$recipe_source/payload/share/nut-us3000/lib.sh" \
    "$recipe_source/payload/share/nut-us3000/healthcheck.sh" \
    "$recipe_source/payload/share/nut-us3000/retry-step.sh"
/bin/chmod 644 "$recipe_source/conf/privilege" "$recipe_source/native/nut-us3000-controller.c" \
    "$recipe_source/native/nut-us3000-hostctl.c" \
    "$recipe_source/wizard"/* \
    "$recipe_source/templates/ups.conf" "$recipe_source/templates/upsd.conf" \
    "$recipe_source/payload/app/helptoc.conf" \
    "$recipe_source/payload/app/config" \
    "$recipe_source/payload/app/index.html" \
    "$recipe_source/payload/app/help/enu/nut-us3000.html" \
    "$recipe_source/payload/app/help/rus/nut-us3000.html" \
    "$recipe_source/payload/app/texts/enu/strings" \
    "$recipe_source/payload/app/texts/rus/strings"

attempt=$($MKTEMP -d "$output_dir/.nut-us3000-spksrc-build.XXXXXX") || fail 'cannot create build attempt'
cleanup() {
    status=$?
    trap - 0 HUP INT TERM
    "$RM" -rf "$attempt" || :
    exit "$status"
}
trap cleanup 0 HUP INT TERM
"$PYTHON" "$project_root/spk/scripts/generate-icons.py" "$attempt/icons" || fail 'icon generation failed'
"$CP" "$attempt/icons/PACKAGE_ICON_256.PNG" "$recipe_source/icon-256.png"
/bin/chmod 644 "$recipe_source/icon-256.png"

for source_spec in \
    "$nut_artifact|nut-2.8.5.tar.gz|18bf32e59eb764b13da3c4fa70384926d7fa584cb31d2fe7f137a570633eeec1" \
    "$libusb_artifact|libusb-1.0.29.tar.bz2|5977fc950f8d1395ccea9bd48c06b3f808fd3c2c961b44b0c2e6e29fc3a70a85"
do
    source=${source_spec%%|*}
    remainder=${source_spec#*|}
    name=${remainder%%|*}
    expected=${remainder#*|}
    dist_archive=$spksrc_root/distrib/$name
    if [ -e "$dist_archive" ] || [ -L "$dist_archive" ]; then
        [ -f "$dist_archive" ] && [ ! -L "$dist_archive" ] || fail 'spksrc source cache target is unsafe'
        [ "$(hash_file "$dist_archive")" = "$expected" ] || \
            fail "spksrc source cache conflicts with verified source: $name"
    else
        "$CP" "$source" "$dist_archive"
        /bin/chmod 644 "$dist_archive"
    fi
done

"$MAKE" -C "$toolchain_recipe" toolchain >&2 || \
    fail 'spksrc toolchain bootstrap failed'
"$MAKE" -C "$spksrc_root/spk/nut-us3000" ARCH=epyc7002 TCVERSION=7.2 package >&2 || \
    fail 'spksrc package build failed'

spk_name=nut-us3000_epyc7002-7.2_2.8.5-0026.spk
built_spk=$spksrc_root/packages/$spk_name
[ -f "$built_spk" ] && [ ! -L "$built_spk" ] || fail 'expected spksrc package was not produced'
final_spk=$output_dir/$spk_name
[ ! -e "$final_spk" ] && [ ! -L "$final_spk" ] || fail 'SPK publication target already exists'
published_stage=$attempt/$spk_name
"$CP" "$built_spk" "$published_stage"
/bin/chmod 644 "$published_stage"
/bin/ln "$published_stage" "$final_spk" || fail 'SPK publication failed'

printf '%s\n' "SPKSRC_SPK_COMPLETE $spk_name"
