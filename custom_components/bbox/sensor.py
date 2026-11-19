"""Support for Bbox sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfDataRate,
    UnitOfInformation,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import BBoxConfigEntry
from .const import DOMAIN
from .entity import BboxEntity
from .helpers import finditem


@dataclass(frozen=True)
class BboxSensorDescription(SensorEntityDescription):
    """Describes a sensor."""

    get_value: Callable[..., Any] | None = None
    value_fn: Callable[..., StateType] | None = None
    # Data read by the coordinator the sensor depends on (default: first key part)
    data_sources: tuple[str, ...] | None = None
    # The sensor is only created when a password is configured
    requires_auth: bool = False


def _to_float(value: Any) -> float | None:
    """Convert a value to float, None if the value is missing or not numeric."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_temperature(data: dict[str, Any]) -> float | None:
    """Return the temperature in °C."""
    if (
        temperature := _to_float(finditem(data, "info.device.temperature.current"))
    ) is not None:
        return temperature
    if (
        temperature := _to_float(finditem(data, "cpu.device.cpu.temperature.main"))
    ) is not None:
        return round(temperature / 1000, 1)
    return None


SENSOR_TYPES: tuple[BboxSensorDescription, ...] = (
    BboxSensorDescription(
        key="info.device.temperature.current",
        name="System Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        icon="mdi:thermometer",
        # Some models (ex: F@st5688b) only report the temperature (in m°C) in the cpu data
        get_value=lambda self: _get_temperature(self.coordinator.data),
        state_class=SensorStateClass.MEASUREMENT,
        data_sources=("info", "cpu"),
    ),
    BboxSensorDescription(
        key="wan_ip_stats.wan.ip.stats.rx.bytes",
        name="Downloaded",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.KILOBYTES,
        icon="mdi:download-network",
        value_fn=lambda x: round(float(x) / 1000, 2),
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BboxSensorDescription(
        key="wan_ip_stats.wan.ip.stats.rx.packetsdiscards",
        name="Download discard packet",
        icon="mdi:upload-network",
    ),
    BboxSensorDescription(
        key="wan_ip_stats.wan.ip.stats.rx.packetserrors",
        name="Download error packet",
        icon="mdi:upload-network",
    ),
    BboxSensorDescription(
        key="wan_ip_stats.wan.ip.stats.rx.bandwidth",
        name="Download speed",
        device_class=SensorDeviceClass.DATA_RATE,
        icon="mdi:upload-network",
        value_fn=lambda x: float(x),
        native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BboxSensorDescription(
        key="wan_ip_stats.wan.ip.stats.rx.occupation",
        name="Download bandwidth occupation",
        device_class=SensorDeviceClass.POWER_FACTOR,
        icon="mdi:upload-network",
        get_value=lambda self: (
            float(
                finditem(
                    self.coordinator.data, "wan_ip_stats.wan.ip.stats.rx.bandwidth"
                )
            )
            * 100
            / float(
                finditem(
                    self.coordinator.data, "wan_ip_stats.wan.ip.stats.rx.maxBandwidth"
                )
            )
        ),
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BboxSensorDescription(
        key="wan_ip_stats.wan.ip.stats.tx.bytes",
        name="Uploaded",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.KILOBYTES,
        icon="mdi:upload-network",
        value_fn=lambda x: round(float(x) / 1000, 2),
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BboxSensorDescription(
        key="wan_ip_stats.wan.ip.stats.tx.packetsdiscards",
        name="Upload discard packet",
        icon="mdi:upload-network",
    ),
    BboxSensorDescription(
        key="wan_ip_stats.wan.ip.stats.tx.packetserrors",
        name="Upload error packet",
        icon="mdi:upload-network",
    ),
    BboxSensorDescription(
        key="wan_ip_stats.wan.ip.stats.tx.bandwidth",
        name="Upload speed",
        device_class=SensorDeviceClass.DATA_RATE,
        icon="mdi:upload-network",
        value_fn=lambda x: float(x),
        native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BboxSensorDescription(
        key="wan_ip_stats.wan.ip.stats.tx.occupation",
        name="Upload bandwidth occupation",
        device_class=SensorDeviceClass.POWER_FACTOR,
        icon="mdi:upload-network",
        get_value=lambda self: (
            float(
                finditem(
                    self.coordinator.data, "wan_ip_stats.wan.ip.stats.tx.bandwidth"
                )
            )
            * 100
            / float(
                finditem(
                    self.coordinator.data, "wan_ip_stats.wan.ip.stats.tx.maxBandwidth"
                )
            )
        ),
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BboxSensorDescription(
        key="wan_ip.wan.ip.address",
        name="IP Address",
        icon="mdi:wan",
    ),
    BboxSensorDescription(
        key="wan_ip.wan.ip.ip6address.0.ipaddress",
        name="IPv6 Address",
        icon="mdi:wan",
    ),
    BboxSensorDescription(
        key="info.device.numberofboots",
        name="Boot counter",
        icon="mdi:counter",
    ),
    BboxSensorDescription(
        key="info.device.uptime",
        name="Uptime",
        icon="mdi:clock",
        state_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
    ),
    BboxSensorDescription(
        key="memory.device.mem.free",
        name="Memory free",
        device_class=SensorDeviceClass.POWER_FACTOR,
        icon="mdi:gauge",
        get_value=lambda self: (
            int(finditem(self.coordinator.data, "memory.device.mem.free") * 100)
            / int(finditem(self.coordinator.data, "memory.device.mem.total"))
        ),
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BboxSensorDescription(
        key="speedtest_infos.speedtest.latestmeasurements.download.0.speed",
        name="Speedtest download",
        icon="mdi:speedometer",
        device_class=SensorDeviceClass.DATA_RATE,
        value_fn=lambda x: _to_float(x),
        native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        requires_auth=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: BBoxConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensor."""
    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    entities = []
    for description in SENSOR_TYPES:
        sensor = BboxSensor(coordinator, description)
        if description.requires_auth and not coordinator.has_password:
            # Without password the sensor would stay unavailable: no entity
            if entity_id := registry.async_get_entity_id(
                SENSOR_DOMAIN, DOMAIN, sensor.unique_id
            ):
                registry.async_remove(entity_id)
            continue
        entities.append(sensor)
    async_add_entities(entities)


class BboxSensor(BboxEntity, SensorEntity):
    """Representation of a sensor."""

    @staticmethod
    def _default_sources(description: EntityDescription) -> tuple[str, ...]:
        return (description.key.split(".")[0],)

    @property
    def native_value(self):
        """Return sensor state."""
        try:
            raw_value = (
                self.entity_description.get_value(self)
                if self.entity_description.get_value is not None
                else finditem(self.coordinator.data, self.entity_description.key)
            )
            return (
                self.entity_description.value_fn(raw_value)
                if self.entity_description.value_fn is not None
                else raw_value
            )
        except (TypeError, ValueError, ZeroDivisionError):
            # Value missing or not supported by this Bbox model
            return None
