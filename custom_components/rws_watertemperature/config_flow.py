"""Config flow for the Rijkswaterstaat water temperature integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util import dt as dt_util

from .api import RwsClient, RwsError, RwsLocation, haversine_km
from .const import (
    CONF_LOCATIONS,
    CONF_QUANTITIES,
    DOMAIN,
    EXTRA_QUANTITIES,
    LOC_CODE,
    LOC_LATITUDE,
    LOC_LONGITUDE,
    LOC_NAME,
    MAX_STATION_AGE,
    NEARBY_CANDIDATES,
    QUANTITIES,
    QUANTITY_TEMPERATURE,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class _Candidate:
    location: RwsLocation
    distance_km: float


async def _async_candidates(
    hass: HomeAssistant, keep: list[dict[str, Any]]
) -> list[_Candidate]:
    """Nearest water temperature stations that reported recently, nearest first.

    Locations in ``keep`` (the current selection) are always included so the
    options flow never silently drops a configured station.
    """
    client = RwsClient(async_get_clientsession(hass))
    temperature = QUANTITIES[QUANTITY_TEMPERATURE]
    home_lat, home_lon = hass.config.latitude, hass.config.longitude

    def distance(loc: RwsLocation) -> float:
        return haversine_km(home_lat, home_lon, loc.latitude, loc.longitude)

    locations = sorted(await client.async_get_locations(temperature), key=distance)
    nearest = locations[:NEARBY_CANDIDATES]
    latest = await client.async_get_latest(temperature, [loc.code for loc in nearest])
    cutoff = dt_util.utcnow() - MAX_STATION_AGE
    fresh = {
        loc.code: loc
        for loc in nearest
        if loc.code in latest and latest[loc.code].observed_at >= cutoff
    }
    for stored in keep:
        if stored[LOC_CODE] not in fresh:
            fresh[stored[LOC_CODE]] = RwsLocation(
                code=stored[LOC_CODE],
                name=stored[LOC_NAME],
                latitude=stored[LOC_LATITUDE],
                longitude=stored[LOC_LONGITUDE],
            )
    return sorted(
        (_Candidate(location=loc, distance_km=distance(loc)) for loc in fresh.values()),
        key=lambda candidate: candidate.distance_km,
    )


def _schema(
    candidates: list[_Candidate],
    selected_codes: list[str],
    selected_quantities: list[str],
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_LOCATIONS, default=selected_codes): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(
                            value=c.location.code,
                            label=f"{c.location.name} ({c.distance_km:.1f} km)",
                        )
                        for c in candidates
                    ],
                    multiple=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_QUANTITIES, default=selected_quantities): SelectSelector(
                SelectSelectorConfig(
                    options=EXTRA_QUANTITIES,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                    translation_key=CONF_QUANTITIES,
                )
            ),
        }
    )


def _options_from_input(
    candidates: list[_Candidate], user_input: dict[str, Any]
) -> dict[str, Any]:
    by_code = {c.location.code: c.location for c in candidates}
    return {
        CONF_LOCATIONS: [
            {
                LOC_CODE: loc.code,
                LOC_NAME: loc.name,
                LOC_LATITUDE: loc.latitude,
                LOC_LONGITUDE: loc.longitude,
            }
            for code in user_input[CONF_LOCATIONS]
            if (loc := by_code.get(code)) is not None
        ],
        CONF_QUANTITIES: [
            q for q in user_input.get(CONF_QUANTITIES, []) if q in EXTRA_QUANTITIES
        ],
    }


class RwsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Rijkswaterstaat water temperature."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._candidates: list[_Candidate] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick nearby stations."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_LOCATIONS):
                errors[CONF_LOCATIONS] = "no_locations_selected"
            else:
                return self.async_create_entry(
                    title="Rijkswaterstaat",
                    data={},
                    options=_options_from_input(self._candidates, user_input),
                )

        if not self._candidates:
            try:
                self._candidates = await _async_candidates(self.hass, [])
            except RwsError:
                _LOGGER.exception("Could not fetch RWS stations")
                return self.async_abort(reason="cannot_connect")
            if not self._candidates:
                return self.async_abort(reason="no_stations")

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(self._candidates, [], []),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> RwsOptionsFlow:
        """Create the options flow."""
        return RwsOptionsFlow()


class RwsOptionsFlow(OptionsFlow):
    """Change the selected stations and quantities."""

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._candidates: list[_Candidate] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the station selection."""
        current_locations: list[dict[str, Any]] = self.config_entry.options.get(
            CONF_LOCATIONS, []
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_LOCATIONS):
                errors[CONF_LOCATIONS] = "no_locations_selected"
            else:
                return self.async_create_entry(
                    data=_options_from_input(self._candidates, user_input)
                )

        if not self._candidates:
            try:
                self._candidates = await _async_candidates(self.hass, current_locations)
            except RwsError:
                _LOGGER.exception("Could not fetch RWS stations")
                return self.async_abort(reason="cannot_connect")

        return self.async_show_form(
            step_id="init",
            data_schema=_schema(
                self._candidates,
                [loc[LOC_CODE] for loc in current_locations],
                self.config_entry.options.get(CONF_QUANTITIES, []),
            ),
            errors=errors,
        )
