"""Fixtures for the Rijkswaterstaat water temperature tests.

The JSON fixtures are synthetic but follow the response shape of the RWS
DDAPI20 WaterWebservices as parsed by dcsbl/rppl.
"""

from __future__ import annotations

from collections.abc import Generator
import json
from pathlib import Path
from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.rws_watertemperature.const import (
    CATALOG_URL,
    CONF_LOCATIONS,
    CONF_QUANTITIES,
    DOMAIN,
    OBSERVATIONS_URL,
)
from homeassistant.core import HomeAssistant

FIXTURES = Path(__file__).parent / "fixtures"
NOW = "2026-09-29T12:00:00+00:00"

OBSERVATION_FIXTURES = {
    "T": "observations_temperature.json",
    "WATHTE": "observations_water_level.json",
}

MAARSSEN = {
    "code": "maarssen.kanaal",
    "name": "Maarssen kanaal",
    "latitude": 52.137,
    "longitude": 5.03,
}
LOBITH = {"code": "lobith", "name": "Lobith", "latitude": 51.855, "longitude": 6.106}


def load_fixture(name: str) -> dict[str, Any]:
    """Load a JSON fixture."""
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading the custom integration in every test."""


@pytest.fixture(autouse=True)
def frozen_time(freezer: FrozenDateTimeFactory) -> FrozenDateTimeFactory:
    """Freeze time so fixture timestamps have a stable age."""
    freezer.move_to(NOW)
    return freezer


@pytest.fixture(autouse=True)
async def home_location(hass: HomeAssistant) -> None:
    """Put Home Assistant's home in Utrecht."""
    hass.config.latitude = 52.09
    hass.config.longitude = 5.12


@pytest.fixture
def rws_api(aioclient_mock: AiohttpClientMocker) -> Generator[AiohttpClientMocker]:
    """Mock the RWS catalog and observation endpoints."""

    async def observations(
        method: str, url: URL, data: Any
    ) -> AiohttpClientMockResponse:
        body = json.loads(data) if isinstance(data, (str, bytes)) else data
        grootheid = body["AquoPlusWaarnemingMetadataLijst"][0]["AquoMetadata"][
            "Grootheid"
        ]["Code"]
        requested = {loc["Code"] for loc in body["LocatieLijst"]}
        response = load_fixture(OBSERVATION_FIXTURES[grootheid])
        response["WaarnemingenLijst"] = [
            w
            for w in response["WaarnemingenLijst"]
            if w["Locatie"]["Code"] in requested
        ]
        return AiohttpClientMockResponse(method, url, json=response)

    aioclient_mock.post(CATALOG_URL, json=load_fixture("catalog.json"))
    aioclient_mock.post(OBSERVATIONS_URL, side_effect=observations)
    yield aioclient_mock


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A config entry with two locations and the water level extra."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Rijkswaterstaat",
        unique_id=DOMAIN,
        data={},
        options={
            CONF_LOCATIONS: [MAARSSEN, LOBITH],
            CONF_QUANTITIES: ["water_level"],
        },
    )
