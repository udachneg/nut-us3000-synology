# NUT US3000 for Synology DSM

[Русский](README_RU.md)

An unofficial native Synology DSM package that connects one UGREEN US3000 UPS
directly over USB and exposes it to DSM through a host-local NUT 2.8.5 server.
No runtime container is used on the NAS.

The current public package version is `2.8.5-0016`. This release starts as a
release candidate until its public fresh package install on a preconfigured
host is complete.

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
- `Package Center: Running` proves only that the retry controller is active. It
  does not prove that DSM receives a live UPS state.
- The package is provided without warranty. Test the complete setup before
  relying on it to protect data.

## Download and verify

Download these two files from [GitHub Releases](https://github.com/udachneg/nut-us3000-synology/releases):

- `nut-us3000_epyc7002-7.2_2.8.5-0016.spk`
- `nut-us3000_epyc7002-7.2_2.8.5-0016.spk.sha256`

Verify the SPK SHA-256 on your computer before installation. For example, on
macOS or Linux:

```console
shasum -a 256 nut-us3000_epyc7002-7.2_2.8.5-0016.spk
```

The result must exactly match the published `.sha256` file.

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

## Configure DSM UPS support

Open **Control Panel → Hardware & Power → UPS**:

1. Enable UPS support.
2. Choose **Synology UPS Server**.
3. Set the safe-mode delay to **10 minutes**.
4. Enter the network UPS server address **10.255.255.1**.
5. Apply the settings.

`10.255.255.1` is a permanent host-local alias created before the package
service starts. It does not depend on the NAS LAN address and is not intended
for access from another device.

## Verify actual protection

Open **Device Information** on the DSM UPS page. Require all of the following:

- manufacturer `UGREEN`;
- model `US3000`;
- status `Connected`;
- a current charge value;
- an online state rather than an unavailable server.

Do not treat the displayed runtime value `65535` seconds as a reliable runtime
estimate. Also confirm that DSM standard notifications are enabled for UPS
disconnect and reconnect events.

## Boot and retry behavior

The package makes one immediate USB attempt. If USB is unavailable during
boot, its first delayed recovery waits until system uptime reaches 10 minutes;
later checks run every 5 minutes. The controller remains running between
attempts, while the UPS server starts only after the exact USB, privilege,
alias and firewall audits pass.

After a successful retry, DSM reconnects to the same `10.255.255.1` endpoint.
Loss of the UPS server does not itself instruct DSM to enter safe mode; DSM's
configured 10-minute policy applies to an actual battery-power event.

## Optional USB reconnect check

Perform this only while mains power and the protected load remain connected:

1. Disconnect only the UPS USB data cable.
2. Confirm that DSM reports loss of the UPS connection.
3. Reconnect the same USB cable.
4. Allow the retry interval and confirm that DSM reports restoration and again
   shows the live UGREEN device state.

## Upgrade and uninstall

Install a newer signed release through **Package Center → Manual Install**.
The package validates existing configuration before upgrade and preserves it.

The uninstall wizard offers two modes:

- **Keep package data** — recommended for reinstall or rollback;
- **Delete package data** — removes package-owned configuration, state and
  package home data.

Neither mode removes DSM UPS settings or the persistent DSM Firewall rule.
Review those host settings separately after uninstall.

## After a DSM update

Treat a different DSM build as untested until verified. After every update:

1. confirm that NUT US3000 is running in Package Center;
2. confirm the live UPS identity and state in DSM Device Information;
3. confirm that DSM still uses Synology UPS Server `10.255.255.1` and the
   10-minute delay;
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
