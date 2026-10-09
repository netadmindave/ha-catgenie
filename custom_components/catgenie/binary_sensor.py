"""Binary sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import CatGenieEntity
from .models import CatGenie


@dataclass(frozen=True, kw_only=True)
class GenieBinaryDescription(BinarySensorEntityDescription):
    value: Callable[[CatGenie], bool | None]


BINARY_SENSORS = (
    GenieBinaryDescription(
        key="connected", device_class=BinarySensorDeviceClass.CONNECTIVITY, value=lambda g: g.connected
    ),
    GenieBinaryDescription(
        key="cleaning", device_class=BinarySensorDeviceClass.RUNNING, value=lambda g: g.is_cleaning
    ),
    GenieBinaryDescription(
        key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value=lambda g: bool(g.active_errors) or g.main_error is not None,
    ),
    GenieBinaryDescription(
        key="sani_low", device_class=BinarySensorDeviceClass.PROBLEM, icon="mdi:bottle-tonic-outline",
        value=lambda g: g.sani_low,
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        CatGenieBinarySensor(coordinator, mid, desc) for mid in coordinator.data for desc in BINARY_SENSORS
    )


class CatGenieBinarySensor(CatGenieEntity, BinarySensorEntity):
    entity_description: GenieBinaryDescription

    def __init__(self, coordinator, mid, desc: GenieBinaryDescription) -> None:
        super().__init__(coordinator, mid, desc.key)
        self.entity_description = desc

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value(self.genie)
