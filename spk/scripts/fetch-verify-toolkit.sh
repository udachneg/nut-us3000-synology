#!/bin/sh
set -eu

fail() {
    printf '%s\n' "$1" >&2
    exit 1
}

mode_is_0600() {
    mode_line=$(LC_ALL=C ls -ld "$1") || return 1
    case "$mode_line" in
        -rw-------*) return 0 ;;
        *) return 1 ;;
    esac
}

[ "$#" -eq 1 ] || exit 64
cache_dir=$1
case "/$cache_dir/" in
    *'/../'*|*'/./'*) exit 64 ;;
esac
umask 077

[ -L "$cache_dir" ] && exit 64
if [ ! -e "$cache_dir" ]; then
    mkdir -p "$cache_dir"
fi
[ -d "$cache_dir" ] || exit 64

for target in "$cache_dir/verified" "$cache_dir/SHA256SUMS" "$cache_dir/PROVENANCE.txt"; do
    [ -L "$target" ] && exit 64
done

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
lock_file=$script_dir/../sources/synology-toolkit.md5
[ -f "$lock_file" ] || fail "publisher lock is missing"

tmp=$(mktemp -d "$cache_dir/.fetch-verify-toolkit.XXXXXX") || exit 1
created_sha=0
created_provenance=0
created_verified=0
cleanup() {
    status=$?
    if [ "$status" -ne 0 ]; then
        [ "$created_verified" -eq 0 ] || rm -rf "$cache_dir/verified" || :
        [ "$created_provenance" -eq 0 ] || rm -f "$cache_dir/PROVENANCE.txt" || :
        [ "$created_sha" -eq 0 ] || rm -f "$cache_dir/SHA256SUMS" || :
    fi
    rm -rf "$tmp" || :
    trap - 0
    exit "$status"
}
trap cleanup 0
seen=$tmp/seen
sha_lock=$tmp/SHA256SUMS
provenance=$tmp/PROVENANCE.txt
stage=$tmp/verified
: > "$seen"
: > "$sha_lock"
mkdir "$stage"
printf '%s\n' 'PUBLISHER=Synology' > "$provenance"

count=0
while IFS=' ' read -r publisher_md5 name url extra || [ -n "${publisher_md5}${name}${url}${extra}" ]; do
    [ -n "$publisher_md5" ] && [ -n "$name" ] && [ -n "$url" ] && [ -z "$extra" ] || fail "invalid publisher lock record"
    case "$publisher_md5" in
        *[!0-9a-f]*|'') fail "invalid publisher md5" ;;
    esac
    [ "${#publisher_md5}" -eq 32 ] || fail "invalid publisher md5"
    case "$name" in
        base_env-7.2.txz|ds.epyc7002-7.2.dev.txz|ds.epyc7002-7.2.env.txz|epyc7002-gcc1220_glibc236_x86_64-GPL.txz) ;;
        *) fail "unexpected archive basename" ;;
    esac
    if grep -F -x -- "$name" "$seen" >/dev/null 2>&1; then
        fail "duplicate archive basename"
    fi
    printf '%s\n' "$name" >> "$seen"
    case "$url" in
        https://global.synologydownload.com/*) ;;
        *) fail "untrusted download URL" ;;
    esac
    [ "${url##*/}" = "$name" ] || fail "URL basename mismatch"

    download=$tmp/$name
    curl --fail --proto '=https' --tlsv1.2 --output "$download" "$url"
    if command -v md5sum >/dev/null 2>&1; then
        md5_line=$(md5sum "$download")
        actual_md5=${md5_line%% *}
        [ "$md5_line" = "$actual_md5  $download" ] || fail "invalid downloaded md5"
    else
        actual_md5=$(md5 -q "$download")
    fi
    case "$actual_md5" in
        *[!0-9a-f]*|'') fail "invalid downloaded md5" ;;
    esac
    [ "${#actual_md5}" -eq 32 ] || fail "invalid downloaded md5"
    [ "$actual_md5" = "$publisher_md5" ] || fail "publisher md5 mismatch"

    if command -v sha256sum >/dev/null 2>&1; then
        sha256_line=$(sha256sum "$download")
        actual_sha256=${sha256_line%% *}
        [ "$sha256_line" = "$actual_sha256  $download" ] || fail "invalid downloaded sha256"
    else
        sha256_line=$(shasum -a 256 "$download")
        actual_sha256=${sha256_line%% *}
        [ "$sha256_line" = "$actual_sha256  $download" ] || fail "invalid downloaded sha256"
    fi
    case "$actual_sha256" in
        *[!0-9a-f]*|'') fail "invalid downloaded sha256" ;;
    esac
    [ "${#actual_sha256}" -eq 64 ] || fail "invalid downloaded sha256"
    printf '%s  %s\n' "$actual_sha256" "$name" >> "$sha_lock"
    printf 'ARCHIVE=%s\nPUBLISHER_MD5=%s\nSHA256=%s\nURL=%s\n' \
        "$name" "$publisher_md5" "$actual_sha256" "$url" >> "$provenance"
    mv "$download" "$stage/$name"
    count=$((count + 1))
done < "$lock_file"

[ "$count" -eq 4 ] || fail "publisher lock must contain four archives"
for name in base_env-7.2.txz ds.epyc7002-7.2.dev.txz ds.epyc7002-7.2.env.txz epyc7002-gcc1220_glibc236_x86_64-GPL.txz; do
    grep -F -x -- "$name" "$seen" >/dev/null 2>&1 || fail "publisher lock is incomplete"
done

if [ -e "$cache_dir/SHA256SUMS" ]; then
    [ -f "$cache_dir/SHA256SUMS" ] || fail "SHA256SUMS is not a regular file"
    cmp -s "$sha_lock" "$cache_dir/SHA256SUMS" || fail "existing SHA256SUMS differs"
    mode_is_0600 "$cache_dir/SHA256SUMS" || fail "existing SHA256SUMS mode is not 0600"
fi
if [ -e "$cache_dir/PROVENANCE.txt" ]; then
    [ -f "$cache_dir/PROVENANCE.txt" ] || fail "PROVENANCE.txt is not a regular file"
    cmp -s "$provenance" "$cache_dir/PROVENANCE.txt" || fail "existing provenance differs"
    mode_is_0600 "$cache_dir/PROVENANCE.txt" || fail "existing provenance mode is not 0600"
fi
chmod 600 "$sha_lock" "$provenance"

if [ -e "$cache_dir/verified" ]; then
    [ -d "$cache_dir/verified" ] || fail "verified is not a directory"
    entry_count=$(find "$cache_dir/verified" -mindepth 1 -maxdepth 1 -print | wc -l | awk '{print $1}')
    [ "$entry_count" -eq 4 ] || fail "verified contains unexpected entries"
    for name in base_env-7.2.txz ds.epyc7002-7.2.dev.txz ds.epyc7002-7.2.env.txz epyc7002-gcc1220_glibc236_x86_64-GPL.txz; do
        target=$cache_dir/verified/$name
        [ -L "$target" ] && fail "verified archive is a symlink"
        [ -f "$target" ] || fail "verified archive is missing"
        cmp -s "$stage/$name" "$target" || fail "existing verified archive differs"
    done
else
    :
fi

if [ ! -e "$cache_dir/SHA256SUMS" ]; then
    mv "$sha_lock" "$cache_dir/SHA256SUMS"
    created_sha=1
fi
if [ ! -e "$cache_dir/PROVENANCE.txt" ]; then
    mv "$provenance" "$cache_dir/PROVENANCE.txt"
    created_provenance=1
fi
if [ ! -e "$cache_dir/verified" ]; then
    mv "$stage" "$cache_dir/verified"
    created_verified=1
fi
