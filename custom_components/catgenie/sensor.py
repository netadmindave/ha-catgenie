"""Sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import STATE_NAMES
from .entity import CatGenieEntity
from .models import CatGenie, utc_hms_to_local


@dataclass(frozen=True, kw_only=True)
class GenieSensorDescription(SensorEntityDescription):
    value: Callable[[CatGenie], Any]
    attrs: Callable[[CatGenie], dict[str, Any]] | None = None


def _local_times(values: list[str]) -> list[str]:
    tz = dt_util.get_default_time_zone()
    out = []
    for t in values:
        try:
            out.append(utc_hms_to_local(t, tz))
        except (ValueError, TypeError):
            out.append(t)
    return out


def _dnd(g: CatGenie) -> str | None:
    start, end = g.config_get("dndFrom"), g.config_get("dndTo")
    if not start or not end:
        return None
    a, b = _local_times([start, end])
    return f"{a}-{b}"


SENSORS = (
    GenieSensorDescription(
        key="status",
        icon="mdi:robot-vacuum",
        device_class=SensorDeviceClass.ENUM,
        options=sorted(set(STATE_NAMES.values())),
        value=lambda g: g.state,
        attrs=lambda g: {"state_code": g.state_code, "raw_progress": g.operation.get("progress")},
    ),
    GenieSensorDescription(
        key="progress",
        icon="mdi:progress-clock",
        native_unit_of_measurement=PERCENTAGE,
        value=lambda g: g.progress,
    ),
    GenieSensorDescription(
        key="sani_solution",
        icon="mdi:bottle-tonic-outline",
        native_unit_of_measurement="washes",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda g: g.washes_left,
    ),
    GenieSensorDescription(
        key="last_clean",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda g: g.last_clean,
    ),
    GenieSensorDescription(
        key="errors",
        icon="mdi:alert-circle-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda g: len(g.active_errors),
        attrs=lambda g: {"active_errors": g.active_errors, "main_error": g.main_error},
    ),
    GenieSensorDescription(
        key="schedule",
        icon="mdi:calendar-clock",
        value=lambda g: ", ".join(_local_times(g.schedule_utc)) or "none",
        attrs=lambda g: {"times_local": _local_times(g.schedule_utc), "times_utc": g.schedule_utc},
    ),
    GenieSensorDescription(
        key="do_not_disturb",
        icon="mdi:sleep",
        value=_dnd,
    ),
    GenieSensorDescription(
        key="raw_state",
        icon="mdi:code-json",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value=lambda g: g.state_code,
        attrs=lambda g: dict(g.raw),
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        CatGenieSensor(coordinator, mid, desc) for mid in coordinator.data for desc in SENSORS
    )


class CatGenieSensor(CatGenieEntity, SensorEntity):
    entity_description: GenieSensorDescription

    def __init__(self, coordinator, mid, desc: GenieSensorDescription) -> None:
        super().__init__(coordinator, mid, desc.key)
        self.entity_description = desc

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.genie)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs
        return fn(self.genie) if fn else None
