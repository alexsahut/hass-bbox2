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
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BBoxConfigEntry
from .const import DOMAIN
from .coordinator import BboxDataUpdateCoordinator
from .entity import BboxDeviceEntity
from .helpers import host_device_key
from .hosts import clean, host_names, hosts_of, mac_key, tracked_macs


async def async_setup_entry(
    hass: HomeAssistant, entry: BBoxConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the trackers of the chosen hosts (none by default).

    The registry was cleaned beforehand (see `async_cleanup_hosts`): without
    password or without a chosen host there is nothing to add.
    """
    coordinator = entry.runtime_data
    if not coordinator.has_password:
        return
    chosen = {mac_key(mac) for mac in tracked_macs(entry.options)}
    hosts = hosts_of(coordinator.data)
    names = host_names(hosts)
    registry = er.async_get(hass)

    description = SensorEntityDescription(key="tracker", translation_key="tracker")
    entities: list[BboxDeviceTracker] = []
    for host in hosts:
        mac = clean(host.get("macaddress"))
        if not mac or mac_key(mac) not in chosen:
            continue
        # A tracker disabled by the integration (2.0.1, or 2.0.2 from Home
        # Assistant 2026.11) is enabled again; a
        # tracker disabled by the user stays disabled
        entity_id = registry.async_get_entity_id(DEVICE_TRACKER_DOMAIN, DOMAIN, mac)
        reg_entry = registry.async_get(entity_id) if entity_id else None
        if reg_entry and reg_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
            registry.async_update_entity(reg_entry.entity_id, disabled_by=None)
        name = names[mac_key(mac)]
        _async_register_device(hass, entry, coordinator, mac, name)
        entities.append(BboxDeviceTracker(coordinator, description, host, name))
    async_add_entities(entities)


def _async_register_device(
    hass: HomeAssistant,
    entry: BBoxConfigEntry,
    coordinator: BboxDataUpdateCoordinator,
    mac: str,
    name: str,
) -> None:
    """Create (or update) the Home Assistant device of a chosen host.

    The device is created here, named after the host, with the Bbox as parent;
    the tracker is linked to it by its `device_info`. The
    identifier `(bbox, {box_id}_{mac})` is the one of 2.0.1. The name given by
    the user (`name_by_user`) is never touched. A device belongs to a single
    config entry: the device of another integration with the same MAC address
    is a different device, left alone.
    """
    devices = dr.async_get(hass)
    box = devices.async_get_device_by_identifier(
        (DOMAIN, coordinator.box_id), entry.entry_id
    )
    extra: dict[str, Any] = {}
    if box is not None:
        extra["via_device_id"] = box.id
    devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, host_device_key(coordinator.box_id, mac))},
        connections={(dr.CONNECTION_NETWORK_MAC, mac)},
        name=name,
        **extra,
    )


class BboxDeviceTracker(BboxDeviceEntity, ScannerEntity):
    """Representation of a tracked device."""

    # The name of the tracker is the one of its device, including the name given
    # by the user (`name_by_user`)
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BboxDataUpdateCoordinator,
        description: SensorEntityDescription,
        device: dict[str, Any],
        name: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, description, device, name)
        self._attr_name = None
        # Home Assistant names the device of a tracker after its hostname
        self._attr_hostname = name
        # The device of the host (see `_async_register_device`), not the one of
        # the Bbox; identifiers and connections only: the name is left alone
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_key)},
            connections={(dr.CONNECTION_NETWORK_MAC, self._mac)},
        )

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return the device of the host.

        `ScannerEntity` returns no device info up to Home Assistant 2026.10, and
        the one of `BboxEntity` (the Bbox) from 2026.11.
        """
        return self._attr_device_info

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return True: the host was chosen by the user.

        `ScannerEntity` disables it otherwise at its first setup from Home
        Assistant 2026.11.
        """
        return True

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
