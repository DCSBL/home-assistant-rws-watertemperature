"""Constants for the Rijkswaterstaat water temperature integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Final

DOMAIN: Final = "rws_watertemperature"

ATTRIBUTION: Final = "Data: Rijkswaterstaat (CC0)"

CATALOG_URL: Final = "https://ddapi20-waterwebservices.rijkswaterstaat.nl/METADATASERVICES/OphalenCatalogus"
OBSERVATIONS_URL: Final = (
    "https://ddapi20-waterwebservices.rijkswaterstaat.nl/"
    "ONLINEWAARNEMINGENSERVICES/OphalenLaatsteWaarnemingen"
)

# PDOK Locatieserver (Kadaster): free geocoder for Dutch place names, no API key.
GEOCODE_URL: Final = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free"

CONF_LOCATIONS: Final = "locations"
CONF_QUANTITIES: Final = "quantities"

# Location metadata stored in the config entry so runtime does not need the catalog.
LOC_CODE: Final = "code"
LOC_NAME: Final = "name"
LOC_LATITUDE: Final = "latitude"
LOC_LONGITUDE: Final = "longitude"

UPDATE_INTERVAL: Final = timedelta(minutes=60)

# A reading older than this makes the sensor unavailable instead of showing a stale value.
MAX_READING_AGE: Final = timedelta(hours=48)

# The config flow only offers stations that reported within this window; many RWS
# "zwemwater" stations stopped reporting years ago.
MAX_STATION_AGE: Final = timedelta(days=90)

# How many of the nearest (or best name matching) stations the config flow checks for
# recent readings and offers.
NEARBY_CANDIDATES: Final = 30


@dataclass(frozen=True, kw_only=True)
class Quantity:
    """An RWS Aquo quantity (Compartiment + Grootheid) exposed as a sensor."""

    key: str
    compartiment: str
    grootheid: str


QUANTITY_TEMPERATURE: Final = "temperature"
QUANTITY_WATER_LEVEL: Final = "water_level"

QUANTITIES: Final[dict[str, Quantity]] = {
    QUANTITY_TEMPERATURE: Quantity(
        key=QUANTITY_TEMPERATURE, compartiment="OW", grootheid="T"
    ),
    QUANTITY_WATER_LEVEL: Quantity(
        key=QUANTITY_WATER_LEVEL, compartiment="OW", grootheid="WATHTE"
    ),
}

# Quantities the user can opt into on top of water temperature.
EXTRA_QUANTITIES: Final = [QUANTITY_WATER_LEVEL]

# Unique ID suffix of the diagnostic "last measurement" timestamp sensor.
LAST_MEASUREMENT_KEY: Final = "last_measurement"
