"""Button for Bbox router."""

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BBoxConfigEntry
from .entity import BboxEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: BBoxConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensor."""
    coordinator = entry.runtime_data
    entities = [
        RefreshButton(
            coordinator,
            ButtonEntityDescription(
                key="refresh", name="Refresh", icon="mdi:refresh-circle"
            ),
        ),
    ]
    async_add_entities(entities)


class RefreshButton(BboxEntity, ButtonEntity):
    """Representation of a button for refreshing integration data."""

    async def async_press(self) -> None:
        """Handle the button press: only queries the box again."""
        await self.coordinator.async_request_refresh()
