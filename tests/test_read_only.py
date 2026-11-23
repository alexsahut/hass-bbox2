"""Read-only guard: the integration declares and creates nothing that acts.

`read_only_guard` (conftest) only checks the requests sent during the tests; this
test checks what the integration declares (`PLATFORMS`) and really creates
(entities, services), so that a write platform or an action entity that no
test exercises still fails the suite. Every addition fails here until it is
explicitly admitted below.
"""

from typing import Any

import pytest
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.components.calendar import CalendarEntity
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.cover import CoverEntity
from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.components.lock import LockEntity
from homeassistant.components.number import NumberEntity
from homeassistant.components.select import SelectEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.components.text import TextEntity
from homeassistant.components.update import UpdateEntity
from homeassistant.components.valve import ValveEntity
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

# Base classes are judged by the Home Assistant component they come from: an
# entity may only inherit classes of the admitted components (an allowlist, so
# that any other entity platform, present or future, is refused). Classes of
# `homeassistant.helpers` (Entity, CoordinatorEntity, RestoreEntity...) and of
# `custom_components.bbox` are neutral, except ToggleEntity, which acts.
# ButtonEntity is checked apart: only the refresh button is admitted.
ADMITTED_COMPONENTS = frozenset(str(p) for p in ADMITTED)
COMPONENTS_PACKAGE = "homeassistant.components."


def _component(cls: type) -> str | None:
    """Return the Home Assistant component the class comes from, or None."""
    if not cls.__module__.startswith(COMPONENTS_PACKAGE):
        return None
    return cls.__module__.removeprefix(COMPONENTS_PACKAGE).split(".")[0]


def _foreign_bases(entity: Entity) -> list[str]:
    """Return the base classes of the entity which are not admitted."""
    return [
        f"{cls.__name__} ({component or 'action'})"
        for cls in type(entity).__mro__
        if (component := _component(cls)) not in (None, *ADMITTED_COMPONENTS)
        or cls is ToggleEntity
    ]


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
    if foreign := _foreign_bases(entity):
        return f"{type(entity).__name__} inherits {', '.join(foreign)}: not admitted"
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
    reloaded, so that every entity the integration creates is checked; the
    registry is read again after the reload and a refresh.
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
    # Entities may also be added on a later update (ports of binary_sensor)
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    entries = er.async_entries_for_config_entry(registry, config_entry.entry_id)
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


# Action classes of Home Assistant, each mixed into a sensor below
ACTION_CLASSES: tuple[type[Entity], ...] = (
    SwitchEntity,
    ToggleEntity,
    NumberEntity,
    SelectEntity,
    TextEntity,
    CoverEntity,
    LockEntity,
    ValveEntity,
    ClimateEntity,
    UpdateEntity,
    CalendarEntity,
)


def _action_sensor(action: type[Entity]) -> Entity:
    """Return a sensor which also inherits the action class."""
    return type(f"_{action.__name__}Sensor", (SensorEntity, action), {})()


class _Camera(Entity):
    """Stand-in of Camera, whose module needs turbojpeg."""


_Camera.__module__ = "homeassistant.components.camera"


class _FilmingSensor(SensorEntity, _Camera):
    """A sensor which also acts as a camera."""


class _Infrared(Entity):
    """Stand-in of InfraredEmitterEntity, a component absent from the lists."""


_Infrared.__module__ = "homeassistant.components.infrared.entity"


class _EmittingSensor(SensorEntity, _Infrared):
    """A sensor which also sends infrared commands."""


class _NamedButton(ButtonEntity):
    """A button without entity description."""


class _PressingSensor(SensorEntity, ButtonEntity):
    """A sensor which is also a button, without entity description."""


class _RebootButton(RefreshButton):
    """A subclass of the refresh button, of the refresh key."""


class _RestartButton(ButtonEntity):
    """A button which is not the refresh button."""

    entity_description = ButtonEntityDescription(key="restart")


def _refresh_button(
    key: str | None, cls: type[RefreshButton] = RefreshButton
) -> RefreshButton:
    """Return a button of the class and key (None: no description), no coordinator."""
    button = cls.__new__(cls)
    if key is not None:
        button.entity_description = ButtonEntityDescription(key=key)
    return button


def test_admitted_entities_pass() -> None:
    """The refresh button and a plain sensor are admitted."""
    assert _refusal(Platform.SENSOR, SensorEntity()) is None
    assert _refusal(Platform.BUTTON, _refresh_button(REFRESH_KEY)) is None


@pytest.mark.parametrize("action", ACTION_CLASSES, ids=lambda c: c.__name__)
def test_action_sensor_is_refused(action: type[Entity]) -> None:
    """A sensor which also inherits an action class is refused, class named."""
    reason = _refusal(Platform.SENSOR, _action_sensor(action))
    assert reason is not None
    assert action.__name__ in reason


@pytest.mark.parametrize(
    ("domain", "entity", "named"),
    [
        (Platform.SWITCH, SwitchEntity(), "switch"),
        (Platform.SENSOR, NumberEntity(), "NumberEntity"),
        (Platform.SENSOR, _FilmingSensor(), "camera"),
        (Platform.SENSOR, _EmittingSensor(), "infrared"),
        (Platform.SENSOR, _PressingSensor(), "_PressingSensor (None)"),
        (Platform.BUTTON, _NamedButton(), "_NamedButton"),
        (Platform.BUTTON, _refresh_button(None), "RefreshButton (None)"),
        (Platform.BUTTON, _refresh_button(REFRESH_KEY, _RebootButton), "_RebootButton"),
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
