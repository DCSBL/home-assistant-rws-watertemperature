"""Tests for the Rijkswaterstaat water temperature config flow."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.rws_watertemperature.config_flow import (
    CONF_POINT,
    CONF_QUERY,
)
from custom_components.rws_watertemperature.const import (
    CATALOG_URL,
    CONF_LOCATIONS,
    CONF_QUANTITIES,
    DOMAIN,
    GEOCODE_URL,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import LOBITH, MAARSSEN


def _offered(result) -> list[tuple[str, str]]:
    schema = result["data_schema"].schema
    key = next(k for k in schema if k == CONF_LOCATIONS)
    return [(o["value"], o["label"]) for o in schema[key].config["options"]]


def _geocode(aioclient_mock: AiohttpClientMocker, lon: float, lat: float) -> None:
    aioclient_mock.get(
        GEOCODE_URL,
        json={
            "response": {
                "docs": [
                    {
                        "weergavenaam": "Nesselande, Rotterdam",
                        "centroide_ll": f"POINT({lon} {lat})",
                    }
                ]
            }
        },
    )


async def _start(hass: HomeAssistant, step: str):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["search_name", "search_location"]
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


async def _search_home(hass: HomeAssistant):
    """Search around the home point."""
    result = await _start(hass, "search_location")
    assert result["step_id"] == "search_location"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_POINT: {"latitude": 52.09, "longitude": 5.12}},
    )


async def test_search_location_flow(
    hass: HomeAssistant, rws_api: AiohttpClientMocker
) -> None:
    """Only recently reporting water temperature stations are offered, nearest first."""
    result = await _search_home(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "select"
    # Stale (2015), no-data, air-temperature and water-level-only locations are left out.
    assert _offered(result) == [
        ("maarssen.kanaal", "Maarssen kanaal (8.1 km)"),
        ("lobith", "Lobith (72.4 km)"),
    ]
    # The nearest station is preselected.
    assert result["data_schema"]({}) == {
        CONF_LOCATIONS: ["maarssen.kanaal"],
        CONF_QUANTITIES: [],
    }

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_LOCATIONS: ["maarssen.kanaal"], CONF_QUANTITIES: ["water_level"]},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Rijkswaterstaat"
    assert result["data"] == {}
    assert result["options"] == {
        CONF_LOCATIONS: [MAARSSEN],
        CONF_QUANTITIES: ["water_level"],
    }


async def test_search_location_far_from_home(
    hass: HomeAssistant, rws_api: AiohttpClientMocker
) -> None:
    """A point elsewhere ranks stations by distance to that point."""
    result = await _start(hass, "search_location")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_POINT: {"latitude": 51.86, "longitude": 6.1}},
    )
    assert [code for code, _ in _offered(result)] == ["lobith", "maarssen.kanaal"]
    assert result["data_schema"]({})[CONF_LOCATIONS] == ["lobith"]


async def test_search_by_station_name(
    hass: HomeAssistant, rws_api: AiohttpClientMocker
) -> None:
    """A station name is matched case- and accent-insensitively without geocoding."""
    result = await _start(hass, "search_name")
    assert result["step_id"] == "search_name"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_QUERY: "  LÖBITH "}
    )
    assert result["step_id"] == "select"
    assert [code for code, _ in _offered(result)] == ["lobith"]
    assert result["data_schema"]({})[CONF_LOCATIONS] == ["lobith"]
    assert not [c for c in rws_api.mock_calls if c[1] == "GET"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LOCATIONS: ["lobith"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {CONF_LOCATIONS: [LOBITH], CONF_QUANTITIES: []}


async def test_search_by_place_name(
    hass: HomeAssistant, rws_api: AiohttpClientMocker
) -> None:
    """A place without a station is geocoded and the best nearby station preselected."""
    _geocode(rws_api, 6.09, 51.85)
    result = await _start(hass, "search_name")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_QUERY: "Nesselande"}
    )
    assert result["step_id"] == "select"
    assert result["description_placeholders"] == {"search": "Nesselande, Rotterdam"}
    assert [code for code, _ in _offered(result)] == ["lobith", "maarssen.kanaal"]
    assert result["data_schema"]({})[CONF_LOCATIONS] == ["lobith"]


async def test_search_by_name_stale_station_falls_back_to_place(
    hass: HomeAssistant, rws_api: AiohttpClientMocker
) -> None:
    """A station that no longer reports is skipped in favour of the place lookup."""
    _geocode(rws_api, 5.1, 52.1)
    result = await _start(hass, "search_name")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_QUERY: "Oud zwemwater"}
    )
    assert result["step_id"] == "select"
    assert "oud.zwemwater" not in [code for code, _ in _offered(result)]


async def test_search_place_not_found(
    hass: HomeAssistant, rws_api: AiohttpClientMocker
) -> None:
    """An unknown place shows an error and lets the user try again."""
    rws_api.get(GEOCODE_URL, json={"response": {"docs": []}})
    result = await _start(hass, "search_name")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_QUERY: "Nergenshuizen"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "search_name"
    assert result["errors"] == {"base": "place_not_found"}


async def test_search_geocoder_unreachable(
    hass: HomeAssistant, rws_api: AiohttpClientMocker
) -> None:
    """The flow aborts when the geocoder cannot be reached."""
    rws_api.get(GEOCODE_URL, exc=TimeoutError)
    result = await _start(hass, "search_name")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_QUERY: "Nesselande"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_select_requires_location(
    hass: HomeAssistant, rws_api: AiohttpClientMocker
) -> None:
    """Submitting without a location shows an error and can recover."""
    result = await _search_home(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LOCATIONS: []}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_LOCATIONS: "no_locations_selected"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LOCATIONS: ["lobith"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {CONF_LOCATIONS: [LOBITH], CONF_QUANTITIES: []}


async def test_search_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The flow aborts when RWS cannot be reached."""
    aioclient_mock.post(CATALOG_URL, exc=TimeoutError)
    result = await _search_home(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_search_no_stations(
    hass: HomeAssistant,
    rws_api: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The search reports an error when no station reported in the last 90 days."""
    freezer.move_to("2030-01-01T00:00:00+00:00")
    result = await _search_home(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "search_location"
    assert result["errors"] == {"base": "no_stations"}


async def test_single_instance(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Only one entry can be created."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] in ("already_configured", "single_instance_allowed")


async def test_options_flow(
    hass: HomeAssistant, rws_api: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """The options flow edits the current selection."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["search_name", "search_location", "keep"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "keep"}
    )
    assert result["step_id"] == "select"
    assert [code for code, _ in _offered(result)] == ["maarssen.kanaal", "lobith"]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_LOCATIONS: ["lobith"], CONF_QUANTITIES: []}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert config_entry.options == {CONF_LOCATIONS: [LOBITH], CONF_QUANTITIES: []}
    assert hass.states.get("sensor.maarssen_kanaal_water_temperature") is None
    assert hass.states.get("sensor.lobith_water_temperature") is not None
    # The water level extra was deselected.
    assert hass.states.get("sensor.lobith_water_level") is None


async def test_options_flow_add_station_by_place(
    hass: HomeAssistant, rws_api: AiohttpClientMocker
) -> None:
    """A new search adds a station while keeping the configured one selected."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        options={CONF_LOCATIONS: [MAARSSEN], CONF_QUANTITIES: []},
    )
    entry.add_to_hass(hass)
    _geocode(rws_api, 6.09, 51.85)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "search_name"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_QUERY: "Nesselande"}
    )
    assert result["data_schema"]({})[CONF_LOCATIONS] == ["maarssen.kanaal", "lobith"]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_LOCATIONS: ["maarssen.kanaal", "lobith"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_LOCATIONS] == [MAARSSEN, LOBITH]


async def test_options_flow_keeps_stale_selected_station(
    hass: HomeAssistant, rws_api: AiohttpClientMocker
) -> None:
    """A configured station that went stale is still offered in a new search."""
    stale = {
        "code": "oud.zwemwater",
        "name": "Oud zwemwater",
        "latitude": 52.1,
        "longitude": 5.1,
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        options={CONF_LOCATIONS: [stale], CONF_QUANTITIES: []},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "search_location"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_POINT: {"latitude": 52.09, "longitude": 5.12}}
    )
    assert "oud.zwemwater" in [code for code, _ in _offered(result)]
