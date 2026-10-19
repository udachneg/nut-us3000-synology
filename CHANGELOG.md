# Changelog

## 2.8.5-0022 — 2026-10-20

- Promote the tested RC1 to the final release without rebuilding the SPK or
  changing any package source or release-asset bytes.
- Since public 0016: exact USB permission recovery, timestamped state/setup badges,
  RU/EN help, recovery of an incomplete NUT process set, and RAM-backed lifecycle.
- Since 0021: selected DSM safe-mode delay is 5 minutes (300 seconds), with matching
  diagnostics and instructions. Saved DSM settings are not changed automatically.
- Boot recovery still waits until 10 minutes uptime when needed; retries remain
  every 5 minutes. NUT remains 2.8.5 and libusb remains 1.0.29.
- Upgrade, keep-data uninstall/reinstall and public-guide delete-data clean
  installation passed on the documented host. The clean-install postflight
  passed 614 seconds after DSM configuration, without a NAS reboot or power test.
  See docs/VALIDATION.md for the
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
