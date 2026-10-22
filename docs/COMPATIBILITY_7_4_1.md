# DSM compatibility policy and evidence — 0028

On **2026-10-23**, 0028 passed one complete safe-mode → mains return →
automatic NAS reboot → automatic NUT start cycle on **Xpenology/Arc SA6400,
DSM 7.4.1-90080 Update 1, epyc7002/x86-64, systemd 219**, UGREEN US3000.
No manual recovery was needed. See [validation](VALIDATION.md) and
[timings and limits](SAFE_MODE_0028.md).

## Unchanged policy

- Unknown DSM version/build/Update or unreadable metadata is advisory, not a
  version-only startup ban.
- Package Center minimum remains 7.2.2-72806; platform, ownership, configuration,
  identity and firewall checks remain enforced.
- Queue reading requires the implemented systemd 219 response contract.
- Compatibility text is separate from actual UPS and settings status.
  The embedded earlier environment matrix can still show yellow on 7.4.1.
  This dated documentation records newer evidence without changing the SPK.
- No claim extends to another DSM build, NAS model or UPS.

## Startup correction and boundaries

0025 required a manual start after an update-time failure. 0026 added bounded
diagnostics. 0027 enlarged CORE convergence from 3 to 20 seconds, without a fixed
delay; its power-recovery boot passed CORE but failed at data_missing_field.
0028 retries well-formed incomplete responses within the existing 20-second
data-readiness window, validates every present identity field, and preserves
fatal errors and strict HEALTH.

The successful 0028 boot had missing_mask=0. It proves this automatic full
cycle, not live exercise of the retry branch or the cause of every old failure.
Clean install/uninstall and USB reconnect were not repeated for 0028.

The [0025 investigation](COMPATIBILITY_7_4_1_0025.md) preserves the offline
official PAT/ABI comparison and then-unverified scenarios as a historical record.
The [0025 validation](VALIDATION_0025.md) distinguishes NUT's startup error from
Container Manager's version-limit rejection.

Do not update DSM merely because an unknown version is permitted. Verify actual
UPS monitoring and settings after updating. Do not assume DSM downgrade is
available: replacing an Arc USB does not restore upgraded DSM.
