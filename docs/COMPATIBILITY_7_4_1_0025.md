# Release 0025 RC1: advisory DSM compatibility

0025 RC1 is a prerelease with controlled-upgrade acceptance on DSM 7.2.2 Update 8.
On 2026-10-21, current operation after manual package start was also checked on
DSM 7.4.1-90080 Update 1. Startup during the DSM update failed; its cause is open.
Stable release 0022 is unchanged. Do not update DSM merely because 0025 accepts
its version; see the [validation record](VALIDATION.md).

## Narrow change

- Remove the runtime DSM version/build/Update allowlist. Unknown versions and
  missing or malformed VERSION metadata do not by themselves block startup.
  The old 0023 candidate's exact 7.4.1/90080/0-1 rule is superseded.
- Keep the existing x86-64/epyc7002 binary platform requirement and the independent
  configuration, ownership, identity, firewall and runtime safety checks. A failed
  safety check is not automatically evidence of DSM incompatibility.
- Package Center still has the existing installation floor `7.2.2-72806`;
  this change supports continued operation across newer DSM updates, not a
  backport to older DSM or a port to other NAS architectures.
- The existing INFO publisher adds a separate English/Russian compatibility
  field. Exact SA6400 `7.2.2/72806 Update8` is labelled "environment previously
  exercised", not guaranteed protection. Other readable environments, including
  7.4.1, are labelled unverified (yellow) by the unchanged 0025 binary. The later
  limited live check is recorded here, not retroactively embedded in the SPK.
  Unreadable/ambiguous metadata
  is "could not determine DSM environment" (yellow), never a startup prerequisite.
  VERSION is read as bounded data, never executed or copied into INFO.
  Installed DSM7.2.2 VERSION has no `unique` field: 0025 reads only productversion,
  buildnumber and smallfixnumber there, and obtains the model from the single
  epyc7002 token of fixed `/bin/uname -a` using the existing bounded executor.
  Missing/failed/ambiguous model detection stays advisory. 0024's faulty
  assumption that VERSION contains `unique` was caught before installation.
- Compatibility text never replaces live UPS connection, settings, or lifecycle
  status. It is refreshed on the existing start/stop/retry publications; no new
  background task, endpoint or persistent state is introduced.
- No change to root-helper privileges, RAM lifecycle, queue parser, firewall
  protection, USB access, timers or configuration migration. In particular the
  queue reader still accepts only its implemented `systemd 219` contract;
  arbitrary systemd versions or transaction formats are not supported.
- Toolchain remains DSM 7.2; `REQUIRED_MAX_DSM` in spksrc selects build toolchains,
  not the runtime allowlist. No new toolchain or runtime dependency is added.

## Evidence and limits

Official SA6400 base PAT 7.4.1-90080 and Update 1 were extracted offline.
Base VERSION identifies the exact platform/model. Update 1 INFO identifies
7.4.1/90080/1. The NANO payload list does not directly replace the listed NUT
integration files; this does not prove absence of every indirect change.

Compared with official 7.2.2 base72806:

- `systemctl`, `libsystemd`, `synopkgctl`, `synofirewall`, `libsynofirewall`,
  USBFS mount script and key safe-shutdown/reboot/poweroff units are identical.
- The target `systemctl --version` was executed with target loader/libraries
  in an isolated container: systemd 219.
- The target loader resolved dependencies of all five NUT package executables
  and DSM upsmon. This is a loader/ABI check, not a physical USB or daemon test.
- `synoups` matches the previously captured live 7.2.2 hash exactly.
  `synoupscommon` adds safe-mode debug-log handling and case-insensitive USB IDs;
  `ups-net.sh`/unit add reload, and udev UPS rules use explicit positive matching.
- The systemd daemon, libc, libsynopkg and upsmon differ. Their complete runtime
  behavior on the target NAS has **not** been verified by these static checks.

The host was upgraded to DSM 7.4.1 Update 1. A subsequent read-only check confirmed
live UPS/DSM communication, RAM services and identities, helper/USB permissions,
cgroup v1/name=systemd, the empty systemd219 queue response, persisted settings
and effective firewall rules over more than ten minutes. The package needed
a manual start after its first system-triggered start failed during the update.
See the [dated validation record and error comparison](VALIDATION.md).

Ordinary-reboot startup, fresh package installation, stop-hook cgroup
transactions, USB reconnect, full safe shutdown and power return on 7.4.1 remain
unverified. Existing 0021/0022 evidence applies only to unchanged components and
its documented environment. The old safe-mode observer limitation remains open.

0024 verification was limited to changed behavior: actual shell platform
admission, the compiled native INFO publisher against local metadata fixtures,
source closure and package audit. These tests do not restart anything or prove
DSM runtime compatibility. Previously passed VM/USB/power/uninstall tests are
not repeated merely because metadata or the package version changed.
0025 adds the captured three-field VERSION/uname regression and checks only
the affected INFO publisher plus source closure/package audit. The unchanged
shell admission and prior live lifecycle tests are not repeated.

## Before and after the DSM change

The pre-DSM installation gate below passed for 0025 on the documented host:
upgrade 0022 → 0025, short read-only postflight and visual Package Center check.
The bounded post-DSM read-only check also passed for current operation, with
the failed update-time startup recorded separately. Neither certifies another
installation or full lifecycle recovery.

The coordinator must first install the audited candidate on current DSM 7.2.2,
with a protected backup of 0022 SPK, package data and DSM UPS/firewall settings.
Verify fresh UPS status on both local endpoints, live DSM monitoring, five-minute
delay, firewall, helper permissions/audit and unchanged unrelated services.
No power interruption is needed for that pre-DSM gate.

Only after that gate may the separate DSM-update plan proceed. After each DSM
step, verify package-start and helper provisioning, cgroup v1/name=systemd,
systemd219 queue response/exit status, loaded units and exact RAM process
identities, USB ownership, effective firewall and persisted settings, both
endpoints and DSM's actual monitor connection. Observe for at least ten minutes.
Full safe-mode/power-return acceptance requires a separately approved window.

If pre-DSM candidate installation fails, do not update DSM. Preserve diagnostics
and use the protected 0022 package/data backup in a controlled reinstall; direct
version downgrade may be refused by Package Center, so do not promise it.
After moving to 7.4.1, 0022 is **not** a working fallback: its runtime guard rejects
that DSM. Do not promise a DSM downgrade or restoration by replacing the ARC USB.

## Sources

- [SA6400 DSM release notes](https://www.synology.com/en-uk/releaseNote/DSM?model=SA6400)
- [Official 7.4.1 archive](https://archive.synology.com/download/Os/DSM/7.4.1-90080)
- [Official Update 1 archive](https://archive.synology.com/download/Os/DSM/7.4.1-90080-1)
- [Official 7.2.2 archive](https://archive.synology.com/download/Os/DSM/7.2.2-72806)

Private analysis captures, PATs, proprietary system binaries and extraction
utilities are not distributed with the SPK or source repository.
