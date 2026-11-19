"""Helpers shared by the tests."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up the entry and wait for the entities."""
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
