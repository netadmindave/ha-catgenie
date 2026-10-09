"""Base entity."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import CatGenieCoordinator
from .models import CatGenie


class CatGenieEntity(CoordinatorEntity[CatGenieCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: CatGenieCoordinator, manufacturer_id: str, key: str) -> None:
        super().__init__(coordinator)
        self._mid = manufacturer_id
        self._attr_unique_id = f"{manufacturer_id}_{key}"
        self._attr_translation_key = key
        genie = self.genie
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, manufacturer_id)},
            connections={(CONNECTION_NETWORK_MAC, genie.mac)} if genie.mac else set(),
            manufacturer=MANUFACTURER,
            model=genie.model,
            name=genie.name,
            serial_number=manufacturer_id,
            sw_version=genie.firmware,
            hw_version=genie.hw_revision,
        )

    @property
    def genie(self) -> CatGenie:
        return self.coordinator.data[self._mid]

    @property
    def available(self) -> bool:
        return super().available and self._mid in (self.coordinator.data or {})
