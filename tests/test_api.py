"""Tests for the RWS API response parsing."""

from __future__ import annotations

from datetime import UTC, datetime

from aiohttp import ClientError
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.rws_watertemperature.api import (
    RwsApiError,
    RwsClient,
    RwsConnectionError,
    haversine_km,
    latest_observations,
    locations_with_quantity,
)
from custom_components.rws_watertemperature.const import (
    CATALOG_URL,
    OBSERVATIONS_URL,
    QUANTITIES,
    QUANTITY_TEMPERATURE,
    QUANTITY_WATER_LEVEL,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .conftest import load_fixture


def test_locations_with_quantity() -> None:
    """The catalog join keeps only locations with the requested series."""
    catalog = load_fixture("catalog.json")
    temperature = locations_with_quantity(catalog, QUANTITIES[QUANTITY_TEMPERATURE])
    assert sorted(loc.code for loc in temperature) == [
        "geen.data",
        "lobith",
        "maarssen.kanaal",
        "oud.zwemwater",
    ]
    level = locations_with_quantity(catalog, QUANTITIES[QUANTITY_WATER_LEVEL])
    assert sorted(loc.code for loc in level) == ["alleen.waterstand", "maarssen.kanaal"]


def test_latest_observations() -> None:
    """The newest valid reading wins per location."""
    latest = latest_observations(load_fixture("observations_temperature.json"))
    assert latest["maarssen.kanaal"].value == 16.8
    assert latest["maarssen.kanaal"].observed_at == datetime(
        2026, 9, 29, 11, 50, tzinfo=UTC
    )
    # The 999999999 "missing" sentinel is skipped.
    assert latest["lobith"].value == 17.9
    assert latest_observations({}) == {}


def test_haversine() -> None:
    """Distance is roughly right for Utrecht to Lobith."""
    assert haversine_km(52.09, 5.12, 51.855, 6.106) == pytest.approx(72.4, abs=0.5)


async def test_client_http_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """HTTP errors become RwsApiError."""
    aioclient_mock.post(OBSERVATIONS_URL, status=500, text="boom")
    client = RwsClient(async_get_clientsession(hass))
    with pytest.raises(RwsApiError):
        await client.async_get_latest(QUANTITIES[QUANTITY_TEMPERATURE], ["lobith"])


async def test_client_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Timeouts and client errors become RwsConnectionError."""
    aioclient_mock.post(CATALOG_URL, exc=ClientError)
    client = RwsClient(async_get_clientsession(hass))
    with pytest.raises(RwsConnectionError):
        await client.async_get_catalog()


async def test_client_invalid_json(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A non-JSON body becomes RwsApiError."""
    aioclient_mock.post(CATALOG_URL, text="<html>maintenance</html>")
    client = RwsClient(async_get_clientsession(hass))
    with pytest.raises(RwsApiError):
        await client.async_get_catalog()


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (204, None),
        (200, {"Succesvol": False, "Foutmelding": "Geen gegevens gevonden!"}),
    ],
)
async def test_client_no_data(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    status: int,
    body: dict | None,
) -> None:
    """'No data' answers are an empty result, not an error."""
    aioclient_mock.post(OBSERVATIONS_URL, status=status, json=body)
    client = RwsClient(async_get_clientsession(hass))
    assert await client.async_get_latest(QUANTITIES[QUANTITY_TEMPERATURE], ["x"]) == {}


async def test_client_no_codes(hass: HomeAssistant) -> None:
    """Asking for no locations does not hit the API."""
    client = RwsClient(async_get_clientsession(hass))
    assert await client.async_get_latest(QUANTITIES[QUANTITY_TEMPERATURE], []) == {}
