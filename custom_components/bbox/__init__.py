"""The Bouygues Bbox integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import BBOX_NAME, DOMAIN, MANUFACTURER
from .coordinator import BboxDataUpdateCoordinator
from .helpers import box_identifier, finditem

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


async def _async_update_listener(hass: HomeAssistant, entry: BBoxConfigEntry) -> None:
    """Reload the entry when the options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: BBoxConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: BBoxConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Remove config entry from a device."""
    return True
