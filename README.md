> **Fork maintenu par [@alexsahut](https://github.com/alexsahut)**, orienté **lecture seule**
> (suivi de la box sans la piloter). Basé sur
> [cyr-ius/hass-bbox2](https://github.com/cyr-ius/hass-bbox2) : un grand merci à
> [cyr-ius](https://github.com/cyr-ius) pour le travail d'origine. Licence MIT conservée.
> Ce fork est indépendant et n'est pas supporté par l'auteur amont.

# Bouygues Bbox Router (read-only)

This is a _custom integration_ for [Home Assistant](https://www.home-assistant.io/) to monitor a
[Bouygues Telecom Bbox](https://www.bouyguestelecom.fr/) router: WAN link, traffic, latencies,
Wi-Fi/WPS/UPnP state, system health and, with the password, presence detection.

![GitHub release](https://img.shields.io/github/release/alexsahut/hass-bbox2)

Changes since upstream 1.5.4 and incompatibilities: see [CHANGELOG.md](CHANGELOG.md).

## Read-only guarantee

This fork **never writes anything to the box**: no Wi-Fi, WPS or parental control switch, no restart.

- The integration only sends HTTP `GET` requests. The only `POST` is the login, and only when a
  password is configured. The client (`api.py`) refuses any other request, and the tests fail if one
  is sent.
- The only button, **Refresh**, just queries the box again.
- No Python dependency (`bboxpy` is not used).

## Installation

Install it from the Home Assistant Marketplace (HACS) as a **custom repository**:

1. Open the Marketplace (HACS), menu ⋮ → **Custom repositories**.
2. Repository: `https://github.com/alexsahut/hass-bbox2`, category **Integration**, then **Add**.
3. Open **Bouygues Bbox** in the list, **Download**, and pick the latest release.
4. Restart Home Assistant.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=alexsahut&repository=hass-bbox2&category=integration)

The Marketplace installs the `bbox.zip` archive of a published release, never the current state of
`master`.

The integration keeps the domain `bbox`, so it **overrides** the native `bbox` integration of Home
Assistant. At startup Home Assistant logs that a custom integration `bbox` overrides the core
integration: this warning is expected.

## Configuration

**Settings → Devices & services → Add integration → Bouygues Bbox.**

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=bbox)

### Host: `mabbox.bytel.fr`, not the IP address

Use the host name **`mabbox.bytel.fr`** (default) with TLS. When it is queried by its IP address,
the Bbox answers a redirect (`302`) to `mabbox.bytel.fr`, and its certificate is issued for that
name: the setup then shows an explicit error asking to use the name. Your DNS must resolve
`mabbox.bytel.fr` to the Bbox (an error says so otherwise).

### Password (optional)

- **Without password**: only the public data of the box are read: WAN link, IP addresses, traffic,
  uptime, firmware, temperature, memory, Ethernet ports, Wi-Fi/WPS/UPnP state, latencies, LAN
  traffic, alerts. No device tracker and no Speedtest sensor are created.
- **With the password of the Bbox web administration page**, the integration also reads the
  connected devices (device trackers), the detailed Wi-Fi state and the Speedtest.

The field is masked, and the password is redacted from the diagnostics. When the box refuses the
password, Home Assistant opens the re-authentication form, where it can be changed or removed.

**Reconfigure** (Settings → Devices & services → Bouygues Bbox → ⋮ → Reconfigure) changes the host,
TLS and the certificate verification, and adds, replaces or removes the password, without deleting
the entry. The password field is always empty (the current password is never sent back to the form):
left empty, the current password is kept; the "Remove the password" checkbox switches back to the
public data only. The box read must be the one of the entry (same LAN MAC address), otherwise the
reconfiguration is refused and the entry is unchanged. The
identifier of the box (its LAN MAC address) does not depend on the password: the entities keep their
`unique_id` with or without it.

### Options

- **Refresh rate** (seconds, default 60).
- **Track connected devices** (device trackers, default off, needs the password). It creates one
  device tracker and one Home Assistant device per host known by the box (about the value of the
  "Appareils connus" sensor, often dozens); turning it off later leaves these devices orphaned.
  Enable it only for presence detection through the box.

### Supported routers

Bbox with Bbox OS. Tested on the Sagemcom **F@st 5696b** (FTTH).

## Entities

The detail (source endpoint, classes, units, rules) is in
[`docs/maintenance/maintenance.md`](docs/maintenance/maintenance.md), section 7.
Entities marked _disabled_ are created disabled by default.

### Without password

| Entity | Type | Notes |
|---|---|---|
| Link status | binary_sensor | WAN link `Up` |
| Lien FTTH | binary_sensor | optical link state |
| IPv6 opérationnel | binary_sensor | IPv6 up with a usable address |
| Wi-Fi activé, Wi-Fi invité activé | binary_sensor | |
| Wi-Fi invité 2,4 GHz / 5 GHz | binary_sensor | _disabled_ |
| SSID de compatibilité 2,4 GHz / 5 GHz | binary_sensor | _disabled_ |
| WPS activé | binary_sensor | |
| UPnP IGD activé | binary_sensor | security sentinel: "on" is shown as a problem |
| Ethernet port N | binary_sensor | one per port, _disabled_ |
| System Temperature | sensor | °C |
| Downloaded / Uploaded | sensor | kB, total |
| Download / Upload speed | sensor | kb/s |
| Download / Upload bandwidth occupation | sensor | % of the contractual rate |
| Download / Upload occupation (raw) | sensor | raw value of the box, _disabled_ |
| Download / Upload discard packet, error packet | sensor | _disabled_ |
| Débit contractuel descendant / montant | sensor | kb/s |
| Type de lien | sensor | e.g. `1000baseT-HD`, diagnostic |
| IP Address, IPv6 Address | sensor | public addresses |
| Boot counter, Last boot | sensor | |
| Memory free | sensor | % |
| Alertes | sensor | number of alerts |
| Appareils connus | sensor | number of known hosts (no name exposed) |
| Latence ping | sensor | ms |
| Latence DNS / HTTP | sensor | ms, _disabled_ |
| Trafic LAN reçu / émis | sensor | bytes, _disabled_ |
| Refresh | button | queries the box again |

### With password (in addition)

| Entity | Type | Notes |
|---|---|---|
| Connected devices | device_tracker | one per host, option "Track connected devices" |
| Speedtest download | sensor | kb/s, _disabled_ |

## Presence detection

Device trackers need the password and the option **Track connected devices**.

The Bbox waits for some time before marking a device as inactive: there is a small delay (1 or
2 minutes) between the time you disconnect a device and the time it appears as "away" in Home
Assistant. Take it into account for `consider_home`. Newly connected devices are reported
immediately and appear as "home" at the next refresh.

## Diagnostics

**Settings → Devices & services → Bouygues Bbox → ⋮ → Download diagnostics** gives the raw data read
from the box, with the sensitive fields redacted (password, tokens, SSID, names, IP addresses, serial
number, MAC addresses…).
