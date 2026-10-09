"""Cleaning mode select (Cat Activation / Time Activation / Manual)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import MODE_CAT_ACTIVATION, MODE_MANUAL, MODE_TIME_ACTIVATION
from .entity import CatGenieEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        CleaningModeSelect(coordinator, mid)
        for mid, g in coordinator.data.items()
        if g.configuration
    )


class CleaningModeSelect(CatGenieEntity, SelectEntity):
    _attr_options = [MODE_CAT_ACTIVATION, MODE_TIME_ACTIVATION, MODE_MANUAL]
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:cog-play"

    def __init__(self, coordinator, mid) -> None:
        super().__init__(coordinator, mid, "cleaning_mode")

    @property
    def current_option(self) -> str | None:
        return self.genie.mode

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_configuration(self._mid, self.genie.config_for_mode(option))
