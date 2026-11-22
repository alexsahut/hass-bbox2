"""Button for Bbox router."""

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BBoxConfigEntry
from .entity import BboxEntity

REFRESH_BUTTON = ButtonEntityDescription(
    key="refresh", translation_key="refresh", icon="mdi:refresh-circle"
)


async def async_setup_entry(
    hass: HomeAssistant, entry: BBoxConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensor."""
    coordinator = entry.runtime_data
    async_add_entities([RefreshButton(coordinator, REFRESH_BUTTON)])


class RefreshButton(BboxEntity, ButtonEntity):
    """Representation of a button for refreshing integration data."""

    async def async_press(self) -> None:
        """Handle the button press: only queries the box again."""
        await self.coordinator.async_request_refresh()
