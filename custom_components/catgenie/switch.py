"""Configuration switches: panel lock and cycle extras."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import CatGenieEntity


@dataclass(frozen=True, kw_only=True)
class ConfigSwitchDescription(SwitchEntityDescription):
    path: str  # dotted key inside configuration
    on_value: Any = True
    off_value: Any = False


SWITCHES = (
    ConfigSwitchDescription(key="child_lock", path="childLock", on_value=1, off_value=0, icon="mdi:lock"),
    ConfigSwitchDescription(key="extra_wash", path="binaryElements.EXTRA_WASH", icon="mdi:water-plus"),
    ConfigSwitchDescription(key="extra_shake", path="binaryElements.EXTRA_SHAKE", icon="mdi:vibrate"),
    ConfigSwitchDescription(key="extra_dry", path="extraDry", icon="mdi:fan-plus"),
)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        ConfigSwitch(coordinator, mid, desc)
        for mid, g in coordinator.data.items()
        for desc in SWITCHES
        if g.config_get(desc.path) is not None
    )


class ConfigSwitch(CatGenieEntity, SwitchEntity):
    entity_description: ConfigSwitchDescription
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, mid, desc: ConfigSwitchDescription) -> None:
        super().__init__(coordinator, mid, desc.key)
        self.entity_description = desc

    @property
    def is_on(self) -> bool | None:
        val = self.genie.config_get(self.entity_description.path)
        return None if val is None else bool(val)

    async def _set(self, on: bool) -> None:
        d = self.entity_description
        cfg = self.genie.config_with(d.path, d.on_value if on else d.off_value)
        await self.coordinator.async_set_configuration(self._mid, cfg)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
