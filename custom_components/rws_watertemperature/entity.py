"""Base entity for the Rijkswaterstaat water temperature integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import RwsObservation
from .const import ATTRIBUTION, DOMAIN, LOC_CODE, LOC_NAME
from .coordinator import RwsCoordinator


class RwsEntity(CoordinatorEntity[RwsCoordinator]):
    """An entity belonging to one RWS measuring location (one device per location)."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: RwsCoordinator, location: dict[str, Any], key: str
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._code: str = location[LOC_CODE]
        self._location = location
        self._attr_unique_id = f"{self._code}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._code)},
            name=location[LOC_NAME],
            manufacturer="Rijkswaterstaat",
            model=self._code,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://waterinfo.rws.nl/",
        )

    def _observation(self, quantity: str) -> RwsObservation | None:
        """Latest observation of ``quantity`` at this location."""
        return (self.coordinator.data or {}).get(quantity, {}).get(self._code)
