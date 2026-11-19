"""Support for tracking."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import (
    DOMAIN as DEVICE_TRACKER_DOMAIN,
)
from homeassistant.components.device_tracker import (
    ScannerEntity,
    SourceType,
)
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BBoxConfigEntry
from .const import CONF_TRACK_DEVICES, DEFAULT_TRACK_DEVICES
from .coordinator import BboxDataUpdateCoordinator
from .entity import BboxDeviceEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: BBoxConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensor."""
    coordinator = entry.runtime_data
    if not coordinator.has_password or not entry.options.get(
        CONF_TRACK_DEVICES, DEFAULT_TRACK_DEVICES
    ):
        # The hosts need a password. Remove the trackers created before the
        # option was disabled, or before the password was removed
        registry = er.async_get(hass)
        for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
            if reg_entry.domain == DEVICE_TRACKER_DOMAIN:
                registry.async_remove(reg_entry.entity_id)
        return

    description = SensorEntityDescription(key="tracker", translation_key="tracker")
    devices = coordinator.data.get("devices", {}).get("hosts", {}).get("list", [])
    entities = [
        BboxDeviceTracker(coordinator, description, device)
        for device in devices
        if device.get("macaddress")
    ]
    async_add_entities(entities)


class BboxDeviceTracker(BboxDeviceEntity, ScannerEntity):
    """Representation of a tracked device."""

    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: BboxDataUpdateCoordinator,
        description: SensorEntityDescription,
        device: dict[str, Any],
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, description, device)

    @property
    def source_type(self) -> str:
        """Return the source type, eg gps or router, of the device."""
        return SourceType.ROUTER

    @property
    def mac_address(self) -> str:
        """Return mac address."""
        return self._mac

    @property
    def ip_address(self) -> str | None:
        """Return ip address."""
        return self._device.get("ipaddress")

    @property
    def is_connected(self) -> bool:
        """Return connecting status."""
        return self._device.get("active", 0) == 1
