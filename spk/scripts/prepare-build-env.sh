#!/bin/sh
set -eu

SPKSRC_COMMIT=5c3cc7da1d4221d7e081ed2a31ba820b0455d4de
BUILDER_PLATFORM=linux/amd64
BUILDER_IMAGE=ghcr.io/synocommunity/spksrc@sha256:deeef1a01210c914c43a7c18a40aee62885eeee041cc70e7bd1907153561cc94
SPKSRC_URL=https://github.com/SynoCommunity/spksrc.git

fail() {
    printf '%s\n' "ERROR: $*" >&2
    exit 1
}

canonical_directory() {
    [ -d "$1" ] && [ ! -L "$1" ] || return 1
    resolved=$(CDPATH= cd -- "$1" && pwd -P) || return 1
    [ "$resolved" = "$1" ]
}

[ "$#" -eq 2 ] || exit 64
project_root=$1
cache_name=$2
case "$project_root" in /*) ;; *) exit 64 ;; esac
canonical_directory "$project_root" || exit 64
case "$cache_name" in ''|*[!A-Za-z0-9_.-]*) exit 64 ;; esac

lock=$project_root/spk/sources/spksrc.lock
[ -f "$lock" ] && [ ! -L "$lock" ] || fail 'spksrc lock is unavailable'
{
    IFS= read -r lock_url
    IFS= read -r lock_commit
    IFS= read -r lock_platform
    IFS= read -r lock_image
    if IFS= read -r lock_extra; then exit 1; fi
} < "$lock" || fail 'spksrc lock is malformed'
[ "$lock_url" = "SPKSRC_URL=$SPKSRC_URL" ] || fail 'spksrc URL lock mismatch'
[ "$lock_commit" = "SPKSRC_COMMIT=$SPKSRC_COMMIT" ] || fail 'spksrc commit lock mismatch'
[ "$lock_platform" = "BUILDER_PLATFORM=$BUILDER_PLATFORM" ] || fail 'builder platform lock mismatch'
[ "$lock_image" = "BUILDER_IMAGE=$BUILDER_IMAGE" ] || fail 'builder image lock mismatch'

command -v docker >/dev/null 2>&1 || fail 'docker is unavailable'
command -v git >/dev/null 2>&1 || fail 'git is unavailable'
docker volume inspect "$cache_name" >/dev/null 2>&1 && fail 'build cache volume already exists'

attempt=$(mktemp -d "${TMPDIR:-/tmp}/nut-us3000-build-env.XXXXXX") || fail 'cannot create build environment attempt'
volume_created=no
cleanup() {
    status=$?
    trap - 0 HUP INT TERM
    rm -rf "$attempt"
    if [ "$status" -ne 0 ] && [ "$volume_created" = yes ]; then
        printf '%s\n' "BUILD_ENV_RETAINED cache=$cache_name" >&2
    fi
    exit "$status"
}
trap cleanup 0 HUP INT TERM

docker pull "$BUILDER_IMAGE"
image_id=$(docker image inspect --format '{{.Id}}' "$BUILDER_IMAGE") || fail 'cannot inspect builder image'
case "$image_id" in sha256:????????????????????????????????????????????????????????????????) ;; *) fail 'builder image ID is malformed' ;; esac

git clone "$SPKSRC_URL" "$attempt/spksrc"
git -C "$attempt/spksrc" checkout --detach "$SPKSRC_COMMIT"
[ "$(git -C "$attempt/spksrc" rev-parse HEAD)" = "$SPKSRC_COMMIT" ] || fail 'spksrc checkout mismatch'

/bin/sh "$project_root/spk/scripts/fetch-verify-toolkit.sh" "$attempt/toolkit"

docker volume create "$cache_name" >/dev/null
volume_created=yes
docker run --rm --platform "$BUILDER_PLATFORM" --network none \
    -v "$attempt/spksrc:/input:ro" -v "$cache_name:/spksrc" \
    "$BUILDER_IMAGE" /bin/sh -c 'cp -a /input/. /spksrc/'
docker run --rm --platform "$BUILDER_PLATFORM" --network none \
    -v "$attempt/toolkit/verified:/toolkit:ro" -v "$cache_name:/spksrc" \
    "$BUILDER_IMAGE" /bin/sh -c '
        set -eu
        mkdir -p /spksrc/distrib/toolchain/7.2 /spksrc/distrib/toolkit/7.2
        cp -a /toolkit/epyc7002-gcc1220_glibc236_x86_64-GPL.txz /spksrc/distrib/toolchain/7.2/
        cp -a /toolkit/ds.epyc7002-7.2.dev.txz /spksrc/distrib/toolkit/7.2/
    '
docker run --rm --platform "$BUILDER_PLATFORM" --network none \
    -v "$cache_name:/spksrc" -w /spksrc \
    "$BUILDER_IMAGE" /usr/bin/make -C toolchain/syno-epyc7002-7.2 toolchain
docker run --rm --platform "$BUILDER_PLATFORM" --network none \
    -v "$cache_name:/spksrc" \
    "$BUILDER_IMAGE" /bin/sh -c \
    'umask 022; printf "BUILDER_IMAGE_ID=%s\nSPKSRC_COMMIT=%s\n" "$1" "$2" > /spksrc/.nut-us3000-build-base' \
    build-metadata "$image_id" "$SPKSRC_COMMIT"

printf '%s\n' "BUILD_ENV_PREPARED cache=$cache_name image_id=$image_id commit=$SPKSRC_COMMIT"
