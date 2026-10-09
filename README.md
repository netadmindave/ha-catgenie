<p align="center"><img src="custom_components/catgenie/brand/icon@2x.png" width="160" alt="CatGenie"></p>

# CatGenie for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Validate](https://github.com/netadmindave/ha-catgenie/actions/workflows/validate.yml/badge.svg)](https://github.com/netadmindave/ha-catgenie/actions/workflows/validate.yml)

An unofficial Home Assistant integration that replaces the CatGenie app (Petnovations) for CatGenie A.I. self-cleaning litter boxes. It talks to the same cloud API as the official app. That API was worked out from the Android app (v1.8.250); see [PROTOCOL.md](PROTOCOL.md).

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=netadmindave&repository=ha-catgenie&category=integration)

1. In HACS, open the ⋮ menu → **Custom repositories**, add `https://github.com/netadmindave/ha-catgenie` with type **Integration**.
2. Install **CatGenie**, then restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → CatGenie**.
4. Enter your country calling code (1 for the US) and the phone number from the CatGenie app, then the SMS code you receive.

### Manual

Copy `custom_components/catgenie` into `<config>/custom_components/` and restart.

Requires Home Assistant **2026.3** or newer (the integration ships its own brand icons).

## Entities (per CatGenie)

| Type | Entities |
|---|---|
| Button | Start cleaning · Start special cycle · Pause · Resume · Cancel cleaning · Refresh |
| Sensor | Status · Cycle progress (empty when idle) · SaniSolution washes left · Last clean · Active errors · Schedule · Do not disturb · Raw cloud data *(diagnostic, disabled by default)* |
| Binary sensor | Connected · Cleaning · Problem · SaniSolution low (≤ 30 washes, as in the app) |
| Select | Cleaning mode: Cat activation / Time activation / Manual |
| Switch | Panel lock · Extra wash · Extra shake · Extra dry |
| Number | Volume (1–7) · Cat activation delay (5–30 min) · Auto panel lock (0–30 min in 5-min steps, 0 = off) |

## Actions

| Action | What it does |
|---|---|
| `catgenie.set_schedule` | Sets up to 8 local cleaning times, and can also switch the unit to Time activation. |
| `catgenie.set_do_not_disturb` | Sets the quiet window in local time. Cat activation won't start a cycle during it. |
| `catgenie.set_configuration` | Advanced: merges raw keys into the device configuration (for example `catSense`). |

```yaml
action: catgenie.set_schedule
data:
  device_id: <your CatGenie>
  times: ["08:00", "14:00", "20:00"]
```

## Notes

- **Cloud polling.** The integration polls every 30 seconds (configurable), and every 10 seconds while a cycle is running. Commands go out through the CatGenie cloud, the same way the app sends them.
- **No local control.** The unit only uses Bluetooth during Wi-Fi setup, and doesn't advertise once it's online.
- **Settings writes send the whole configuration.** Changing a setting sends the full device configuration back, as the app does. That avoids clobbering fields Home Assistant doesn't expose.
- **Re-authentication.** If the cloud revokes the login, Home Assistant raises a re-authentication prompt. You'll get a new SMS code.

## Troubleshooting

Turn on debug logging:

```yaml
logger:
  logs:
    custom_components.catgenie: debug
```

You can also use **Download diagnostics** on the integration page. Your phone number, MAC address, tokens and the signing secret are redacted.

## Disclaimer

This project is not affiliated with or endorsed by Petnovations. CatGenie is a trademark of its owner. The cloud API is undocumented and may change without notice.
