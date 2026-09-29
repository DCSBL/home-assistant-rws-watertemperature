"""Client for the Rijkswaterstaat WaterWebservices (DDAPI20) API.

No API key is needed. Two endpoints are used:

- ``OphalenCatalogus`` lists every measuring location and which Aquo quantities
  (Compartiment + Grootheid) it has a series for.
- ``OphalenLaatsteWaarnemingen`` returns the latest observations for a quantity
  at one or more locations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import math
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from homeassistant.util import dt as dt_util

from .const import CATALOG_URL, OBSERVATIONS_URL, Quantity

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = ClientTimeout(total=60)
USER_AGENT = "home-assistant-rws-watertemperature"

# RWS reports missing numeric values with this sentinel instead of null.
MISSING_VALUE = 999999999


class RwsError(Exception):
    """Base error for the RWS API."""


class RwsConnectionError(RwsError):
    """The RWS API could not be reached."""


class RwsApiError(RwsError):
    """The RWS API returned an error or an unexpected response."""


@dataclass(frozen=True, kw_only=True)
class RwsLocation:
    """A measuring location from the RWS catalog."""

    code: str
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True, kw_only=True)
class RwsObservation:
    """The latest reading of one quantity at one location."""

    code: str
    value: float
    observed_at: datetime


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def locations_with_quantity(
    catalog: dict[str, Any], quantity: Quantity
) -> list[RwsLocation]:
    """Return the catalog locations that have a series for ``quantity``."""
    meta_ids = {
        meta["AquoMetadata_MessageID"]
        for meta in catalog.get("AquoMetadataLijst") or []
        if (meta.get("Compartiment") or {}).get("Code") == quantity.compartiment
        and (meta.get("Grootheid") or {}).get("Code") == quantity.grootheid
    }
    loc_ids = {
        link["Locatie_MessageID"]
        for link in catalog.get("AquoMetadataLocatieLijst") or []
        if link.get("AquoMetaData_MessageID") in meta_ids
    }
    locations: dict[str, RwsLocation] = {}
    for loc in catalog.get("LocatieLijst") or []:
        if loc.get("Locatie_MessageID") not in loc_ids:
            continue
        if loc.get("Lat") is None or loc.get("Lon") is None or not loc.get("Code"):
            continue
        locations[loc["Code"]] = RwsLocation(
            code=loc["Code"],
            name=loc.get("Naam") or loc["Code"],
            latitude=float(loc["Lat"]),
            longitude=float(loc["Lon"]),
        )
    return list(locations.values())


def latest_observations(response: dict[str, Any]) -> dict[str, RwsObservation]:
    """Pick the most recent valid reading per location from an observations response."""
    latest: dict[str, RwsObservation] = {}
    for waarneming in response.get("WaarnemingenLijst") or []:
        code = (waarneming.get("Locatie") or {}).get("Code")
        if not code:
            continue
        for meting in waarneming.get("MetingenLijst") or []:
            value = (meting.get("Meetwaarde") or {}).get("Waarde_Numeriek")
            timestamp = meting.get("Tijdstip")
            if value is None or timestamp is None or value >= MISSING_VALUE:
                continue
            observed_at = dt_util.parse_datetime(timestamp)
            if observed_at is None:
                continue
            current = latest.get(code)
            if current is None or observed_at > current.observed_at:
                latest[code] = RwsObservation(
                    code=code, value=float(value), observed_at=observed_at
                )
    return latest


class RwsClient:
    """Minimal async client for the RWS WaterWebservices."""

    def __init__(self, session: ClientSession) -> None:
        """Initialize the client with a shared aiohttp session."""
        self._session = session

    async def _post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            async with self._session.post(
                url,
                json=body,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                # RWS answers 204 when a location has no observations for the quantity.
                if resp.status == 204:
                    return {}
                if resp.status >= 400:
                    text = await resp.text()
                    raise RwsApiError(f"HTTP {resp.status} from {url}: {text[:200]}")
                data = await resp.json(content_type=None)
        except TimeoutError as err:
            raise RwsConnectionError(f"Timeout talking to {url}") from err
        except ClientError as err:
            raise RwsConnectionError(f"Error talking to {url}: {err}") from err
        except ValueError as err:
            raise RwsApiError(f"Invalid JSON from {url}") from err
        if not isinstance(data, dict):
            raise RwsApiError(f"Unexpected response from {url}")
        if data.get("Succesvol") is False:
            # A failed lookup for locations without data is not an error for us.
            _LOGGER.debug(
                "RWS reported unsuccessful request: %s", data.get("Foutmelding")
            )
            return {}
        return data

    async def async_get_catalog(self) -> dict[str, Any]:
        """Fetch the location/quantity catalog."""
        return await self._post(
            CATALOG_URL,
            {
                "CatalogusFilter": {
                    "Compartimenten": True,
                    "Grootheden": True,
                    "Locaties": True,
                }
            },
        )

    async def async_get_locations(self, quantity: Quantity) -> list[RwsLocation]:
        """Fetch all locations that have a series for ``quantity``."""
        return locations_with_quantity(await self.async_get_catalog(), quantity)

    async def async_get_latest(
        self, quantity: Quantity, codes: list[str]
    ) -> dict[str, RwsObservation]:
        """Fetch the latest reading of ``quantity`` for all ``codes`` in one request."""
        if not codes:
            return {}
        response = await self._post(
            OBSERVATIONS_URL,
            {
                "AquoPlusWaarnemingMetadataLijst": [
                    {
                        "AquoMetadata": {
                            "Compartiment": {"Code": quantity.compartiment},
                            "Grootheid": {"Code": quantity.grootheid},
                        }
                    }
                ],
                "LocatieLijst": [{"Code": code} for code in codes],
            },
        )
        return latest_observations(response)
