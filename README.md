# indiaciv: India as a strategy-game map, built from real data

**Live:** https://abhinavm-web.github.io/indiaciv/

A visualizer (not a game) that draws the **real** India like a turn-based 4X strategy map: hex terrain, states and
districts, cities with yield banners, lenses, power plants, ports, airports and World Heritage sites. It is a port of
Andrej Karpathy's [usaciv](https://karpathy.ai/usaciv/) (MIT), built on the country-agnostic pipeline of the
[iranciv](https://github.com/zanganeh/iranciv) port (MIT). The engine, art and app are Karpathy's; the data pipeline
here is rewritten for India's public data.

## The rule: no mock data

Every number comes from a public source that the pipeline downloads and processes itself, with the URL, date and
checksum recorded in `data/raw/<source>/manifest.json` and cited in the in-app **Almanac**. When no systematic source
has been found, the value is `null` (shown as "–") and listed on the Almanac's **Pending data** page (from
`nation.json` → `pending`). Nothing is typed in by hand, split by population or interpolated.

## What's in it (v1)

- **The map.** 20 km hexes on an Albers equal-area projection, borders on the official boundary of India (Survey of
  India). Relief from AWS Terrain Tiles, land cover from ESA WorldCover 2021, rivers and lakes from Natural Earth.
  36 states and UTs, 786 districts. Neighbouring countries are drawn under fog.
- **Population: Census 2011** (the latest India has published), from the census office's own Primary Census Abstract.
  India had 640 districts in 2011 and about 790 now, so each of the 5,988 census **sub-districts** is given, whole, to
  today's district that holds most of its area; its counts follow it. Every person in the census is placed
  (1,210,854,977). State totals are sums of districts, so Telangana and Ladakh have their own 2011 figures.
- **Cities.** The 522 census urban agglomerations and towns of 100,000+ people. The census has no coordinates, so each
  is placed at the GeoNames point of the same name **inside its own census sub-district** (or, failing that, inside the
  districts its 2011 district became). Capitals from GeoNames' seats of government (Wikidata's capital property when
  the query service answers).
- **Yields.**
  - **Gold** is GDP: Gross State Domestic Product at current prices, 2022-23 (National Statistical Office, via the
    RBI *Handbook of Statistics on Indian States*), in rupees. District and city GDP: **Pending** (no comparable
    official series).
  - **Food** is farm workers: cultivators + agricultural labourers, main and marginal (Census 2011).
  - **Production** is power-plant capacity in MW (WRI Global Power Plant Database, 2021; nuclear left out).
  - **Science** counts prominent universities, **Culture** UNESCO World Heritage properties (Wikidata).
- **Panels.** Every city, state and the nation carry Census 2011 people facts (literacy, sex ratio, children 0-6, work
  participation, household size, urban share) and workers by the census's four categories (cultivators,
  agricultural labourers, household industry, other work), compared with India. States add the latest published
  development indicators from the RBI handbook (rural and urban unemployment, multidimensional poverty, life
  expectancy, infant mortality, SDG India Index, forest cover, tourist visits, installed power, power per person)
  and GDP by sector.
- **Health & housing: NFHS-5 (2019-21).** Twelve indicators (electricity, drinking water, sanitation, clean cooking
  fuel, health insurance, women's literacy and schooling, child marriage, institutional births, child stunting and
  underweight, women's anaemia) for 700 of today's districts, every state and India, read from the official IIPS fact
  sheet PDFs (district PDFs via a pinned mirror, each fetch spot-checked value by value against the DHS Program's
  copies; state and India sheets from the DHS Program's official compendiums). Matched to today's districts by name,
  spelling variant or 2011 name; districts created after 2017 are Pending.
- **Growth 2001-2011** from Census Table A-02 (with the 1901-2011 series): exact for the nation, states and today's
  districts made of whole 2011 districts; Pending where a 2011 district was split.
- **Lenses.** Population density, growth, urban share, literacy, life expectancy, farm-worker share, poverty, urban
  unemployment, income per person, earthquakes since 1900 (USGS), forest, farmland, built-up land.
- **Resources and wonders.** Coal, gas, oil, hydro, wind, solar and biomass power plants (WRI); World Heritage sites,
  national parks and universities (Wikidata); Natural Earth roads, rail and ports; OurAirports airports with
  scheduled service.

## Data sources

| Source | Used for | How it is fetched |
|---|---|---|
| [Census of India 2011, Primary Census Abstract](https://censusindia.gov.in/nada/index.php/catalog/42559) (ORGI) | Population, households, literacy, workers, cities | Download (xlsx) |
| [PCA Urban Agglomerations 2011](https://censusindia.gov.in/nada/index.php/catalog/45261) (ORGI) | Cities | Download (xlsx) |
| [Census 2011 Table A-02](https://censusindia.gov.in/nada/index.php/catalog/43333) (ORGI) | Growth 2001-2011, 1901-2011 series | Catalogue search, xlsx/xls (needs `xlrd` for .xls) |
| [INDIAN-SHAPEFILES](https://github.com/datta07/INDIAN-SHAPEFILES) (MIT) | States, districts, 2011 sub-districts | Download, pinned commit |
| [RBI Handbook of Statistics on Indian States](https://www.rbi.org.in/Scripts/AnnualPublications.aspx?head=Handbook+of+Statistics+on+Indian+States) | State GDP, value added by sector, per-capita NSDP, unemployment, poverty, life expectancy, infant mortality, SDG score, forest, tourism, power | 16 tables found on the page, xlsx |
| [NFHS-5 fact sheets](https://rchiips.org/nfhs/districtfactsheet_NFHS-5.shtml) (IIPS, MoHFW) | District, state and India health & housing indicators | District PDFs from a pinned mirror, verified against [DHS Program](https://www.dhsprogram.com/) copies; state & India compendiums from DHS (needs `pdftotext`) |
| [GeoNames](https://www.geonames.org/) (CC BY 4.0) | City positions, seats of government | Download |
| [ESA WorldCover 2021](https://esa-worldcover.org/) | Land cover | Download (needs `rasterio`) |
| [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) | Elevation | Download |
| [Natural Earth](https://www.naturalearthdata.com/) | Neighbours, lakes, rivers, roads, rail, ports | Download |
| [WRI Global Power Plant Database](https://datasets.wri.org/dataset/globalpowerplantdatabase) | Power plants, Production | Download |
| [OurAirports](https://ourairports.com/countries/IN/) | Airports | Download |
| [Wikidata](https://www.wikidata.org/) | World Heritage, national parks, universities, capitals | SPARQL at build time (paced for rate limits) |
| [USGS ComCat](https://earthquake.usgs.gov/earthquakes/search/) | Earthquakes | Event web service at build time |
| [Global Energy Monitor](https://globalenergymonitor.org/) Global Coal Mine Tracker (May 2026) and Global Iron Ore Mines Tracker | Operating coal and iron ore mines: location, owner, capacity | CC BY 4.0; public asset API at build time |

## Pending (v1)

See the Almanac's *Pending data* page for the live list. The main gaps:

- District and city GDP; population after 2011 (the next census has not published results); growth for cities, for
  districts carved from split 2011 districts, and for Andhra Pradesh, Telangana and Jammu and Kashmir.
- City-level jobs, incomes and rents (usaciv's City View and Advisors are off until Indian sources are wired in).
- Oil and gas fields, and mines other than coal and iron ore.
- Five districts with no 2011 census area (Mirpur and Muzaffarabad in Pakistan-administered Kashmir; three new
  districts drawn from sub-districts that straddle older ones).

## Running it

```sh
uv pip install rasterio numpy xlrd       # only for the WorldCover fetch and the census .xls tables
uv run python -m pipeline all            # fetch → process → build → check
uv run python -m pipeline serve          # http://127.0.0.1:8765
uv run python -m pipeline package        # indiaciv.zip: the static site, ready to upload
```

The pipeline is standard-library Python (Excel files are read with a small built-in reader, `pipeline/core/xlsx.py`).
The web app is static: serve `web/` from any static host. Tests: `PYTHONPATH=. uv run --with pytest pytest -q`.

## Credits

Engine, art and app: [usaciv](https://karpathy.ai/usaciv/) by Andrej Karpathy, MIT licence. Country-agnostic pipeline:
[iranciv](https://github.com/zanganeh/iranciv) contributors, MIT licence. India data pipeline: this repository. See
`LICENSE`.
