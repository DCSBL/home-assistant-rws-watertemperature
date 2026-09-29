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
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import RwsObservation
from .const import (
    CONF_LOCATIONS,
    LAST_MEASUREMENT_KEY,
    LOC_LATITUDE,
    LOC_LONGITUDE,
    MAX_READING_AGE,
    QUANTITY_TEMPERATURE,
    QUANTITY_WATER_LEVEL,
)
from .coordinator import RwsConfigEntry, RwsCoordinator
from .entity import RwsEntity

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


class RwsSensor(RwsEntity, SensorEntity):
    """Base sensor for one quantity at one RWS location."""

    entity_description: RwsSensorEntityDescription

    def __init__(
        self,
        coordinator: RwsCoordinator,
        location: dict[str, Any],
        description: RwsSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, location, description.key)
        self.entity_description = description

    @property
    def observation(self) -> RwsObservation | None:
        """Latest observation for this sensor's quantity and location."""
        return self._observation(self.entity_description.quantity)


class RwsMeasurementSensor(RwsSensor):
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


class RwsLastMeasurementSensor(RwsSensor):
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
