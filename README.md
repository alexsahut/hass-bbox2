> **Fork maintenu par [@alexsahut](https://github.com/alexsahut)**, orienté **lecture seule**
> (suivi de la box sans la piloter). Basé sur
> [cyr-ius/hass-bbox2](https://github.com/cyr-ius/hass-bbox2) : un grand merci à
> [cyr-ius](https://github.com/cyr-ius) pour le travail d'origine. Licence MIT conservée.
> Ce fork est indépendant et n'est pas supporté par l'auteur amont.
> Installation : ajouter ce dépôt comme dépôt personnalisé (catégorie « Integration »)
> dans HACS / la Marketplace de Home Assistant.

# Bouygues Bbox Router

This a _custom component_ for [Home Assistant](https://www.home-assistant.io/).
The `bbox2` integration allows you to observe [Bbox router](http://www.bouygues.fr/).

There is currently support for the following device types within Home Assistant:

- Sensor with traffic metrics
- Binary Sensor with wan status , public ip , private ip
- Device tracker for connected devices (via option add wired devices)
- Press button to refresh the data (only queries the box)

This fork is **read-only**: it never writes anything to the box (no Wi-Fi, WPS, parental control switch, no restart).

![GitHub release](https://img.shields.io/github/release/Cyr-ius/hass-bbox2)
[![hacs_badge](https://img.shields.io/badge/HACS-Default-bouygues.svg)](https://github.com/hacs/integration)
![downloads](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.bbox.total)

## Configuration

The preferred way to setup the Bouygues Bbox platform is by enabling the discovery component.

Add Bouygues Bbox module via HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=alexsahut&repository=hass-bbox2&category=integration)

Add your device via the Integration menu

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=bbox2)

### Initial setup

Use the host name **`mabbox.bytel.fr`** (default) with TLS. The Bbox answers a redirect (`302`) to
`mabbox.bytel.fr` when it is queried by its IP address: the setup then shows an explicit error asking
to use that name. Your DNS must resolve `mabbox.bytel.fr` to the Bbox (an error says so otherwise).

The **password is optional**:

- **Without password**: only the public data of the box are read (state of the link, IP addresses,
  traffic, uptime, firmware, temperature, memory, Ethernet ports, WPS). No device tracker and no
  Speedtest sensor are created.
- **With the password of the Bbox web administration page**: the connected devices (device
  tracker), the Wi-Fi state and the Speedtest are read in addition.

The password can be added, changed or removed later from the re-authentication form.

The integration only reads the box (HTTP `GET`). The only `POST` is the login, when a password is set.

### Supported routers

Only the routers with Bbox OS are supported:

- Bbox (all versions)

## Presence Detection

This platform offers presence detection by keeping track of the
devices connected to a [Bbox](http://www.bouygues.fr/) router.

Presence detection needs the password. Ability to disable this option by integration options ("Track connected devices").

### Notes

Note that the Bbox waits for some time before marking a device as inactive, meaning that there will be a small delay (1 or 2 minutes) between the time you disconnect a device and the time it will appear as "away" in Home Assistant.

You should take this into account when specifying the `consider_home` parameter.
On the contrary, the Bbox immediately reports devices newly connected, so they should appear as "home" almost instantly, as soon as Home Assistant refreshes the devices states.

## Sensor

This platform offers you sensors to monitor a Bbox router. The monitored conditions are instant upload and download rates in kb/s. The public sensors (Wi-Fi, WPS, UPnP, FTTH/IPv6 link, contractual rates, alerts, latencies, LAN traffic...) work without a password. The detail of the sensors (source, classes, units, enabled by default, public or authenticated) is in `docs/maintenance/maintenance.md`, section 7.
