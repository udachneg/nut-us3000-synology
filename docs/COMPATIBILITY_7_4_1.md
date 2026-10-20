# Local candidate 0023: SA6400 / DSM 7.4.1

This development branch is **not a published release**. Stable release 0022 is
unchanged. Do not update DSM merely because this candidate accepts its version.

## Narrow change

- Keep the previous DSM 7.2 policy: 7.2 patch >= 2, build >= 72806, epyc7002/x86-64.
- Add only `7.4.1`, build `90080`, `smallfixnumber` 0 or 1, with both VERSION
  `unique` and uname identifying `synology_epyc7002_sa6400`.
- Unknown builds, later updates, other new-version models, ambiguous/missing
  fields remain rejected. No change to root-helper privileges, RAM lifecycle,
  queue parser, firewall protection, USB access, timers or configuration migration.
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

No real DSM 7.4.1 boot, package installation, cgroup transaction, USB reconnect,
full safe shutdown or power-return test has been performed. Existing 0021/0022
evidence applies only to unchanged components and its documented environment.
The old full safe-mode observer limitation is not retroactively closed.

## Before and after the DSM change

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
