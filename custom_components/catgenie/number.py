"""Volume, cat-activation delay and auto panel lock."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    AUTO_LOCK_MAX_STEPS,
    AUTO_LOCK_STEP_MIN,
    CAT_DELAY_MAX_S,
    CAT_DELAY_MIN_S,
    VOLUME_MAX,
    VOLUME_MIN,
)
from .entity import CatGenieEntity


def _seconds_to_minutes(v: Any) -> float | None:
    return None if v is None else v / 60


def _minutes_to_seconds(v: float) -> int:
    return int(round(v * 60))


@dataclass(frozen=True, kw_only=True)
class GenieNumberDescription(NumberEntityDescription):
    config_key: str
    to_ha: Callable[[Any], float | None] = lambda v: v
    to_api: Callable[[float], Any] = lambda v: int(v)


NUMBERS = (
    GenieNumberDescription(
        key="volume",
        config_key="volumeLevel",
        icon="mdi:volume-high",
        native_min_value=VOLUME_MIN,
        native_max_value=VOLUME_MAX,
        native_step=1,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    ),
    GenieNumberDescription(
        key="cat_delay",
        config_key="catDelay",  # seconds
        icon="mdi:timer-sand",
        native_min_value=CAT_DELAY_MIN_S / 60,
        native_max_value=CAT_DELAY_MAX_S / 60,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        to_ha=_seconds_to_minutes,
        to_api=_minutes_to_seconds,
    ),
    GenieNumberDescription(
        key="auto_lock",
        config_key="autoLock",  # seconds, 5-minute steps, 0 = off
        icon="mdi:lock-clock",
        native_min_value=0,
        native_max_value=AUTO_LOCK_STEP_MIN * AUTO_LOCK_MAX_STEPS,
        native_step=AUTO_LOCK_STEP_MIN,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        to_ha=_seconds_to_minutes,
        to_api=_minutes_to_seconds,
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        CatGenieNumber(coordinator, mid, desc)
        for mid, g in coordinator.data.items()
        for desc in NUMBERS
        if g.config_get(desc.config_key) is not None
    )


class CatGenieNumber(CatGenieEntity, NumberEntity):
    entity_description: GenieNumberDescription

    def __init__(self, coordinator, mid, desc: GenieNumberDescription) -> None:
        super().__init__(coordinator, mid, desc.key)
        self.entity_description = desc

    @property
    def native_value(self) -> float | None:
        d = self.entity_description
        return d.to_ha(self.genie.config_get(d.config_key))

    async def async_set_native_value(self, value: float) -> None:
        d = self.entity_description
        cfg = self.genie.config_with(d.config_key, d.to_api(value))
        await self.coordinator.async_set_configuration(self._mid, cfg)
