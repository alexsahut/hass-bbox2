"""Support for Bbox sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
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
from homeassistant.helpers.entity import EntityCategory, EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

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
    # Path of the value in the data when it differs from the key (the key, which
    # builds the unique_id, never changes for an entity which is kept)
    source: str | None = None
    # The value is a start time, kept stable between two updates
    boot_time: bool = False
    # Entities removed from the registry: unique keys of replaced sensors
    replaces: tuple[str, ...] = ()


# A new boot time is only taken into account when it moves by more than this
BOOT_TIME_TOLERANCE = timedelta(seconds=10)


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


def _occupation_percent(data: dict[str, Any], direction: str) -> float | None:
    """Return the rate as a percentage of the contractual bandwidth (0-100).

    None when the contractual bandwidth is missing or 0, or the rate is unknown.
    """
    prefix = f"wan_ip_stats.wan.ip.stats.{direction}"
    bandwidth = _to_float(finditem(data, f"{prefix}.bandwidth"))
    contractual = _to_float(finditem(data, f"{prefix}.contractualBandwidth"))
    if bandwidth is None or not contractual or contractual <= 0:
        return None
    return round(min(max(bandwidth * 100 / contractual, 0.0), 100.0), 2)


def _get_boot_time(data: dict[str, Any]) -> datetime | None:
    """Return the start time of the Bbox: `device.now` minus `device.uptime`."""
    now = finditem(data, "info.device.now")
    uptime = _to_float(finditem(data, "info.device.uptime"))
    if not isinstance(now, str) or uptime is None or uptime < 0:
        return None
    if (parsed := dt_util.parse_datetime(now)) is None or parsed.tzinfo is None:
        return None
    return (parsed - timedelta(seconds=uptime)).replace(microsecond=0)


def _alerts_count(data: dict[str, Any]) -> int | None:
    """Return the number of alerts: length of `alerts.list`.

    When `alerts` is not available, `summary.alerts.count` gives the same number.
    """
    alerts = finditem(data, "alerts.alerts.list")
    if isinstance(alerts, list):
        return len(alerts)
    count = finditem(data, "summary.alerts.count")
    return count if isinstance(count, int) and not isinstance(count, bool) else None


def _known_devices(data: dict[str, Any]) -> int | None:
    """Return the number of entries of `summary.hosts` (no name nor address)."""
    hosts = finditem(data, "summary.hosts")
    return len(hosts) if isinstance(hosts, list) else None


def _last_latency(data: dict[str, Any], series: str) -> float | None:
    """Return the average latency (ms) of the last point of a `wan/diags` series.

    The series are in chronological order: the last element of the list is the
    most recent point, whatever its protocol (the box alternates IPv4 and IPv6).
    A point without measurement (no try, or no success) gives None, never 0.
    The box gives microseconds (assumption, see maintenance.md).
    """
    points = finditem(data, f"wan_diags.diags.{series}")
    if not isinstance(points, list) or not points:
        return None
    point = points[-1]
    if not isinstance(point, dict):
        return None
    tries, success = _to_float(point.get("tries")), _to_float(point.get("success"))
    average = _to_float(point.get("average"))
    if not tries or not success or average is None or average < 0:
        return None
    return round(average / 1000, 3)


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
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    BboxSensorDescription(
        key="wan_ip_stats.wan.ip.stats.rx.packetserrors",
        name="Download error packet",
        icon="mdi:upload-network",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
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
        icon="mdi:gauge",
        get_value=lambda self: _occupation_percent(self.coordinator.data, "rx"),
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BboxSensorDescription(
        key="wan_ip_stats.wan.ip.stats.rx.occupation_raw",
        name="Download occupation (raw)",
        icon="mdi:gauge",
        # Raw field of the box, its unit is not documented (see maintenance.md)
        source="wan_ip_stats.wan.ip.stats.rx.occupation",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
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
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    BboxSensorDescription(
        key="wan_ip_stats.wan.ip.stats.tx.packetserrors",
        name="Upload error packet",
        icon="mdi:upload-network",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
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
        icon="mdi:gauge",
        get_value=lambda self: _occupation_percent(self.coordinator.data, "tx"),
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BboxSensorDescription(
        key="wan_ip_stats.wan.ip.stats.tx.occupation_raw",
        name="Upload occupation (raw)",
        icon="mdi:gauge",
        # Raw field of the box, its unit is not documented (see maintenance.md)
        source="wan_ip_stats.wan.ip.stats.tx.occupation",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
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
        key="info.device.boot_time",
        name="Last boot",
        icon="mdi:clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        data_sources=("info",),
        boot_time=True,
        # Replaces the "Uptime" sensor (key "info.device.uptime")
        replaces=("info.device.uptime",),
    ),
    BboxSensorDescription(
        key="memory.device.mem.free",
        name="Memory free",
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
    BboxSensorDescription(
        key="wan_ftth_stats.wan.ftth.mode",
        translation_key="link_type",
        icon="mdi:ethernet",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BboxSensorDescription(
        key="wan_ip_stats.wan.ip.stats.rx.contractualBandwidth",
        translation_key="contractual_download",
        icon="mdi:download-network",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        value_fn=_to_float,
    ),
    BboxSensorDescription(
        key="wan_ip_stats.wan.ip.stats.tx.contractualBandwidth",
        translation_key="contractual_upload",
        icon="mdi:upload-network",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        value_fn=_to_float,
    ),
    BboxSensorDescription(
        key="alerts.alerts.list",
        translation_key="alerts",
        icon="mdi:alert-circle-outline",
        state_class=SensorStateClass.MEASUREMENT,
        get_value=lambda self: _alerts_count(self.coordinator.data),
        data_sources=("alerts", "summary"),
    ),
    BboxSensorDescription(
        key="summary.hosts",
        translation_key="known_devices",
        icon="mdi:devices",
        state_class=SensorStateClass.MEASUREMENT,
        get_value=lambda self: _known_devices(self.coordinator.data),
    ),
    BboxSensorDescription(
        key="wan_diags.diags.ping",
        translation_key="latency_ping",
        icon="mdi:timer-outline",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        get_value=lambda self: _last_latency(self.coordinator.data, "ping"),
    ),
    BboxSensorDescription(
        key="wan_diags.diags.dns",
        translation_key="latency_dns",
        icon="mdi:timer-outline",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        get_value=lambda self: _last_latency(self.coordinator.data, "dns"),
    ),
    BboxSensorDescription(
        key="wan_diags.diags.http",
        translation_key="latency_http",
        icon="mdi:timer-outline",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        get_value=lambda self: _last_latency(self.coordinator.data, "http"),
    ),
    BboxSensorDescription(
        key="lan_stats.lan.stats.rx.bytes",
        translation_key="lan_received",
        icon="mdi:download-network",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        value_fn=lambda x: int(x),
    ),
    BboxSensorDescription(
        key="lan_stats.lan.stats.tx.bytes",
        translation_key="lan_sent",
        icon="mdi:upload-network",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        value_fn=lambda x: int(x),
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
        sensor_class = BboxBootTimeSensor if description.boot_time else BboxSensor
        sensor = sensor_class(coordinator, description)
        if description.requires_auth and not coordinator.has_password:
            # Without password the sensor would stay unavailable: no entity
            if entity_id := registry.async_get_entity_id(
                SENSOR_DOMAIN, DOMAIN, sensor.unique_id
            ):
                registry.async_remove(entity_id)
            continue
        for legacy_key in description.replaces:
            # The replaced sensor would stay "unavailable" forever
            if entity_id := registry.async_get_entity_id(
                SENSOR_DOMAIN, DOMAIN, f"{sensor.box_id}-{legacy_key}"
            ):
                registry.async_remove(entity_id)
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
                else finditem(
                    self.coordinator.data,
                    self.entity_description.source or self.entity_description.key,
                )
            )
            return (
                self.entity_description.value_fn(raw_value)
                if self.entity_description.value_fn is not None
                else raw_value
            )
        except (TypeError, ValueError, ZeroDivisionError):
            # Value missing or not supported by this Bbox model
            return None


class BboxBootTimeSensor(BboxSensor):
    """Start time of the Bbox, stable from one update to the next.

    `device.now` and `device.uptime` are read at slightly different instants and
    rounded to the second: the computed time jitters by a second or two. The value
    only changes when it moves by more than BOOT_TIME_TOLERANCE (a real reboot).
    """

    _boot_time: datetime | None = None

    @property
    def native_value(self) -> datetime | None:
        """Return the start time."""
        computed = _get_boot_time(self.coordinator.data)
        if computed is None:
            return self._boot_time
        if (
            self._boot_time is None
            or abs(computed - self._boot_time) > BOOT_TIME_TOLERANCE
        ):
            self._boot_time = computed
        return self._boot_time
