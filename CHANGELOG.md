# Changelog

## 2.8.5-0022 — pre-release (RC1)

- Publish the already-built and NAS-tested 0022 candidate without rebuilding it.
- Since public 0016: exact USB permission recovery, timestamped state/setup badges,
  RU/EN help, recovery of an incomplete NUT process set, and RAM-backed lifecycle.
- Since 0021: selected DSM safe-mode delay is 5 minutes (300 seconds), with matching
  diagnostics and instructions. Saved DSM settings are not changed automatically.
- Boot recovery still waits until 10 minutes uptime when needed; retries remain
  every 5 minutes. NUT remains 2.8.5 and libusb remains 1.0.29.
- Upgrade and keep-data uninstall/reinstall passed on the documented host.
  Public delete-data installation is pending. See docs/VALIDATION.md for the
  safe-mode observer limitation and exact scope of inherited evidence.

## 2.8.5-0016 — pre-release

- First public release candidate, maintained by Hevtech.
- Native NUT 2.8.5 and libusb 1.0.29 package for the exact documented
  Xpenology/Arc DSM matrix.
- Reproducible two-build offline release flow with pinned upstream sources,
  normalized manifest and SPK inspection.
- English and Russian installation, firewall, verification and maintenance
  documentation.
- Public clean-install validation pending before final release.
