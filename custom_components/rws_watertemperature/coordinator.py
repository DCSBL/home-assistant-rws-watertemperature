"""Data update coordinator for the Rijkswaterstaat water temperature integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RwsClient, RwsError, RwsObservation
from .const import (
    CONF_LOCATIONS,
    CONF_QUANTITIES,
    DOMAIN,
    LOC_CODE,
    QUANTITIES,
    QUANTITY_TEMPERATURE,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

type RwsConfigEntry = ConfigEntry[RwsCoordinator]

# quantity key -> location code -> latest observation
type RwsData = dict[str, dict[str, RwsObservation]]


def entry_quantities(entry: ConfigEntry) -> list[str]:
    """Quantities enabled for an entry; water temperature is always included."""
    extra = [q for q in entry.options.get(CONF_QUANTITIES, []) if q in QUANTITIES]
    return [QUANTITY_TEMPERATURE, *(q for q in extra if q != QUANTITY_TEMPERATURE)]


class RwsCoordinator(DataUpdateCoordinator[RwsData]):
    """Fetch the latest readings for all configured locations in one go per quantity."""

    config_entry: RwsConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: RwsConfigEntry, client: RwsClient
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.codes: list[str] = [
            loc[LOC_CODE] for loc in entry.options.get(CONF_LOCATIONS, [])
        ]
        self.quantities = entry_quantities(entry)

    async def _async_update_data(self) -> RwsData:
        data: RwsData = {}
        try:
            for key in self.quantities:
                data[key] = await self.client.async_get_latest(
                    QUANTITIES[key], self.codes
                )
        except RwsError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        return data
