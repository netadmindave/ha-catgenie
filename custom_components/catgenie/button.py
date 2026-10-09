"""Cycle control buttons (cloud: device/management/{id}/operation)."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CleaningState
from .entity import CatGenieEntity


@dataclass(frozen=True, kw_only=True)
class OpButtonDescription(ButtonEntityDescription):
    state: int | None


BUTTONS = (
    OpButtonDescription(key="start_cleaning", icon="mdi:play", state=CleaningState.PLAY),
    OpButtonDescription(key="start_special_cleaning", icon="mdi:play-speed", state=CleaningState.PLAY_SPECIAL),
    OpButtonDescription(key="pause_cleaning", icon="mdi:pause", state=CleaningState.SUSPENDED),
    OpButtonDescription(key="resume_cleaning", icon="mdi:play-pause", state=CleaningState.RESUMED),
    OpButtonDescription(key="cancel_cleaning", icon="mdi:stop", state=CleaningState.ABORT),
    OpButtonDescription(key="refresh", icon="mdi:refresh", state=None, entity_category=EntityCategory.DIAGNOSTIC),
)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        CatGenieButton(coordinator, mid, desc) for mid in coordinator.data for desc in BUTTONS
    )


class CatGenieButton(CatGenieEntity, ButtonEntity):
    entity_description: OpButtonDescription

    def __init__(self, coordinator, mid, desc: OpButtonDescription) -> None:
        super().__init__(coordinator, mid, desc.key)
        self.entity_description = desc

    async def async_press(self) -> None:
        if self.entity_description.state is None:
            await self.coordinator.async_request_refresh()
            return
        await self.coordinator.async_operation(self._mid, self.entity_description.state)
