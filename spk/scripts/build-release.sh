#!/bin/sh
set -eu

SPKSRC_COMMIT=5c3cc7da1d4221d7e081ed2a31ba820b0455d4de
BUILDER_PLATFORM=linux/amd64
BUILDER_IMAGE=ghcr.io/synocommunity/spksrc@sha256:deeef1a01210c914c43a7c18a40aee62885eeee041cc70e7bd1907153561cc94
SPK_NAME=nut-us3000_epyc7002-7.2_2.8.5-0025.spk

fail() {
    printf '%s\n' "ERROR: $*" >&2
    exit 1
}

canonical_directory() {
    [ -d "$1" ] && [ ! -L "$1" ] || return 1
    resolved=$(CDPATH= cd -- "$1" && pwd -P) || return 1
    [ "$resolved" = "$1" ]
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

[ "$#" -eq 3 ] || exit 64
project_root=$1
cache_name=$2
output_dir=$3
case "$project_root:$output_dir" in *'\n'*|*'\r'*) exit 64 ;; esac
case "$project_root" in /*) ;; *) exit 64 ;; esac
case "$output_dir" in /*) ;; *) exit 64 ;; esac
case "$cache_name" in ''|*[!A-Za-z0-9_.-]*) exit 64 ;; esac
canonical_directory "$project_root" || exit 64
canonical_directory "$output_dir" || exit 64
[ -z "$(find "$output_dir" -mindepth 1 -maxdepth 1 -print -quit)" ] || fail 'output directory must be empty'

lock=$project_root/spk/sources/spksrc.lock
[ -f "$lock" ] && [ ! -L "$lock" ] || fail 'spksrc lock is unavailable'
grep -Fx "SPKSRC_COMMIT=$SPKSRC_COMMIT" "$lock" >/dev/null || fail 'spksrc commit lock mismatch'
grep -Fx "BUILDER_PLATFORM=$BUILDER_PLATFORM" "$lock" >/dev/null || fail 'builder platform lock mismatch'
grep -Fx "BUILDER_IMAGE=$BUILDER_IMAGE" "$lock" >/dev/null || fail 'builder image lock mismatch'

docker volume inspect "$cache_name" >/dev/null 2>&1 || fail 'prepared build cache is unavailable'
image_id=$(docker image inspect --format '{{.Id}}' "$BUILDER_IMAGE") || fail 'pinned builder image is unavailable'
metadata=$(docker run --rm --platform "$BUILDER_PLATFORM" --network none \
    -v "$cache_name:/base:ro" "$BUILDER_IMAGE" /bin/cat /base/.nut-us3000-build-base) || \
    fail 'prepared build metadata is unavailable'
printf '%s\n' "$metadata" | grep -Fx "BUILDER_IMAGE_ID=$image_id" >/dev/null || fail 'prepared builder image mismatch'
printf '%s\n' "$metadata" | grep -Fx "SPKSRC_COMMIT=$SPKSRC_COMMIT" >/dev/null || fail 'prepared spksrc commit mismatch'

run_id=$(date -u +%Y%m%dT%H%M%SZ)-$$
volume_a=$cache_name-build-a-$run_id
volume_b=$cache_name-build-b-$run_id
attempt=$(mktemp -d "$output_dir/.release-build.XXXXXX") || fail 'cannot create release build attempt'
success=no
cleanup() {
    status=$?
    trap - 0 HUP INT TERM
    rm -rf "$attempt"
    if [ "$status" -ne 0 ] || [ "$success" != yes ]; then
        for name in "$SPK_NAME" "$SPK_NAME.sha256" normalized-manifest-0025.sha256 BUILD-PROVENANCE-0025.txt; do
            rm -f "$output_dir/$name"
        done
        printf '%s\n' "BUILD_VOLUMES_RETAINED $volume_a $volume_b" >&2
    fi
    exit "$status"
}
trap cleanup 0 HUP INT TERM

for volume in "$volume_a" "$volume_b"; do
    docker volume inspect "$volume" >/dev/null 2>&1 && fail "build volume already exists: $volume"
    docker volume create "$volume" >/dev/null
    docker run --rm --platform "$BUILDER_PLATFORM" --network none \
        -v "$cache_name:/from:ro" -v "$volume:/to" \
        "$BUILDER_IMAGE" /bin/sh -c 'cp -a /from/. /to/'
done

mkdir "$attempt/a" "$attempt/b" "$attempt/canonical" "$attempt/manifests"
docker run --rm --platform "$BUILDER_PLATFORM" --network none \
    -v "$project_root:/project:ro" -v "$volume_a:/spksrc" -v "$attempt/a:/output" \
    "$BUILDER_IMAGE" /bin/sh /project/spk/scripts/build-spksrc-spk.sh /project /spksrc /output
printf '%s\n' 'BUILD_A=PASS network=none'
docker run --rm --platform "$BUILDER_PLATFORM" --network none \
    -v "$project_root:/project:ro" -v "$attempt/a:/output:ro" -v "$attempt/manifests:/manifests" \
    "$BUILDER_IMAGE" /usr/bin/python3 /project/spk/scripts/inspect-spk.py \
    /project "/output/$SPK_NAME" /usr/bin/x86_64-linux-gnu-readelf /manifests/a.json

docker run --rm --platform "$BUILDER_PLATFORM" --network none \
    -v "$project_root:/project:ro" -v "$volume_b:/spksrc" -v "$attempt/b:/output" \
    "$BUILDER_IMAGE" /bin/sh /project/spk/scripts/build-spksrc-spk.sh /project /spksrc /output
printf '%s\n' 'BUILD_B=PASS network=none'
docker run --rm --platform "$BUILDER_PLATFORM" --network none \
    -v "$project_root:/project:ro" -v "$attempt/b:/output:ro" -v "$attempt/manifests:/manifests" \
    "$BUILDER_IMAGE" /usr/bin/python3 /project/spk/scripts/inspect-spk.py \
    /project "/output/$SPK_NAME" /usr/bin/x86_64-linux-gnu-readelf /manifests/b.json

cmp -s "$attempt/manifests/a.json" "$attempt/manifests/b.json" || fail 'normalized rebuild manifests differ'
printf '%s\n' 'NORMALIZED_REBUILD_MATCH=YES'
cp "$attempt/a/$SPK_NAME" "$attempt/canonical/$SPK_NAME"
chmod 644 "$attempt/canonical/$SPK_NAME"
docker run --rm --platform "$BUILDER_PLATFORM" --network none \
    -v "$project_root:/project:ro" -v "$attempt/canonical:/canonical:ro" -v "$attempt/manifests:/manifests" \
    "$BUILDER_IMAGE" /usr/bin/python3 /project/spk/scripts/inspect-spk.py \
    /project "/canonical/$SPK_NAME" /usr/bin/x86_64-linux-gnu-readelf /manifests/canonical.json
cmp -s "$attempt/manifests/a.json" "$attempt/manifests/canonical.json" || fail 'canonical manifest differs from build A'

spk_hash=$(hash_file "$attempt/canonical/$SPK_NAME") || fail 'cannot hash canonical SPK'
manifest_hash=$(hash_file "$attempt/manifests/canonical.json") || fail 'cannot hash canonical manifest'
printf '%s  %s\n' "$spk_hash" "$SPK_NAME" > "$attempt/canonical/$SPK_NAME.sha256"
printf '%s  %s\n' "$manifest_hash" normalized-manifest.json > "$attempt/canonical/normalized-manifest-0025.sha256"
python3 "$project_root/spk/scripts/write-provenance.py" \
    "$attempt/canonical/BUILD-PROVENANCE-0025.txt" \
    "SPKSRC_COMMIT=$SPKSRC_COMMIT" \
    "NUT_SHA256=18bf32e59eb764b13da3c4fa70384926d7fa584cb31d2fe7f137a570633eeec1" \
    "LIBUSB_SHA256=5977fc950f8d1395ccea9bd48c06b3f808fd3c2c961b44b0c2e6e29fc3a70a85" \
    "BUILDER_IMAGE_ID=$image_id" \
    'BUILD_NETWORK=none' \
    'PACKAGE_VERSION=2.8.5-0025'

for name in "$SPK_NAME" "$SPK_NAME.sha256" normalized-manifest-0025.sha256 BUILD-PROVENANCE-0025.txt; do
    mv "$attempt/canonical/$name" "$output_dir/$name"
done
success=yes
printf '%s\n' 'SPK_AUDIT_COMPLETE'
printf '%s\n' 'RELEASE_BUILD_0025_COMPLETE'
