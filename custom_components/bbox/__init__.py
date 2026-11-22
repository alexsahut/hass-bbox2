"""The Bouygues Bbox integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    BBOX_NAME,
    CONF_TRACK_DEVICES,
    CONF_TRACKED_DEVICES,
    DOMAIN,
    MANUFACTURER,
)
from .coordinator import BboxDataUpdateCoordinator
from .helpers import box_identifier, finditem, host_device_key
from .hosts import mac_key, tracked_macs

RESTART_BUTTON_KEY = "restart"

type BBoxConfigEntry = ConfigEntry[BboxDataUpdateCoordinator]

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.BUTTON,
]


async def async_setup_entry(hass: HomeAssistant, entry: BBoxConfigEntry) -> bool:
    """Set up Bouygues Bbox from a config entry."""
    coordinator = BboxDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    if not entry.unique_id:
        # Every entry gets the LAN MAC address from the config flow
        if not (box_id := box_identifier(coordinator.data.get("lan_ip"))):
            raise ConfigEntryError("The LAN MAC address of the Bbox is unknown")
        hass.config_entries.async_update_entry(entry, unique_id=box_id)

    # The Bbox device must exist before the devices connected to it (via_device_id)
    device = finditem(coordinator.data, "info.device") or {}
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, coordinator.box_id)},
        manufacturer=MANUFACTURER,
        name=BBOX_NAME,
        model=device.get("modelname"),
        serial_number=device.get("serialnumber"),
        sw_version=(device.get("main") or {}).get("version"),
    )

    _async_remove_write_entities(hass, entry)
    _async_cleanup_hosts(hass, entry, coordinator)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


@callback
def _async_remove_write_entities(hass: HomeAssistant, entry: BBoxConfigEntry) -> None:
    """Remove the switch and restart button entities of this entry.

    These write entities no longer exist; earlier installations may still have
    them in the entity registry. Idempotent, limited to this config entry.
    """
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.domain == Platform.SWITCH or (
            entity.domain == Platform.BUTTON
            and entity.unique_id.endswith(f"-{RESTART_BUTTON_KEY}")
        ):
            registry.async_remove(entity.entity_id)


@callback
def _async_cleanup_hosts(
    hass: HomeAssistant, entry: BBoxConfigEntry, coordinator: BboxDataUpdateCoordinator
) -> None:
    """Remove the trackers and the devices of the hosts which are not chosen.

    Run at every load, idempotent, limited to this config entry. Without
    password no host is chosen (they can not be read): all are removed. A chosen
    host stays even if the box does not list it at the moment.

    - the trackers (entity registry) of this entry whose MAC address is not
      chosen are removed (the unique_id of a tracker is its MAC address);
    - the devices of this entry are kept if they are the Bbox, or a chosen host;
      this entry is removed from the others (`_async_release_device`): a device
      shared with another integration survives.

    No other entity is touched: the sensors, binary sensors and the button
    belong to the Bbox device.
    """
    chosen = (
        {mac_key(mac) for mac in tracked_macs(entry.options)}
        if coordinator.has_password
        else set()
    )
    entities = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(entities, entry.entry_id):
        if (
            reg_entry.domain == Platform.DEVICE_TRACKER
            and mac_key(reg_entry.unique_id) not in chosen
        ):
            entities.async_remove(reg_entry.entity_id)

    kept = {
        (DOMAIN, host_device_key(coordinator.box_id, mac).lower()) for mac in chosen
    }
    devices = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(devices, entry.entry_id):
        if (DOMAIN, coordinator.box_id) in device.identifiers:
            continue
        if any((domain, key.lower()) in kept for domain, key in device.identifiers):
            continue
        if any(
            kind == dr.CONNECTION_NETWORK_MAC and mac_key(value) in chosen
            for kind, value in device.connections
        ):
            continue
        _async_release_device(devices, device, entry.entry_id)


@callback
def _async_release_device(
    devices: dr.DeviceRegistry, device: dr.DeviceEntry, entry_id: str
) -> None:
    """Remove this config entry from a device, never the device of another one.

    Up to HA 2026.9 (`DeviceEntry.config_entries`), HA merges the devices which
    declare the same MAC address connection (Shelly, ESPHome, Sonos...) into one
    device shared by several config entries, listed by
    `async_entries_for_config_entry`: only this entry is detached, HA deletes
    the device once it has no config entry left. Since HA 2026.10
    (`DeviceEntry.config_entry_id`), a device belongs to a single config entry
    (`remove_config_entry_id` is deprecated): the device listed for this entry
    is ours alone and is removed, the one of the other integration is another
    device.
    """
    if hasattr(device, "config_entry_id"):
        devices.async_remove_device(device.id)
    else:
        devices.async_update_device(device.id, remove_config_entry_id=entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: BBoxConfigEntry) -> bool:
    """Migrate the config entry (minor versions only).

    1.2 (2.0.2): the boolean option `track_devices` becomes the list
    `tracked_devices`, empty: the user chooses the devices to track. The major
    version stays 1, so that 2.0.1 can still load the entry (it ignores the
    unknown option and has no migration to run).
    """
    if entry.minor_version < 2:
        options = {k: v for k, v in entry.options.items() if k != CONF_TRACK_DEVICES}
        options.setdefault(CONF_TRACKED_DEVICES, [])
        hass.config_entries.async_update_entry(entry, options=options, minor_version=2)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: BBoxConfigEntry) -> None:
    """Reload the entry when the options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: BBoxConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: BBoxConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Remove the device of a host, never the one of the Bbox.

    The MAC address of the host is removed from the chosen hosts
    (`tracked_devices`), the other options are kept: the host is not created
    again at the next load. A host is known by its MAC address connection, or
    by its identifier `{box_id}_{mac}` (`host_device_key`).
    """
    box_id = str(entry.unique_id)
    if (DOMAIN, box_id) in device_entry.identifiers:
        return False

    removed = {
        mac_key(value)
        for kind, value in device_entry.connections
        if kind == dr.CONNECTION_NETWORK_MAC
    }
    chosen = tracked_macs(entry.options)
    for mac in chosen:
        if any(
            (domain, key.lower()) == (DOMAIN, host_device_key(box_id, mac).lower())
            for domain, key in device_entry.identifiers
        ):
            removed.add(mac_key(mac))
    kept = [mac for mac in chosen if mac_key(mac) not in removed]
    if kept != chosen:
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_TRACKED_DEVICES: kept}
        )
    return True
