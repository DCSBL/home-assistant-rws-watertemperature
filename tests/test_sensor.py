"""Tests for the Rijkswaterstaat water temperature sensors and setup."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.rws_watertemperature.const import (
    ATTRIBUTION,
    DOMAIN,
    OBSERVATIONS_URL,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_sensors(
    hass: HomeAssistant,
    rws_api: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Latest readings become sensor states on one device per location."""
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    state = hass.states.get("sensor.maarssen_kanaal_water_temperature")
    assert state.state == "16.8"
    assert state.attributes["unit_of_measurement"] == "°C"
    assert state.attributes["device_class"] == "temperature"
    assert state.attributes["state_class"] == "measurement"
    assert state.attributes["observed_at"] == "2026-09-29T12:50:00+01:00"
    assert state.attributes["latitude"] == 52.137
    assert state.attributes["longitude"] == 5.03
    assert state.attributes["attribution"] == ATTRIBUTION

    state = hass.states.get("sensor.maarssen_kanaal_water_level")
    assert state.state == "-40.0"
    assert state.attributes["unit_of_measurement"] == "cm"

    state = hass.states.get("sensor.maarssen_kanaal_last_measurement")
    assert state.state == "2026-09-29T11:50:00+00:00"
    entity = entity_registry.async_get("sensor.maarssen_kanaal_last_measurement")
    assert entity.entity_category == "diagnostic"
    assert entity.unique_id == "maarssen.kanaal_last_measurement"

    device = device_registry.async_get_device(identifiers={(DOMAIN, "maarssen.kanaal")})
    assert device.name == "Maarssen kanaal"
    assert device.manufacturer == "Rijkswaterstaat"
    assert device.entry_type is dr.DeviceEntryType.SERVICE


async def test_stale_reading_unavailable(
    hass: HomeAssistant, rws_api: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """A reading older than 48 hours is not shown, but its timestamp is."""
    await _setup(hass, config_entry)

    # Lobith's latest reading is four days old; the 999999999 sentinel is ignored.
    assert hass.states.get("sensor.lobith_water_temperature").state == STATE_UNAVAILABLE
    assert (
        hass.states.get("sensor.lobith_last_measurement").state
        == "2026-09-25T09:00:00+00:00"
    )
    # No water level series at Lobith.
    assert hass.states.get("sensor.lobith_water_level").state == STATE_UNAVAILABLE


async def test_update_failure(
    hass: HomeAssistant,
    rws_api: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Sensors become unavailable when a refresh fails and recover afterwards."""
    await _setup(hass, config_entry)
    state_id = "sensor.maarssen_kanaal_water_temperature"
    assert hass.states.get(state_id).state == "16.8"

    mocks = list(rws_api._mocks)
    rws_api.clear_requests()
    rws_api.post(OBSERVATIONS_URL, status=500, text="boom")
    freezer.tick(timedelta(minutes=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(state_id).state == STATE_UNAVAILABLE

    rws_api.clear_requests()
    rws_api._mocks.extend(mocks)
    freezer.tick(timedelta(minutes=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(state_id).state == "16.8"
