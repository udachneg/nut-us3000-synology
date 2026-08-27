# NUT US3000 2.8.5-0016 RC1

> **Superseded by `v2.8.5-0016-rc2`. Do not install RC1.** RC2 keeps the
> product name separate from the `Hevtech` maintainer attribution.

This is a pre-release awaiting a fresh package install on a preconfigured DSM
host. The package itself keeps the internal version `2.8.5-0016`; the
`v2.8.5-0016-rc1` suffix identifies only this GitHub validation stage.

## Validated scope

- Xpenology/Arc DSM `7.2.2-72806`, model `SA6400`;
- architecture `epyc7002` / x86-64;
- UGREEN US3000 USB `2b89:ffff`, serial `DC600`;
- NUT `2.8.5`, `usbhid-ups`, Arduino HID `0.22`;
- libusb `1.0.29`;
- native DSM package with no runtime container on the NAS.

Official Synology models, other DSM builds, other architectures and other UPS
units are untested. This unofficial package is provided without warranty.

## Before installation

Follow the complete English or Russian instructions in the repository. In
particular, configure the persistent DSM Firewall deny rule for TCP 3493 before
installing, keep UPS mains power and the protected load connected, and verify
the downloaded SPK against its `.sha256` asset.

The final `v2.8.5-0016` release will be promoted only after the exact RC SPK is
downloaded from GitHub, installed manually through Package Center on the
preconfigured validation host, allowed its documented 10-minute startup
window, and passes the read-only postflight. Promotion will reuse these exact
SPK bytes.

SPK SHA-256:

```text
0b9b021357e8168b99ddb6e6fb33010c976191b2b3631133d23a5753989c7307
```

Maintained by Hevtech.
