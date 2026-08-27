#!/bin/sh
set -eu

NUT_URL=https://networkupstools.org/source/2.8/nut-2.8.5.tar.gz
NUT_SIGNATURE_URL=https://networkupstools.org/source/2.8/nut-2.8.5.tar.gz.sig
LIBUSB_URL=https://github.com/libusb/libusb/releases/download/v1.0.29/libusb-1.0.29.tar.bz2
NUT_NAME=nut-2.8.5.tar.gz
SIGNATURE_NAME=nut-2.8.5.tar.gz.sig
LIBUSB_NAME=libusb-1.0.29.tar.bz2

fail() {
    printf '%s\n' "ERROR: $*" >&2
    exit 1
}

hash_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        line=$(sha256sum "$1") || return 1
    elif command -v shasum >/dev/null 2>&1; then
        line=$(shasum -a 256 "$1") || return 1
    else
        return 1
    fi
    digest=${line%% *}
    case "$digest" in ''|*[!0-9a-f]*) return 1 ;; esac
    [ "${#digest}" -eq 64 ] || return 1
    printf '%s\n' "$digest"
}

manifest_digest() {
    relative=$1
    matches=$(awk -v wanted="$relative" '$2 == wanted {print $1}' "$manifest") || return 1
    [ "$(printf '%s\n' "$matches" | awk 'NF {count++} END {print count+0}')" -eq 1 ] || return 1
    case "$matches" in ''|*[!0-9a-f]*) return 1 ;; esac
    [ "${#matches}" -eq 64 ] || return 1
    printf '%s\n' "$matches"
}

safe_existing_target() {
    target=$1
    expected=$2
    if [ -e "$target" ] || [ -L "$target" ]; then
        [ -f "$target" ] && [ ! -L "$target" ] || fail "source target is unsafe: $target"
        [ "$(hash_file "$target")" = "$expected" ] || fail "existing source hash mismatch: $target"
    fi
}

[ "$#" -eq 1 ] || exit 64
artifacts=$1
case "$artifacts" in /*) ;; *) exit 64 ;; esac
case "$artifacts" in *'\n'*|*'\r'*) exit 64 ;; esac

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) || exit 64
project_root=$(CDPATH= cd -- "$script_dir/../.." && pwd -P) || exit 64
manifest=$project_root/spk/sources/source-manifest.sha256
signature=$project_root/spk/sources/$SIGNATURE_NAME
keyring=$project_root/spk/sources/nut-key.gpg
[ -f "$manifest" ] && [ ! -L "$manifest" ] || fail 'source manifest is unavailable'
[ -f "$signature" ] && [ ! -L "$signature" ] || fail 'NUT signature is unavailable'
[ -f "$keyring" ] && [ ! -L "$keyring" ] || fail 'NUT keyring is unavailable'

[ "$NUT_URL" = "https://networkupstools.org/source/2.8/$NUT_NAME" ] || fail 'NUT URL lock mismatch'
[ "$NUT_SIGNATURE_URL" = "https://networkupstools.org/source/2.8/$SIGNATURE_NAME" ] || fail 'NUT signature URL lock mismatch'
[ "$LIBUSB_URL" = "https://github.com/libusb/libusb/releases/download/v1.0.29/$LIBUSB_NAME" ] || fail 'libusb URL lock mismatch'

line_count=$(awk 'END {print NR+0}' "$manifest")
[ "$line_count" -eq 4 ] || fail 'source manifest entry count mismatch'
nut_hash=$(manifest_digest "artifacts/$NUT_NAME") || fail 'NUT manifest entry mismatch'
signature_hash=$(manifest_digest "spk/sources/$SIGNATURE_NAME") || fail 'signature manifest entry mismatch'
key_hash=$(manifest_digest 'spk/sources/nut-key.gpg') || fail 'key manifest entry mismatch'
libusb_hash=$(manifest_digest "artifacts/$LIBUSB_NAME") || fail 'libusb manifest entry mismatch'
[ "$(hash_file "$signature")" = "$signature_hash" ] || fail 'bundled signature hash mismatch'
[ "$(hash_file "$keyring")" = "$key_hash" ] || fail 'bundled keyring hash mismatch'

if [ -e "$artifacts" ] || [ -L "$artifacts" ]; then
    [ -d "$artifacts" ] && [ ! -L "$artifacts" ] || fail 'artifact directory is unsafe'
else
    mkdir -p "$artifacts"
fi
artifacts=$(CDPATH= cd -- "$artifacts" && pwd -P) || exit 64
safe_existing_target "$artifacts/$NUT_NAME" "$nut_hash"
safe_existing_target "$artifacts/$LIBUSB_NAME" "$libusb_hash"

attempt=$(mktemp -d "$artifacts/.source-fetch.XXXXXX") || fail 'cannot create source fetch attempt'
cleanup() {
    status=$?
    trap - 0 HUP INT TERM
    rm -rf "$attempt"
    exit "$status"
}
trap cleanup 0 HUP INT TERM

curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
    --output "$attempt/$NUT_NAME" "$NUT_URL"
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
    --output "$attempt/$SIGNATURE_NAME" "$NUT_SIGNATURE_URL"
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
    --output "$attempt/$LIBUSB_NAME" "$LIBUSB_URL"

[ "$(hash_file "$attempt/$NUT_NAME")" = "$nut_hash" ] || fail 'downloaded NUT hash mismatch'
[ "$(hash_file "$attempt/$SIGNATURE_NAME")" = "$signature_hash" ] || fail 'downloaded signature hash mismatch'
[ "$(hash_file "$attempt/$LIBUSB_NAME")" = "$libusb_hash" ] || fail 'downloaded libusb hash mismatch'
cmp -s "$attempt/$SIGNATURE_NAME" "$signature" || fail 'downloaded signature differs from bundled evidence'
dearmored_keyring=$attempt/nut-keyring.gpg
gpg --batch --yes --dearmor --output "$dearmored_keyring" "$keyring" >/dev/null 2>&1 || \
    fail 'NUT key dearmor failed'
[ -f "$dearmored_keyring" ] && [ ! -L "$dearmored_keyring" ] || fail 'NUT keyring conversion is unsafe'
chmod 600 "$dearmored_keyring"
gpgv --keyring "$dearmored_keyring" "$attempt/$SIGNATURE_NAME" "$attempt/$NUT_NAME" >/dev/null 2>&1 || \
    fail 'NUT detached signature verification failed'

for name in "$NUT_NAME" "$LIBUSB_NAME"; do
    target=$artifacts/$name
    if [ ! -e "$target" ] && [ ! -L "$target" ]; then
        mv "$attempt/$name" "$target"
        chmod 644 "$target"
    fi
done

printf '%s\n' "SOURCE_FETCH_COMPLETE $artifacts"
