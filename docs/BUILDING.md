# Reproducible build

This document describes the developer build path for NUT US3000
`2.8.5-0025`. It is not part of the ordinary DSM installation flow.

## Pinned inputs

- spksrc commit: `5c3cc7da1d4221d7e081ed2a31ba820b0455d4de`
- builder image:
  `ghcr.io/synocommunity/spksrc@sha256:deeef1a01210c914c43a7c18a40aee62885eeee041cc70e7bd1907153561cc94`
- NUT `2.8.5` SHA-256:
  `18bf32e59eb764b13da3c4fa70384926d7fa584cb31d2fe7f137a570633eeec1`
- libusb `1.0.29` SHA-256:
  `5977fc950f8d1395ccea9bd48c06b3f808fd3c2c961b44b0c2e6e29fc3a70a85`
- target: `epyc7002`, DSM toolchain `7.2`

Verify the package source tree against `release/PACKAGE-SOURCE-0025.sha256`
from the checkout root using `shasum -a 256 -c release/PACKAGE-SOURCE-0025.sha256`.
Every distributed `spk/` file is byte-identical to the build-time snapshot.
Publication reuses the audited and installed 0025 binary; no package source or
SPK bytes are changed for the RC release. A new build is not required merely
to publish that artifact.

The NUT detached signature and release keyring are tracked under
`spk/sources/`. Synology Toolkit archives, sysroot, Docker image layers and
build volumes are fetched locally and are not redistributed.

## Requirements

- macOS or Linux host with POSIX shell, Python 3, Git, GnuPG and Docker;
- Docker capable of running `linux/amd64` containers;
- enough local space for the builder image, two cloned native volumes and build
  outputs;
- network access only during the explicit fetch/bootstrap phases.

## Publication checks

The following targeted checks validate current public source closure and docs;
they require no downloaded SPK and do not rerun VM/NAS lifecycle tests.
The remaining asset tests in `test_publication_0022.py` intentionally validate
historical 0022 assets in `artifacts/`; do not put 0025 assets there to run those
historical checks. Historical 0016 tests are documented separately in
`tests/historical_0016/README.md`. Verify 0025 downloads using its checksum file
as described below.

From this checkout:

```console
python3 -m unittest \
  tests.test_publication_0022.Publication0022Test.test_complete_spk_source_matches_build_snapshot \
  tests.test_publication_0022.Publication0022Test.test_source_manifest_is_exactly_the_git_distributed_source_set \
  tests.test_publication_0022.Publication0022Test.test_instructions_and_completed_gate \
  tests.test_publication_0022.Publication0022Test.test_current_document_links_resolve \
  tests.test_publication_0022.Publication0022Test.test_public_index_has_no_private_paths_or_artifacts -v
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
CACHE_NAME=nut-us3000-public-0025-build-base
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
OUTPUT_DIR=$(mktemp -d /tmp/nut-us3000-public-0025-output.XXXXXX)
/bin/sh spk/scripts/build-release.sh "$PROJECT_ROOT" "$CACHE_NAME" "$OUTPUT_DIR"
```

Both package builds and all inspector runs use `--network none`. The wrapper
creates two new volumes from the prepared base, compares normalized manifests
byte-for-byte, audits the canonical SPK and writes:

- `nut-us3000_epyc7002-7.2_2.8.5-0025.spk`;
- its `.sha256` file;
- `normalized-manifest-0025.sha256`;
- `BUILD-PROVENANCE-0025.txt`.

Expected final markers include:

```text
BUILD_A=PASS network=none
BUILD_B=PASS network=none
NORMALIZED_REBUILD_MATCH=YES
SPK_AUDIT_COMPLETE
RELEASE_BUILD_0025_COMPLETE
```

The build volumes are retained for audit or diagnosis. Remove them only after
reviewing their exact names and deciding that the evidence is no longer needed.

## Release boundary

The SPK is distributed only as a GitHub Release asset and is not committed to
Git history. A public RC must pass the documented ordinary-user installation
and read-only DSM postflight before the same SPK bytes can be promoted to the
final release.

## Published asset checks

Download all assets into one directory and run:

```console
shasum -a 256 -c SHA256SUMS-0025.txt
```

The normalized manifest itself is supplied as `normalized-manifest.json`, together
with `normalized-manifest-0025.sha256`. The existing build wrapper emits its hash;
the publication also retains the audited manifest bytes from the two-build run.
The source closure is versioned in Git; the complete tagged GitHub source archive
plus the exact NUT/libusb source archives constitute the distributed source inputs.

The source tree includes the RAM payload generator and all scripts/units it embeds.
It does not require files from a private diagnostic workspace. Build prerequisites
such as the pinned spksrc checkout/toolchain remain explicit upstream inputs.
