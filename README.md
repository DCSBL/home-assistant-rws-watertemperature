# Rijkswaterstaat Water Temperature for Home Assistant

A [HACS](https://hacs.xyz) custom integration that shows the latest surface water
temperature measured by [Rijkswaterstaat](https://waterinfo.rws.nl/) (RWS) at
measuring locations near your home. Optionally, it also shows the water level at the
same locations.

Data comes from the public RWS WaterWebservices API. No account or API key is needed.
Data: Rijkswaterstaat (CC0).

## Installation

1. In HACS, open the menu → **Custom repositories**, add
   `https://github.com/dcsbl/home-assistant-rws-watertemperature` as an **Integration**.
2. Install **Rijkswaterstaat Water Temperature** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and pick
   **Rijkswaterstaat Water Temperature**.

## Configuration

The setup lists the 30 RWS locations nearest to your home location (**Settings →
System → General**). It only shows the ones that reported a water temperature in the
last 90 days, sorted by distance, for example `Maarssen kanaal (8.1 km)`. Many RWS
"zwemwater" stations stopped reporting years ago, so they are left out.

Pick one or more locations, and optionally tick **Water level** to add a water level
sensor too. To change your selection later, use **Configure** on the integration.
Sensors for locations you deselect are removed.

## Entities

Each location becomes a device (manufacturer Rijkswaterstaat) with:

| Entity | Description |
| --- | --- |
| Water temperature | Latest water temperature in °C. Attributes: `observed_at`, `latitude`, `longitude`. |
| Water level | Latest water level in cm (only if enabled). |
| Last measurement | Diagnostic timestamp of the latest water temperature measurement. |

All locations refresh together once an hour, using one API request per measured
quantity.

If a location's latest reading is more than 48 hours old, its measurement sensors show
**unavailable** rather than an outdated value. The **Last measurement** sensor keeps
showing when RWS last reported, so you can see why.

## Removal

Remove the integration via **Settings → Devices & services → Rijkswaterstaat Water
Temperature → Delete**, then uninstall it in HACS.

## Development

```sh
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
pytest
```

The test fixtures in `tests/fixtures` are synthetic. They follow the response shape of
the RWS DDAPI20 WaterWebservices as used by [rppl](https://github.com/dcsbl/rppl).
