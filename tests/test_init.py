"""Tests for setting up and unloading the Rijkswaterstaat water temperature integration."""

from __future__ import annotations

import json

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.rws_watertemperature.const import (
    CONF_LOCATIONS,
    CONF_QUANTITIES,
    DOMAIN,
    OBSERVATIONS_URL,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import MAARSSEN


async def test_setup_and_unload(
    hass: HomeAssistant, rws_api: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """The entry loads and unloads cleanly."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_one_bulk_request_per_quantity(
    hass: HomeAssistant, rws_api: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """All locations are fetched in a single request per quantity."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    requests = [call for call in rws_api.mock_calls if str(call[1]) == OBSERVATIONS_URL]
    assert len(requests) == 2  # water temperature + water level
    for _, _, body, _ in requests:
        body = json.loads(body) if isinstance(body, (str, bytes)) else body
        assert [loc["Code"] for loc in body["LocatieLijst"]] == [
            "maarssen.kanaal",
            "lobith",
        ]


async def test_setup_retry_on_connection_error(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """Setup is retried when RWS cannot be reached."""
    aioclient_mock.post(OBSERVATIONS_URL, exc=TimeoutError)
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_retry_on_http_error(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """Setup is retried when RWS answers with a server error."""
    aioclient_mock.post(OBSERVATIONS_URL, status=503, text="unavailable")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_deselected_location_removed(
    hass: HomeAssistant,
    rws_api: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Devices and entities of deselected locations are removed on reload."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert device_registry.async_get_device(identifiers={(DOMAIN, "lobith")})

    hass.config_entries.async_update_entry(
        config_entry, options={CONF_LOCATIONS: [MAARSSEN], CONF_QUANTITIES: []}
    )
    await hass.async_block_till_done()

    assert device_registry.async_get_device(identifiers={(DOMAIN, "lobith")}) is None
    assert entity_registry.async_get("sensor.lobith_water_temperature") is None
    assert entity_registry.async_get("sensor.maarssen_kanaal_water_level") is None
    assert entity_registry.async_get("sensor.maarssen_kanaal_water_temperature")
