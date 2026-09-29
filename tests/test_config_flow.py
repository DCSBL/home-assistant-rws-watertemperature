"""Tests for the Rijkswaterstaat water temperature config flow."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.rws_watertemperature.const import (
    CATALOG_URL,
    CONF_LOCATIONS,
    CONF_QUANTITIES,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import LOBITH, MAARSSEN


def _offered(result) -> list[tuple[str, str]]:
    schema = result["data_schema"].schema
    key = next(k for k in schema if k == CONF_LOCATIONS)
    return [(o["value"], o["label"]) for o in schema[key].config["options"]]


async def test_user_flow(hass: HomeAssistant, rws_api: AiohttpClientMocker) -> None:
    """Only recently reporting water temperature stations are offered, nearest first."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    # Stale (2015), no-data, air-temperature and water-level-only locations are left out.
    assert _offered(result) == [
        ("maarssen.kanaal", "Maarssen kanaal (8.1 km)"),
        ("lobith", "Lobith (72.4 km)"),
    ]

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


async def test_user_flow_requires_location(
    hass: HomeAssistant, rws_api: AiohttpClientMocker
) -> None:
    """Submitting without a location shows an error and can recover."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
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


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The flow aborts when RWS cannot be reached."""
    aioclient_mock.post(CATALOG_URL, exc=TimeoutError)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_user_flow_no_stations(
    hass: HomeAssistant,
    rws_api: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The flow aborts when no nearby station reported in the last 90 days."""
    freezer.move_to("2030-01-01T00:00:00+00:00")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_stations"


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
    """The options flow changes the selection and keeps configured stations offered."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
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


async def test_options_flow_keeps_stale_selected_station(
    hass: HomeAssistant, rws_api: AiohttpClientMocker
) -> None:
    """A configured station that went stale is still offered in the options flow."""
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
    assert "oud.zwemwater" in [code for code, _ in _offered(result)]
