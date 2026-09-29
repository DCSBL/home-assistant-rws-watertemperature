"""Config flow for the Rijkswaterstaat water temperature integration.

The user finds stations in one of two ways: by name (a station name, or any Dutch
place name that is resolved to coordinates) or by picking a point on the map. Either
way the nearest stations that reported recently are offered.
"""

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
    LocationSelector,
    LocationSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
from homeassistant.util import dt as dt_util

from .api import RwsClient, RwsError, RwsLocation, haversine_km, normalize_name
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

CONF_QUERY = "query"
CONF_POINT = "location"


@dataclass(frozen=True, kw_only=True)
class _Candidate:
    location: RwsLocation
    distance_km: float


def _stored_locations(stored: list[dict[str, Any]]) -> list[RwsLocation]:
    return [
        RwsLocation(
            code=item[LOC_CODE],
            name=item[LOC_NAME],
            latitude=item[LOC_LATITUDE],
            longitude=item[LOC_LONGITUDE],
        )
        for item in stored
    ]


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


class _StationPickerMixin:
    """Shared search-then-select steps of the config and options flow."""

    hass: HomeAssistant
    # Steps offered in the first menu, set by the concrete flow.
    _menu_options: tuple[str, ...]

    def _init_picker(self) -> None:
        self._stations: list[RwsLocation] | None = None
        self._candidates: list[_Candidate] = []
        self._preselected: list[str] = []
        self._search_label = ""

    # Provided by the concrete flow.
    def _current_locations(self) -> list[dict[str, Any]]:
        return []

    def _current_quantities(self) -> list[str]:
        return []

    async def _async_finish(self, options: dict[str, Any]) -> ConfigFlowResult:
        raise NotImplementedError

    async def _async_menu(self, step_id: str) -> ConfigFlowResult:
        return self.async_show_menu(  # type: ignore[attr-defined,no-any-return]
            step_id=step_id, menu_options=list(self._menu_options)
        )

    async def _async_stations(self) -> list[RwsLocation]:
        """All stations that have a water temperature series (fetched once)."""
        if self._stations is None:
            client = RwsClient(async_get_clientsession(self.hass))
            self._stations = await client.async_get_locations(
                QUANTITIES[QUANTITY_TEMPERATURE]
            )
        return self._stations

    async def _async_set_candidates(
        self,
        pool: list[RwsLocation],
        latitude: float,
        longitude: float,
        *,
        preselect_nearest: bool,
    ) -> bool:
        """Offer the nearest recently reporting stations of ``pool``.

        Stations already selected are always kept so a search never silently drops
        one. Returns False when the search found nothing to offer.
        """
        client = RwsClient(async_get_clientsession(self.hass))
        temperature = QUANTITIES[QUANTITY_TEMPERATURE]

        def distance(loc: RwsLocation) -> float:
            return haversine_km(latitude, longitude, loc.latitude, loc.longitude)

        nearest = sorted(pool, key=distance)[:NEARBY_CANDIDATES]
        latest = await client.async_get_latest(
            temperature, [loc.code for loc in nearest]
        )
        cutoff = dt_util.utcnow() - MAX_STATION_AGE
        fresh = [
            loc
            for loc in nearest
            if loc.code in latest and latest[loc.code].observed_at >= cutoff
        ]
        if not fresh:
            return False
        kept = _stored_locations(self._current_locations())
        kept_codes = [loc.code for loc in kept]
        offered = {loc.code: loc for loc in fresh}
        offered.update({loc.code: loc for loc in kept})
        self._candidates = sorted(
            (
                _Candidate(location=loc, distance_km=distance(loc))
                for loc in offered.values()
            ),
            key=lambda candidate: candidate.distance_km,
        )
        self._preselected = kept_codes + (
            [fresh[0].code]
            if preselect_nearest and fresh[0].code not in kept_codes
            else []
        )
        return True

    async def async_step_search_name(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Search by station name, falling back to any Dutch place name."""
        errors: dict[str, str] = {}
        if user_input is not None:
            query = user_input[CONF_QUERY].strip()
            try:
                result = await self._async_search_name(query)
            except RwsError:
                _LOGGER.exception("Could not search RWS stations")
                return self.async_abort(reason="cannot_connect")  # type: ignore[attr-defined,no-any-return]
            if isinstance(result, str):
                errors["base"] = result
            else:
                return await self.async_step_select()
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="search_name",
            data_schema=vol.Schema({vol.Required(CONF_QUERY): TextSelector()}),
            errors=errors,
        )

    async def _async_search_name(self, query: str) -> str | None:
        """Fill the candidates for ``query``; return an error key when none found."""
        if not query:
            return "place_not_found"
        stations = await self._async_stations()
        wanted = normalize_name(query)
        home = (self.hass.config.latitude, self.hass.config.longitude)
        matches = [
            loc for loc in stations if wanted and wanted in normalize_name(loc.name)
        ]
        if matches and await self._async_set_candidates(
            matches, *home, preselect_nearest=len(matches) == 1
        ):
            self._search_label = query
            return None
        # No station carries that name (or none reported recently): treat the query
        # as a place and look for the best station around it.
        place = await RwsClient(async_get_clientsession(self.hass)).async_geocode(query)
        if place is None:
            return "place_not_found"
        if not await self._async_set_candidates(
            stations, place.latitude, place.longitude, preselect_nearest=True
        ):
            return "no_stations"
        self._search_label = place.name
        return None

    async def async_step_search_location(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Search around a point on the map."""
        errors: dict[str, str] = {}
        if user_input is not None:
            point = user_input[CONF_POINT]
            latitude, longitude = point["latitude"], point["longitude"]
            try:
                found = await self._async_set_candidates(
                    await self._async_stations(),
                    latitude,
                    longitude,
                    preselect_nearest=True,
                )
            except RwsError:
                _LOGGER.exception("Could not search RWS stations")
                return self.async_abort(reason="cannot_connect")  # type: ignore[attr-defined,no-any-return]
            if found:
                self._search_label = f"{latitude:.4f}, {longitude:.4f}"
                return await self.async_step_select()
            errors["base"] = "no_stations"
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="search_location",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POINT,
                        default={
                            "latitude": self.hass.config.latitude,
                            "longitude": self.hass.config.longitude,
                        },
                    ): LocationSelector(LocationSelectorConfig(radius=False))
                }
            ),
            errors=errors,
        )

    async def async_step_keep(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Only edit the current selection (options flow)."""
        current = self._current_locations()
        self._candidates = [
            _Candidate(
                location=loc,
                distance_km=haversine_km(
                    self.hass.config.latitude,
                    self.hass.config.longitude,
                    loc.latitude,
                    loc.longitude,
                ),
            )
            for loc in _stored_locations(current)
        ]
        self._preselected = [item[LOC_CODE] for item in current]
        self._search_label = ""
        return await self.async_step_select()

    async def async_step_select(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick stations from the search result."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_LOCATIONS):
                errors[CONF_LOCATIONS] = "no_locations_selected"
            else:
                return await self._async_finish(
                    _options_from_input(self._candidates, user_input)
                )
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="select",
            data_schema=_schema(
                self._candidates, self._preselected, self._current_quantities()
            ),
            description_placeholders={"search": self._search_label},
            errors=errors,
        )


class RwsConfigFlow(_StationPickerMixin, ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Rijkswaterstaat water temperature."""

    VERSION = 1
    _menu_options = ("search_name", "search_location")

    def __init__(self) -> None:
        """Initialize the flow."""
        self._init_picker()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose how to look for stations."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return await self._async_menu("user")

    async def _async_finish(self, options: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(
            title="Rijkswaterstaat", data={}, options=options
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> RwsOptionsFlow:
        """Create the options flow."""
        return RwsOptionsFlow()


class RwsOptionsFlow(_StationPickerMixin, OptionsFlow):
    """Change the selected stations and quantities."""

    _menu_options = ("search_name", "search_location", "keep")

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._init_picker()

    def _current_locations(self) -> list[dict[str, Any]]:
        return list(self.config_entry.options.get(CONF_LOCATIONS, []))

    def _current_quantities(self) -> list[str]:
        return list(self.config_entry.options.get(CONF_QUANTITIES, []))

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose how to change the stations."""
        return await self._async_menu("init")

    async def _async_finish(self, options: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(data=options)
