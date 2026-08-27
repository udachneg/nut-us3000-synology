# Validation status

Status: `RC_PENDING_PUBLIC_CLEAN_INSTALL`

The `2.8.5-0016` publication revision preserves the accepted native runtime
contract while changing only release metadata, HEVTECH source headers,
user-facing compatibility wording and public build/release infrastructure.

## Validated matrix

- Xpenology/Arc DSM `7.2.2-72806`, model `SA6400`;
- architecture `epyc7002` / x86-64;
- UGREEN US3000 `2b89:ffff`, serial `DC600`;
- NUT `2.8.5`, Arduino HID `0.22`;
- libusb `1.0.29`.

## Inherited evidence

The accepted private predecessor established reproducible offline packaging,
exact SPK topology, ELF dependencies, lifecycle behavior, USB/NUT operation,
reboot recovery, DSM connection and an external LAN-negative firewall boundary.
This document intentionally contains no private raw logs or infrastructure
identifiers.

The persistent DSM Firewall deny and DSM UPS Server settings are pre-existing
host prerequisites. The package does not create them. Therefore the public
gate is a fresh package install on a preconfigured host, not clean-host
provisioning.

## Pending public gate

The GitHub RC must be downloaded and installed manually through Package Center
after delete-data uninstall. Arc Apps & Permissions remains disabled. After 10
minutes, a read-only postflight must confirm package version/status, package-user
privilege audit, native process identity, USB identity, both local endpoints,
the exact alias and listener set, DSM-managed firewall rule, DSM connection,
fresh package data and absence of a runtime container.

The final tag and Release must not be created unless every postflight condition
passes. The final Release must reuse the exact RC SPK SHA-256.
