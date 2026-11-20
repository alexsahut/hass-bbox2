"""Support for Bbox binary sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import BBoxConfigEntry
from .entity import BboxEntity
from .helpers import finditem


@dataclass(frozen=True)
class BboxBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a sensor."""

    value_fn: Callable[..., StateType] | None = None
    # Path of the value in the data when it differs from the key
    source: str | None = None
    data_sources: tuple[str, ...] | None = None
    # Computes the state from all the data (when one path is not enough)
    get_value: Callable[[dict[str, Any]], bool | None] | None = None
    # Ethernet port: id in `device/led.ethernetPort`
    port_id: Any = None


def _flag(value: Any) -> bool:
    """Convert a 0/1 flag of the box to a boolean (TypeError if missing)."""
    return bool(int(value))


def _is_up(value: Any) -> bool:
    """Return True if a state of the box reads "Up" (AttributeError if missing)."""
    return value.lower() == "up"


def _ipv6_ready(data: dict[str, Any]) -> bool | None:
    """IPv6 is operational: `ip6state` is Up and an address is Preferred.

    Unknown when `ip6state` is missing. A Preferred address is a valid address
    which can be used as the source of new connections.
    """
    state = finditem(data, "wan_ip.wan.ip.ip6state")
    if not isinstance(state, str):
        return None
    addresses = finditem(data, "wan_ip.wan.ip.ip6address")
    return _is_up(state) and any(
        isinstance(address, dict)
        and str(address.get("status", "")).lower() == "preferred"
        for address in (addresses if isinstance(addresses, list) else [])
    )


LINK_STATUS = BboxBinarySensorDescription(
    # The key is kept for the unique_id; the value is the state of the WAN link
    key="info.device.status",
    name="Link status",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    source="wan_ip.wan.link.state",
    data_sources=("wan_ip",),
    value_fn=_is_up,
)

BINARY_SENSOR_TYPES: tuple[BboxBinarySensorDescription, ...] = (
    BboxBinarySensorDescription(
        key="summary.wireless.radio",
        translation_key="wifi_enabled",
        icon="mdi:wifi",
        value_fn=_flag,
    ),
    BboxBinarySensorDescription(
        key="summary.wireless.guestenable",
        translation_key="guest_wifi_enabled",
        icon="mdi:wifi-star",
        value_fn=_flag,
    ),
    BboxBinarySensorDescription(
        key="summary.wireless.guest24enable",
        translation_key="guest_wifi_24_enabled",
        icon="mdi:wifi-star",
        entity_registry_enabled_default=False,
        value_fn=_flag,
    ),
    BboxBinarySensorDescription(
        key="summary.wireless.guest5enable",
        translation_key="guest_wifi_5_enabled",
        icon="mdi:wifi-star",
        entity_registry_enabled_default=False,
        value_fn=_flag,
    ),
    BboxBinarySensorDescription(
        key="summary.wireless.compatibility24enable",
        translation_key="compatibility_ssid_24_enabled",
        icon="mdi:wifi-cog",
        entity_registry_enabled_default=False,
        value_fn=_flag,
    ),
    BboxBinarySensorDescription(
        key="summary.wireless.compatibility5enable",
        translation_key="compatibility_ssid_5_enabled",
        icon="mdi:wifi-cog",
        entity_registry_enabled_default=False,
        value_fn=_flag,
    ),
    BboxBinarySensorDescription(
        key="wps.wps.enable",
        translation_key="wps_enabled",
        icon="mdi:lock-open-variant",
        value_fn=_flag,
    ),
    # Security sentinel: UPnP IGD lets any device of the LAN open ports on the
    # Internet. It must stay off, so "on" is shown as a problem.
    BboxBinarySensorDescription(
        key="upnp_igd.upnp.igd.enable",
        translation_key="upnp_igd_enabled",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_flag,
    ),
    BboxBinarySensorDescription(
        key="wan_ftth_stats.wan.ftth.state",
        translation_key="ftth_link",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=_is_up,
    ),
    BboxBinarySensorDescription(
        key="wan_ip.wan.ip.ip6state",
        translation_key="ipv6_ready",
        icon="mdi:numeric-6-box",
        get_value=_ipv6_ready,
    ),
)


def _port_description(index: int, port_id: Any) -> BboxBinarySensorDescription:
    """Describe the Ethernet port at position `index` of `ethernetPort`.

    The key (and so the unique_id) is the one of the former fixed ports, built
    from the position; the state is looked up by the id given by the box.
    """
    return BboxBinarySensorDescription(
        key=f"led.ethernetPort.{index}.state",
        name=f"Ethernet port {port_id}",
        entity_registry_enabled_default=False,
        port_id=port_id,
        value_fn=_is_up,
    )


def _ports(data: dict[str, Any]) -> list[Any]:
    """Return the ids of the Ethernet ports reported by `device/led`."""
    ports = finditem(data, "led.ethernetPort")
    if not isinstance(ports, list):
        return []
    return [port["id"] for port in ports if isinstance(port, dict) and "id" in port]


async def async_setup_entry(
    hass: HomeAssistant, entry: BBoxConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up binary sensors; the ports follow what `device/led` reports."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            BboxBinarySensor(coordinator, description)
            for description in (LINK_STATUS, *BINARY_SENSOR_TYPES)
        ]
    )
    known: set[Any] = set()

    @callback
    def _add_ports() -> None:
        # Also called after each update: the answer may come after the setup
        new = [
            BboxBinarySensor(coordinator, _port_description(index, port_id))
            for index, port_id in enumerate(_ports(coordinator.data))
            if port_id not in known
        ]
        known.update(sensor.entity_description.port_id for sensor in new)
        if new:
            async_add_entities(new)

    _add_ports()
    entry.async_on_unload(coordinator.async_add_listener(_add_ports))


class BboxBinarySensor(BboxEntity, BinarySensorEntity):
    """Representation of a sensor."""

    @staticmethod
    def _default_sources(description: EntityDescription) -> tuple[str, ...]:
        return (description.key.split(".")[0],)

    @property
    def is_on(self):
        """Return sensor state."""
        description = self.entity_description
        if description.get_value is not None:
            return description.get_value(self.coordinator.data)
        if description.port_id is not None:
            ports = finditem(self.coordinator.data, "led.ethernetPort")
            data = next(
                (
                    port.get("state")
                    for port in ports or []
                    if isinstance(port, dict) and port.get("id") == description.port_id
                ),
                None,
            )
        else:
            data = finditem(
                self.coordinator.data, description.source or description.key
            )
        if description.value_fn is not None:
            try:
                return description.value_fn(data)
            except (TypeError, AttributeError):
                # Value missing or not supported by this Bbox model
                return None
        return data
