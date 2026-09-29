"""Sensors for the Rijkswaterstaat water temperature integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    EntityCategory,
    UnitOfLength,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import RwsObservation
from .const import (
    ATTRIBUTION,
    CONF_LOCATIONS,
    DOMAIN,
    LAST_MEASUREMENT_KEY,
    LOC_CODE,
    LOC_LATITUDE,
    LOC_LONGITUDE,
    LOC_NAME,
    MAX_READING_AGE,
    QUANTITY_TEMPERATURE,
    QUANTITY_WATER_LEVEL,
)
from .coordinator import RwsConfigEntry, RwsCoordinator

# Coordinator-based entities: updates are centralised, no per-entity limit needed.
PARALLEL_UPDATES = 0

ATTR_OBSERVED_AT = "observed_at"


@dataclass(frozen=True, kw_only=True)
class RwsSensorEntityDescription(SensorEntityDescription):
    """Describes an RWS measurement sensor."""

    quantity: str


MEASUREMENT_SENSORS: dict[str, RwsSensorEntityDescription] = {
    QUANTITY_TEMPERATURE: RwsSensorEntityDescription(
        key=QUANTITY_TEMPERATURE,
        translation_key="water_temperature",
        quantity=QUANTITY_TEMPERATURE,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    QUANTITY_WATER_LEVEL: RwsSensorEntityDescription(
        key=QUANTITY_WATER_LEVEL,
        translation_key="water_level",
        quantity=QUANTITY_WATER_LEVEL,
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
}

LAST_MEASUREMENT_SENSOR = RwsSensorEntityDescription(
    key=LAST_MEASUREMENT_KEY,
    translation_key="last_measurement",
    quantity=QUANTITY_TEMPERATURE,
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RwsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up RWS sensors from a config entry."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []
    for location in entry.options.get(CONF_LOCATIONS, []):
        entities.extend(
            RwsMeasurementSensor(coordinator, location, MEASUREMENT_SENSORS[quantity])
            for quantity in coordinator.quantities
        )
        entities.append(
            RwsLastMeasurementSensor(coordinator, location, LAST_MEASUREMENT_SENSOR)
        )
    async_add_entities(entities)


class RwsEntity(CoordinatorEntity[RwsCoordinator], SensorEntity):
    """Base entity for one quantity at one RWS location."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    entity_description: RwsSensorEntityDescription

    def __init__(
        self,
        coordinator: RwsCoordinator,
        location: dict[str, Any],
        description: RwsSensorEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._code: str = location[LOC_CODE]
        self._location = location
        self._attr_unique_id = f"{self._code}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._code)},
            name=location[LOC_NAME],
            manufacturer="Rijkswaterstaat",
            model=self._code,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://waterinfo.rws.nl/",
        )

    @property
    def observation(self) -> RwsObservation | None:
        """Latest observation for this entity's quantity and location."""
        return (
            (self.coordinator.data or {})
            .get(self.entity_description.quantity, {})
            .get(self._code)
        )


class RwsMeasurementSensor(RwsEntity):
    """The latest measured value; unavailable when the reading is stale."""

    @property
    def available(self) -> bool:
        """Only available with a reading that is recent enough."""
        obs = self.observation
        return (
            super().available
            and obs is not None
            and dt_util.utcnow() - obs.observed_at <= MAX_READING_AGE
        )

    @property
    def native_value(self) -> float | None:
        """Return the measured value."""
        obs = self.observation
        return obs.value if obs else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Measurement time and station coordinates."""
        obs = self.observation
        return {
            ATTR_OBSERVED_AT: obs.observed_at.isoformat() if obs else None,
            ATTR_LATITUDE: self._location[LOC_LATITUDE],
            ATTR_LONGITUDE: self._location[LOC_LONGITUDE],
        }


class RwsLastMeasurementSensor(RwsEntity):
    """When RWS last measured water temperature at this location (even if stale)."""

    @property
    def available(self) -> bool:
        """Available whenever there is any reading."""
        return super().available and self.observation is not None

    @property
    def native_value(self) -> datetime | None:
        """Return the measurement timestamp."""
        obs = self.observation
        return obs.observed_at if obs else None
