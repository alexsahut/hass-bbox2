"""Read-only guard: the integration declares and creates nothing that acts.

`read_only_guard` (conftest) only checks the requests sent during the tests; this
test checks what the integration declares (`PLATFORMS`) and really creates
(entities, services), so that a write platform or an action entity that no
test exercises still fails the suite. Every addition fails here until it is
explicitly admitted below.
"""

from typing import Any

import pytest
from homeassistant.components.alarm_control_panel import AlarmControlPanelEntity
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.components.calendar import CalendarEntity
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.cover import CoverEntity
from homeassistant.components.date import DateEntity
from homeassistant.components.datetime import DateTimeEntity
from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.components.lawn_mower import LawnMowerEntity
from homeassistant.components.lock import LockEntity
from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.notify import NotifyEntity
from homeassistant.components.number import NumberEntity
from homeassistant.components.scene import Scene
from homeassistant.components.select import SelectEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.components.text import TextEntity
from homeassistant.components.time import TimeEntity
from homeassistant.components.todo import TodoListEntity
from homeassistant.components.update import UpdateEntity
from homeassistant.components.vacuum import StateVacuumEntity
from homeassistant.components.valve import ValveEntity
from homeassistant.components.water_heater import WaterHeaterEntity
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_platform
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity, ToggleEntity

from custom_components.bbox import PLATFORMS
from custom_components.bbox.button import RefreshButton
from custom_components.bbox.const import DOMAIN

from .common import setup_entry
from .conftest import FakeBox
from .const import AUTHENTICATED_ANSWERS, BOX_ID

# The only admitted platforms, each with the only class its entities may have.
# `button` is admitted for the refresh button alone (it only reads the box
# again): see REFRESH_KEY.
ADMITTED: dict[str, type[Entity]] = {
    Platform.SENSOR: SensorEntity,
    Platform.BINARY_SENSOR: BinarySensorEntity,
    Platform.DEVICE_TRACKER: ScannerEntity,
    Platform.BUTTON: RefreshButton,
}
REFRESH_KEY = "refresh"

# Home Assistant entities which act on a device: none may be created, whatever
# its platform (ToggleEntity covers switch, light, fan, siren, humidifier,
# remote; CalendarEntity and the ACTION_COMPONENTS act without being toggles).
# ButtonEntity is checked apart: only the refresh button is admitted.
ACTION_ENTITIES: tuple[type[Entity], ...] = (
    ToggleEntity,
    NumberEntity,
    SelectEntity,
    TextEntity,
    DateEntity,
    TimeEntity,
    DateTimeEntity,
    CoverEntity,
    LockEntity,
    ValveEntity,
    ClimateEntity,
    WaterHeaterEntity,
    MediaPlayerEntity,
    StateVacuumEntity,
    LawnMowerEntity,
    AlarmControlPanelEntity,
    UpdateEntity,
    Scene,
    NotifyEntity,
    TodoListEntity,
    CalendarEntity,
)
# Components whose entities act without being toggles, and whose module needs
# a dependency absent from the tests (turbojpeg, hassil, mutagen): their entity
# classes are recognised by the module of a base class, without import.
ACTION_COMPONENTS = ("camera", "assist_satellite", "tts", "conversation", "ai_task")


def _action_component(entity: Entity) -> str | None:
    """Return the action component a base class of the entity comes from."""
    for cls in type(entity).__mro__:
        for component in ACTION_COMPONENTS:
            module = f"homeassistant.components.{component}"
            if cls.__module__ == module or cls.__module__.startswith(f"{module}."):
                return f"{cls.__name__} ({component})"
    return None


@pytest.fixture(name="options")
def get_options() -> dict[str, Any]:
    """Track every host, so that every platform creates entities."""
    hosts = AUTHENTICATED_ANSWERS["hosts"][0]["hosts"]["list"]
    return {"tracked_devices": [host["macaddress"] for host in hosts]}


def _refused_platforms(platforms: list[Platform]) -> list[str]:
    """Return the declared platforms which are not admitted."""
    return sorted(str(p) for p in platforms if p not in ADMITTED)


def _services(hass: HomeAssistant) -> list[str]:
    """Return the services registered in the domain of the integration."""
    return sorted(hass.services.async_services_for_domain(DOMAIN))


def test_platforms_are_read_only() -> None:
    """PLATFORMS only holds the admitted platforms."""
    refused = _refused_platforms(PLATFORMS)
    assert not refused, f"Platform(s) not admitted (write to the box?): {refused}"


def _entities(hass: HomeAssistant, entry: ConfigEntry) -> list[tuple[str, Entity]]:
    """Return (platform, entity) of every entity created for the entry."""
    return [
        (platform.domain, entity)
        for platform in entity_platform.async_get_platforms(hass, DOMAIN)
        if platform.config_entry is not None
        and platform.config_entry.entry_id == entry.entry_id
        for entity in platform.entities.values()
    ]


def _refusal(domain: str, entity: Entity) -> str | None:
    """Return why the entity is not admitted, or None."""
    expected = ADMITTED.get(domain)
    if expected is None:
        return f"platform {domain} not admitted"
    if not isinstance(entity, expected):
        return f"{type(entity).__name__} is not a {expected.__name__}"
    if action := next((c for c in ACTION_ENTITIES if isinstance(entity, c)), None):
        return f"{type(entity).__name__} is a {action.__name__} (action)"
    if action_component := _action_component(entity):
        return f"{type(entity).__name__} is a {action_component} (action)"
    key = getattr(getattr(entity, "entity_description", None), "key", None)
    if isinstance(entity, ButtonEntity) and (
        type(entity) is not RefreshButton or key != REFRESH_KEY
    ):
        return f"button {type(entity).__name__} ({key}) is not the refresh button"
    return None


async def test_entities_are_read_only(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """Every entity created with a password is admitted; no action entity.

    Home Assistant does not add the entities disabled by default to their
    platform: every registry entry of the entry is enabled and the entry
    reloaded, so that every entity the integration creates is checked.
    """
    await setup_entry(hass, config_entry)
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, config_entry.entry_id)
    for entry in entries:
        if entry.disabled_by is not None:
            registry.async_update_entity(entry.entity_id, disabled_by=None)
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state == ConfigEntryState.LOADED

    entities = _entities(hass, config_entry)
    # The check is meaningful only if every registry entry is a checked entity
    unchecked = sorted(
        {e.entity_id for e in entries} - {entity.entity_id for _, entity in entities}
    )
    assert not unchecked, f"Entity(ies) not checked: {unchecked}"
    # and if every platform created entities
    empty = sorted({str(p) for p in PLATFORMS} - {domain for domain, _ in entities})
    assert not empty, f"Platform(s) without entity: {empty}"

    refused = {
        entity.entity_id: reason
        for domain, entity in entities
        if (reason := _refusal(domain, entity))
    }
    assert not refused, f"Entity(ies) not admitted: {refused}"


async def test_registry_is_read_only(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The registry entries of the entry: admitted platforms, refresh button only."""
    await setup_entry(hass, config_entry)
    assert config_entry.state == ConfigEntryState.LOADED

    registry = er.async_entries_for_config_entry(
        er.async_get(hass), config_entry.entry_id
    )
    assert registry
    refused = sorted(
        f"{e.entity_id} ({e.unique_id})"
        for e in registry
        if e.domain not in ADMITTED
        or (e.domain == Platform.BUTTON and e.unique_id != f"{BOX_ID}-{REFRESH_KEY}")
    )
    assert not refused, f"Entity(ies) not admitted: {refused}"
    buttons = [e.unique_id for e in registry if e.domain == Platform.BUTTON]
    assert buttons == [f"{BOX_ID}-{REFRESH_KEY}"]


async def test_no_service(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The integration registers no service of its own."""
    await setup_entry(hass, config_entry)
    assert config_entry.state == ConfigEntryState.LOADED

    services = _services(hass)
    assert not services, f"Service(s) of the domain {DOMAIN}: {services}"


# The checks themselves: each addition of the matrix is refused and named.


@pytest.mark.parametrize(
    "platform",
    [Platform.SWITCH, Platform.NUMBER, Platform.SELECT, Platform.TEXT, Platform.LIGHT],
)
def test_added_platform_is_refused(platform: Platform) -> None:
    """A write platform added to PLATFORMS is refused and named."""
    assert _refused_platforms([*PLATFORMS, platform]) == [str(platform)]


class _SwitchingSensor(SensorEntity, SwitchEntity):
    """A sensor which also acts on the box."""


class _Camera(Entity):
    """Stand-in of Camera, whose module needs turbojpeg."""


_Camera.__module__ = "homeassistant.components.camera"


class _FilmingSensor(SensorEntity, _Camera):
    """A sensor which also acts as a camera."""


class _CalendarSensor(SensorEntity, CalendarEntity):
    """A sensor which can also create events."""


class _NamedButton(ButtonEntity):
    """A button without entity description."""


class _RestartButton(ButtonEntity):
    """A button which is not the refresh button."""

    entity_description = ButtonEntityDescription(key="restart")


def _refresh_button(key: str) -> RefreshButton:
    """Return a RefreshButton of the key, without coordinator."""
    button = RefreshButton.__new__(RefreshButton)
    button.entity_description = ButtonEntityDescription(key=key)
    return button


def test_admitted_entities_pass() -> None:
    """The refresh button and a plain sensor are admitted."""
    assert _refusal(Platform.SENSOR, SensorEntity()) is None
    assert _refusal(Platform.BUTTON, _refresh_button(REFRESH_KEY)) is None


@pytest.mark.parametrize(
    ("domain", "entity", "named"),
    [
        (Platform.SWITCH, SwitchEntity(), "switch"),
        (Platform.SENSOR, _SwitchingSensor(), "_SwitchingSensor"),
        (Platform.SENSOR, NumberEntity(), "NumberEntity"),
        (Platform.SENSOR, _FilmingSensor(), "camera"),
        (Platform.SENSOR, _CalendarSensor(), "CalendarEntity"),
        (Platform.BUTTON, _NamedButton(), "_NamedButton"),
        (Platform.BUTTON, _RestartButton(), "_RestartButton"),
        (Platform.BUTTON, _refresh_button("restart"), "restart"),
    ],
)
def test_added_entity_is_refused(domain: str, entity: Entity, named: str) -> None:
    """An action entity, or a button other than refresh, is refused and named."""
    reason = _refusal(domain, entity)
    assert reason is not None
    assert named in reason


async def test_added_service_is_refused(hass: HomeAssistant) -> None:
    """A service registered in the domain of the integration is named."""

    async def reboot(call: ServiceCall) -> None:
        """Do nothing."""

    hass.services.async_register(DOMAIN, "reboot", reboot)
    assert _services(hass) == ["reboot"]
