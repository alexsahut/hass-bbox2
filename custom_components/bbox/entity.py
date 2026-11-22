"""Parent Entity."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BBOX_NAME, DOMAIN, MANUFACTURER
from .coordinator import BboxDataUpdateCoordinator
from .helpers import finditem, host_device_key


class BboxEntity(CoordinatorEntity[BboxDataUpdateCoordinator], Entity):
    """Base class for all Bbox entities."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: BboxDataUpdateCoordinator, description: EntityDescription
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        explicit = getattr(description, "data_sources", None)
        self._data_sources: tuple[str, ...] = (
            explicit if explicit is not None else self._default_sources(description)
        )

        device = finditem(coordinator.data, "info.device") or {}
        # LAN MAC address: the same with or without password
        self.box_id = coordinator.box_id
        self._attr_unique_id = f"{self.box_id}-{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self.box_id)},
            "manufacturer": MANUFACTURER,
            "name": BBOX_NAME,
            "model": device.get("modelname"),
            "serial_number": device.get("serialnumber"),
            "sw_version": device.get("main", {}).get("version"),
            "configuration_url": f"https://{coordinator.config_entry.data[CONF_HOST]}",
        }

    @staticmethod
    def _default_sources(description: EntityDescription) -> tuple[str, ...]:
        """Return the data the entity depends on (none: always available)."""
        return ()

    @property
    def available(self) -> bool:
        """Return True if the data the entity depends on has been read."""
        if not super().available:
            return False
        return not self._data_sources or any(
            source in self.coordinator.data for source in self._data_sources
        )


class BboxDeviceEntity(BboxEntity):
    """Base class for all device's entities connected to the Bbox."""

    def __init__(
        self,
        coordinator: BboxDataUpdateCoordinator,
        description: EntityDescription,
        device: dict[str, Any],
        name: str,
    ) -> None:
        """Initialize. The name comes from `hosts.host_names` (duplicates handled)."""
        super().__init__(coordinator, description)
        self._device = device
        self._mac = device["macaddress"]
        self._device_key = host_device_key(self.box_id, self._mac)
        self._device_name = name
        self._attr_name = name

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        return {"link": self._device.get("link")}

    @staticmethod
    def _default_sources(description: EntityDescription) -> tuple[str, ...]:
        return ("devices",)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Respond to a DataUpdateCoordinator update."""
        if "devices" in self.coordinator.data:
            devices = self.coordinator.data["devices"].get("hosts", {}).get("list", [])
            self._device = next(
                (device for device in devices if device.get("macaddress") == self._mac),
                {},
            )
        self.async_write_ha_state()
