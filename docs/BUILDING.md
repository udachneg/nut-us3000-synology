# Reproducible build

This document describes the developer build path for HEVTECH NUT US3000
`2.8.5-0016`. It is not part of the ordinary DSM installation flow.

## Pinned inputs

- spksrc commit: `5c3cc7da1d4221d7e081ed2a31ba820b0455d4de`
- builder image:
  `ghcr.io/synocommunity/spksrc@sha256:deeef1a01210c914c43a7c18a40aee62885eeee041cc70e7bd1907153561cc94`
- NUT `2.8.5` SHA-256:
  `18bf32e59eb764b13da3c4fa70384926d7fa584cb31d2fe7f137a570633eeec1`
- libusb `1.0.29` SHA-256:
  `5977fc950f8d1395ccea9bd48c06b3f808fd3c2c961b44b0c2e6e29fc3a70a85`
- target: `epyc7002`, DSM toolchain `7.2`

The NUT detached signature and release keyring are tracked under
`spk/sources/`. Synology Toolkit archives, sysroot, Docker image layers and
build volumes are fetched locally and are not redistributed.

## Requirements

- macOS or Linux host with POSIX shell, Python 3, Git, GnuPG and Docker;
- Docker capable of running `linux/amd64` containers;
- enough local space for the builder image, two cloned native volumes and build
  outputs;
- network access only during the explicit fetch/bootstrap phases.

## Tests

From a clean checkout:

```console
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## Fetch and verify redistributable sources

```console
PROJECT_ROOT=$(pwd -P)
/bin/sh spk/scripts/fetch-verify-sources.sh "$PROJECT_ROOT/artifacts"
```

`fetch-verify-sources.sh` verifies exact hashes, the bundled signature and the
pinned NUT keyring before it publishes either source archive.

## Prepare the networked build environment

Use a new Docker volume name for every bootstrap:

```console
CACHE_NAME=nut-us3000-public-0016-build-base
/bin/sh spk/scripts/prepare-build-env.sh "$PROJECT_ROOT" "$CACHE_NAME"
```

`prepare-build-env.sh` performs the only builder image pull, spksrc clone and
official Synology Toolkit acquisition. It verifies the lock, copies the exact
checkout into a native volume and bootstraps only
`toolchain/syno-epyc7002-7.2`. Existing images, volumes and caches are never
deleted automatically.

## Run two offline release builds

Create an empty canonical output directory:

```console
OUTPUT_DIR=$(mktemp -d /tmp/nut-us3000-public-0016-output.XXXXXX)
/bin/sh spk/scripts/build-release.sh "$PROJECT_ROOT" "$CACHE_NAME" "$OUTPUT_DIR"
```

Both package builds and all inspector runs use `--network none`. The wrapper
creates two new volumes from the prepared base, compares normalized manifests
byte-for-byte, audits the canonical SPK and writes:

- `nut-us3000_epyc7002-7.2_2.8.5-0016.spk`;
- its `.sha256` file;
- `normalized-manifest-0016.sha256`;
- `BUILD-PROVENANCE-0016.txt`.

Expected final markers include:

```text
BUILD_A=PASS network=none
BUILD_B=PASS network=none
NORMALIZED_REBUILD_MATCH=YES
SPK_AUDIT_COMPLETE
RELEASE_BUILD_0016_COMPLETE
```

The build volumes are retained for audit or diagnosis. Remove them only after
reviewing their exact names and deciding that the evidence is no longer needed.

## Release boundary

The SPK is distributed only as a GitHub Release asset and is not committed to
Git history. A public RC must pass the documented ordinary-user installation
and read-only DSM postflight before the same SPK bytes can be promoted to the
final release.
