#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile


ALLOWED_KEYS = {
    "BUILD_NETWORK",
    "BUILDER_IMAGE_ID",
    "LIBUSB_SHA256",
    "NUT_SHA256",
    "PACKAGE_VERSION",
    "SPKSRC_COMMIT",
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        return 64
    output = Path(argv[1])
    if not output.is_absolute() or output.exists() or output.is_symlink():
        return 64
    if not output.parent.is_dir() or output.parent.is_symlink():
        return 64

    values: dict[str, str] = {}
    for raw in argv[2:]:
        if "\n" in raw or "\r" in raw or "=" not in raw:
            fail("invalid provenance argument")
        key, value = raw.split("=", 1)
        if key not in ALLOWED_KEYS:
            fail(f"unknown provenance key: {key}")
        if key in values:
            fail(f"duplicate provenance key: {key}")
        if not value:
            fail(f"empty provenance value: {key}")
        if value.startswith("/") or any(marker in value for marker in ("/Users/", "/home/", "/private/")):
            fail(f"private host path in provenance value: {key}")
        values[key] = value

    if set(values) != ALLOWED_KEYS:
        fail("provenance key set mismatch")

    payload = "".join(f"{key}={values[key]}\n" for key in sorted(values))
    descriptor, temporary = tempfile.mkstemp(prefix=".provenance.", dir=output.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.link(temporary, output)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
