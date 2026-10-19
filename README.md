# NUT US3000 for Synology DSM

[Русский](README_RU.md)

An unofficial native Synology DSM package that connects one UGREEN US3000 UPS
directly over USB and exposes it to DSM through a host-local NUT 2.8.5 server.
No runtime container is used on the NAS.

Current prerelease: **[2.8.5-0022 RC1](https://github.com/udachneg/nut-us3000-synology/releases/tag/v2.8.5-0022-rc1)**.
Upgrade and keep-data reinstall have been checked. Delete-data clean installation
using this public guide is still pending; this is not a final stable release.

## Tested compatibility

Only this exact combination is validated:

| Component | Validated value |
| --- | --- |
| DSM | Xpenology/Arc, DSM 7.2.2-72806, model `SA6400` |
| Architecture | `epyc7002` / x86-64 |
| UPS | UGREEN US3000, USB `2b89:ffff`, serial `DC600` |
| NUT | `2.8.5`, `usbhid-ups`, subdriver `Arduino HID 0.22` |
| libusb | `1.0.29` |

Official Synology NAS models, other DSM builds, other architectures and other
UPS units are untested. A DSM update does not automatically inherit this
compatibility claim.

## Safety and scope

- Keep UPS mains power and the protected load connected during installation.
- This package does not command UPS load-off, forced shutdown or FSD.
- DSM remains responsible for safe-mode timing, shutdown policy and standard
  notifications.
- The server and USB driver run from RAM. During a confirmed safe shutdown they
  survive package stopping and data-volume unmounting so DSM can observe mains
  restoration. Ordinary package stop/uninstall terminates the RAM services.
  Recovery on arbitrary DSM versions is not guaranteed; see
  [validation limits](docs/VALIDATION.md).
- `Package Center: Running` proves only that the retry controller is active. It
  does not prove that DSM receives a live UPS state.
- The package is provided without warranty. Test the complete setup before
  relying on it to protect data.

## Download and verify

Download these two files from **[RC 0022](https://github.com/udachneg/nut-us3000-synology/releases/tag/v2.8.5-0022-rc1)**
(a prerelease may not appear as Latest):

- `nut-us3000_epyc7002-7.2_2.8.5-0022.spk`
- `nut-us3000_epyc7002-7.2_2.8.5-0022.spk.sha256`

Verify the SPK SHA-256 on your computer before installation. For example, on
macOS or Linux:

```console
shasum -a 256 nut-us3000_epyc7002-7.2_2.8.5-0022.spk
```

The result must exactly match the published `.sha256` file.
This build's SHA-256: `cd3fbec1def596f4048a0280e6734e4d37d66c10c77e84a3763af3988c2ca72f`.
The SPK is not signed with a Synology certificate. A checksum verifies integrity,
not trust in the download source. Read the warnings and license and accept only
if you agree.

## One-time DSM Firewall prerequisite

The DSM-managed firewall rule is a persistent host prerequisite. The SPK does
not create or delete it. Configure it once before installing the package:

1. Open **Control Panel → Security → Firewall** and edit the active profile.
2. Add a deny rule for custom **TCP 3493**.
3. Select **All sources** and **All interfaces**.
4. Move it to the first enabled position, above broader allow rules.
5. Apply the profile and confirm that the rule remains enabled.

The package creates only a narrow transient early-start guard and audits the
saved DSM-managed rule. That transient guard is not a replacement for this
one-time setting.

## Manual installation

1. Connect the UGREEN US3000 USB data cable to the NAS. Keep mains power and
   the protected load connected.
2. Confirm that the firewall prerequisite above is already present.
3. Open **Package Center → Manual Install** and select the verified SPK.
4. Review the package information and license, then complete installation.
5. Leave **Arc Apps & Permissions** disabled. It is not required for the
   validated normal path.
6. Allow up to 10 minutes after system startup for the first delayed recovery
   attempt if USB was not ready immediately.

The package supplies its own helper, prepares the RAM services and grants access
only to the selected USB device. Old installation remnants and a manual udev rule
are not required. DSM UPS settings and the persistent firewall rule remain manual.
If DSM offers to open TCP 3493, do not allow network access: this setup needs a
**deny**, not an open port.

## Configure DSM UPS support

Open **Control Panel → Hardware & Power → UPS**:

1. Enable UPS support.
2. Choose **Synology UPS Server**.
3. Choose a custom safe-mode delay of **5 minutes**.
4. Enter the network UPS server address **10.255.255.1**.
5. Apply and open Device Information.

Five minutes is the selected delay, not a guarantee of battery runtime under your
load. Upgrading the package does not automatically replace a saved ten-minute delay.

`10.255.255.1` is a permanent host-local alias created before the package
service starts. It does not depend on the NAS LAN address and is not intended
for access from another device.

## Verify connection and settings

Open **Device Information** on the DSM UPS page. Require all of the following:

- manufacturer `UGREEN`;
- model `US3000`;
- status `Connected`;
- a current charge value;
- an online state rather than an unavailable server.

Do not treat the displayed runtime value `65535` seconds as a reliable runtime
estimate. Also confirm that DSM standard notifications are enabled for UPS
disconnect and reconnect events.

The package description separates sections with ◆. Connection state, DSM settings
and firewall settings have independent badges: 🟢 checked, 🔴 problem/mismatch,
🟡 unknown/waiting; ⚪ package stopped. Check the UTC observation time: text older
than 10 minutes is stale regardless of color. Refresh DSM if necessary. A green
firewall badge checks configuration and rule ordering, not external connectivity.

For this RC acceptance, wait at least 10 minutes after setup and revisit Device
Information and the package card. This observes installation; it is not a power
interruption test. A working connection alone does not prove safe shutdown.

## Boot and retry behavior

The package makes one immediate USB attempt. If USB is unavailable during
boot, its first delayed recovery waits until system uptime reaches 10 minutes;
later checks run every 5 minutes. The controller remains running between
attempts, while the UPS server starts only after the exact USB, privilege,
alias and firewall audits pass.

After a successful retry, DSM reconnects to the same `10.255.255.1` endpoint.
Loss of the UPS server does not itself instruct DSM to enter safe mode; DSM's
configured 5-minute policy applies to an actual battery-power event.

## Optional USB reconnect check

Perform this only while mains power and the protected load remain connected:

1. Disconnect only the UPS USB data cable.
2. Confirm that DSM reports loss of the UPS connection.
3. Reconnect the same USB cable.
4. Allow the retry interval and confirm that DSM reports restoration and again
   shows the live UGREEN device state.

## Upgrade and uninstall

Install a newer verified release through **Package Center → Manual Install**.
The package validates existing configuration before upgrade and preserves it.

The uninstall wizard offers two modes:

- **Keep package data** — recommended for reinstall or rollback;
- **Delete package data** — removes package-owned configuration, state and
  package home data.

Neither mode removes DSM UPS settings or the persistent DSM Firewall rule.
Review those host settings separately after uninstall.

Before uninstalling, disable UPS support in DSM and apply; monitoring is temporarily
unavailable. Remove only NUT US3000 through Package Center. For a clean install,
select Delete package data: this erases package settings, so retain a backup first
if needed. Reinstall the same verified SPK, repeat DSM UPS configuration and verify
the connection. Do not manually remove shared DSM configuration or other packages.

This is a fresh package install on a preconfigured host, not a NAS reset. The
persistent firewall deny and DSM UPS form values may remain. The package does not
create these host settings for the user.

## After a DSM update

Treat a different DSM build as untested until verified. After every update:

1. confirm that NUT US3000 is running in Package Center;
2. confirm the live UPS identity and state in DSM Device Information;
3. confirm that DSM still uses Synology UPS Server `10.255.255.1` and the
   5-minute delay;
4. confirm that the first enabled DSM Firewall rule still denies TCP 3493 from
   all sources on all interfaces;
5. perform the optional USB reconnect check before relying on protection.

## Troubleshooting

- **Package runs but DSM shows no UPS:** recheck Device Information, the exact
  address `10.255.255.1`, USB `2b89:ffff` and the firewall prerequisite.
- **Package needs up to 10 minutes after boot:** this is the designed first
  recovery delay; subsequent checks occur every 5 minutes.
- **Installation or start reports a proven privilege error on Arc:** only then
  use **Arc Control → Apps & Permissions** as a conditional fallback and retry.
  Arc Apps & Permissions is not required in the validated normal path.
- **A different DSM build or NAS model:** it is outside the tested matrix; do
  not assume compatibility from a successful installation alone.

## License and trademarks

Code and package integration maintained by Hevtech are licensed under
[`GPL-2.0-or-later`](LICENSE). Third-party licenses and exact source components
are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Build
instructions are in [docs/BUILDING.md](docs/BUILDING.md), and validation status
is in [docs/VALIDATION.md](docs/VALIDATION.md).

UGREEN, Synology and Arc names are used only to describe compatibility. This
unofficial project is not affiliated with, sponsored by or endorsed by their
respective owners.
