"""Tests for the RWS API response parsing."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.rws_watertemperature.api import (
    haversine_km,
    latest_observations,
    locations_with_quantity,
)
from custom_components.rws_watertemperature.const import (
    QUANTITIES,
    QUANTITY_TEMPERATURE,
    QUANTITY_WATER_LEVEL,
)

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
