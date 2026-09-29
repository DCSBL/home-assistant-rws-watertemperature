# Rijkswaterstaat Water Temperature for Home Assistant

[English](#english) · [Nederlands](#nederlands)

## English

A [HACS](https://hacs.xyz) custom integration that shows the latest surface water
temperature measured by [Rijkswaterstaat](https://waterinfo.rws.nl/) (RWS) at
measuring locations near your home. Optionally, it also shows the water level at the
same locations.

Data comes from the public RWS WaterWebservices API. No account or API key is needed.
Data: Rijkswaterstaat (CC0).

### Installation

1. In HACS, open the menu → **Custom repositories**, add
   `https://github.com/dcsbl/home-assistant-rws-watertemperature` as an **Integration**.
2. Install **Rijkswaterstaat Water Temperature** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and pick
   **Rijkswaterstaat Water Temperature**.

### Configuration

The setup lists the 30 RWS locations nearest to your home location (**Settings →
System → General**). It only shows the ones that reported a water temperature in the
last 90 days, sorted by distance, for example `Maarssen kanaal (8.1 km)`. Many RWS
"zwemwater" stations stopped reporting years ago, so they are left out.

Pick one or more locations, and optionally tick **Water level** to add a water level
sensor too. To change your selection later, use **Configure** on the integration.
Sensors for locations you deselect are removed.

### Entities

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

### Removal

Remove the integration via **Settings → Devices & services → Rijkswaterstaat Water
Temperature → Delete**, then uninstall it in HACS.

## Nederlands

Een [HACS](https://hacs.xyz)-integratie die de laatst gemeten oppervlaktewatertemperatuur
van [Rijkswaterstaat](https://waterinfo.rws.nl/) (RWS) toont voor meetlocaties bij je huis.
Optioneel toont hij ook de waterstand op dezelfde locaties.

De gegevens komen uit de openbare RWS WaterWebservices-API. Een account of API-sleutel is
niet nodig. Data: Rijkswaterstaat (CC0).

### Installatie

1. Open in HACS het menu → **Aangepaste repositories** en voeg
   `https://github.com/dcsbl/home-assistant-rws-watertemperature` toe als **Integratie**.
2. Installeer **Rijkswaterstaat Water Temperature** en herstart Home Assistant.
3. Ga naar **Instellingen → Apparaten & diensten → Integratie toevoegen** en kies
   **Rijkswaterstaat Water Temperature**.

### Instellen

De installatie zoekt de 30 RWS-meetlocaties die het dichtst bij je thuislocatie liggen
(**Instellingen → Systeem → Algemeen**). Alleen locaties die de afgelopen 90 dagen een
watertemperatuur hebben gemeten worden getoond, op afstand gesorteerd, bijvoorbeeld
`Maarssen kanaal (8.1 km)`. Veel RWS-zwemwaterlocaties meten al jaren niet meer en vallen
daarom weg.

Kies een of meer locaties en vink eventueel **Waterstand** aan voor een extra
waterstandsensor. Je keuze wijzig je later via **Configureren** bij de integratie.
Sensoren van locaties die je uitvinkt worden verwijderd.

### Entiteiten

Elke locatie wordt een apparaat (fabrikant Rijkswaterstaat) met:

| Entiteit | Beschrijving |
| --- | --- |
| Watertemperatuur | Laatste watertemperatuur in °C. Attributen: `observed_at`, `latitude`, `longitude`. |
| Waterstand | Laatste waterstand in cm (alleen als ingeschakeld). |
| Laatst bijgewerkt | Diagnostisch tijdstip van de laatste watertemperatuurmeting. |

Alle locaties worden samen eens per uur ververst, met één API-verzoek per meetgrootheid.

Is de laatste meting van een locatie ouder dan 48 uur, dan tonen de meetsensoren
**niet beschikbaar** in plaats van een verouderde waarde. **Laatst bijgewerkt** blijft
tonen wanneer RWS voor het laatst mat, zodat je ziet waarom.

### Verwijderen

Verwijder de integratie via **Instellingen → Apparaten & diensten → Rijkswaterstaat Water
Temperature → Verwijderen** en de-installeer hem daarna in HACS.

## Development

Releases use CalVer (`YYYY.M.N`): push a tag like `2026.9.1`. The release workflow sets the manifest version, builds
`rws_watertemperature.zip` and publishes a GitHub release that HACS installs from.


```sh
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
pytest
```

The test fixtures in `tests/fixtures` are synthetic. They follow the response shape of
the RWS DDAPI20 WaterWebservices as used by [rppl](https://github.com/dcsbl/rppl).