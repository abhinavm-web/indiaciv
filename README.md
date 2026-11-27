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

**Derived** figures are the one exception, and are labelled as such wherever they appear (a "derived" tag with the
method in its tooltip). They are calculated only from sourced numbers by a stated method, shown beside the data and
never fed into totals, yields, ranks or lenses. Today there are three: SHRUG's SECC consumption estimates for cities (a published model estimate); the NFHS-5
figures of the parent district for districts created after 2017 (shown beside their cities only); and each
district's population on 1 July 2026, the
2011 census count carried forward at the district's 2001-2011 growth and scaled with its state's other districts to
the state's official projection (Technical Group on Population Projections, MoHFW). Official projections themselves
are tagged "projection".

## What's in it (v1)

- **The map.** 20 km hexes on an Albers equal-area projection, borders on the official boundary of India (Survey of
  India). Relief from AWS Terrain Tiles, land cover from ESA WorldCover 2021, rivers and lakes from Natural Earth.
  36 states and UTs, 790 districts. Neighbouring countries are drawn under fog.
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
    RBI *Handbook of Statistics on Indian States*), in rupees. City GDP: **Pending**. District GDP is shown (not used as a yield) where a
    state publishes it and its file is readable: each state's own estimate, labelled as not comparable across states.
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
  districts made of whole 2011 districts. Where a 2011 district was split, growth is summed over SHRUG's consistent
  small areas (census 2001 and 2011 on the same villages and towns), used only where SHRUG's 2001 total for each
  2011 district involved is within 2% of the census's own; the rest are Pending. Cities from Census Table A-04
  (each town and agglomeration at every census since 1901, on its boundaries at that census), matched by the exact
  2011 population; cities that were not census towns in 2001 are Pending.
- **Lenses.** Population density, growth, urban share, literacy, life expectancy, farm-worker share, poverty, urban
  unemployment, income per person, earthquakes since 1900 (USGS), forest, farmland, built-up land.
- **Resources and wonders.** Coal, gas, oil, hydro, wind, solar and biomass power plants (WRI); operating coal and
  iron ore mines and the larger oil and gas blocks (Global Energy Monitor); World Heritage sites,
  national parks and universities (Wikidata); Natural Earth roads, rail and ports; OurAirports airports with
  scheduled service.

## Data sources

| Source | Used for | How it is fetched |
|---|---|---|
| [Census of India 2011, Primary Census Abstract](https://censusindia.gov.in/nada/index.php/catalog/42559) (ORGI) | Population, households, literacy, workers, cities | Download (xlsx) |
| [PCA Urban Agglomerations 2011](https://censusindia.gov.in/nada/index.php/catalog/45261) (ORGI) | Cities | Download (xlsx) |
| [Census 2011 Table A-02](https://censusindia.gov.in/nada/index.php/catalog/43333) (ORGI) | Growth 2001-2011, 1901-2011 series | Catalogue search, xlsx/xls (needs `xlrd` for .xls) |
| [Global Energy Monitor](https://globalenergymonitor.org/projects/global-oil-gas-extraction-tracker/) Global Oil and Gas Extraction Tracker | Oil and gas blocks with a known location | CC BY 4.0; data file behind GEM's public map (August 2023) |
| [Technical Group on Population Projections](https://nhm.gov.in/New_Updates_2018/Report_Population_Projection_2019.pdf) (MoHFW) | State projections to 2036; basis of the derived district estimate | Table 11 read with `pdftotext` |
| State Directorates of Economics and Statistics: [Maharashtra](https://mls.org.in/PDF2026/budjet/ESM_25_26_Eng%20Book.pdf), [Tamil Nadu](https://des.tn.gov.in/sites/default/files/2025-07/34.%20STATE%20INCOME.pdf), [Uttarakhand](https://des.uk.gov.in/district-domestic-product-estimates/), [Telangana](https://des.telangana.gov.in/publications/TS%20Economy%20PE2023-24.pdf) | District GDP, each state's own estimate (not comparable across states) | Tables read from each publication |
| [SHRUG v2.2](https://www.devdatalab.org/shrug_download/) (Development Data Lab) | Economic Census 2013 jobs (cities, districts, states), SECC consumption estimate (cities), PM2.5 (districts) | **CC BY-NC-SA 4.0**; signed download links fetched fresh each run |
| [NITI Aayog National MPI 2023](https://www.niti.gov.in/sites/default/files/2023-08/India-National-Multidimentional-Poverty-Index-2023.pdf) | District poverty (multidimensional headcount, 2019-21) | District tables read from the PDF (needs `pymupdf` at fetch) |
| [Census 2011 Table A-04](https://censusindia.gov.in/nada/index.php/catalog/42876) (ORGI) | City growth 2001-2011, 1901-2011 series | Catalogue search, six xlsx tables by size class |
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

- City GDP; district GDP outside Maharashtra, Tamil Nadu, Uttarakhand and Telangana (other states publish it, but
  each in its own format, and many state sites cannot be reached from the build machine); population after 2011 (the next census has not published results); growth for
  districts carved from split 2011 districts, and for Andhra Pradesh, Telangana and Jammu and Kashmir.
- City-level jobs, incomes and rents (usaciv's City View and Advisors are off until Indian sources are wired in).
- Economic Census jobs for cities whose SHRUG urban area does not match the census city (shared with a neighbour, or
  more than 15% different in 2011 population), and for districts where SHRUG did not place the jobs consistently
  (all of Delhi).
- Oil and gas blocks without a location in GEM's tracker (14 of 23), smaller fields, and mines other than coal and
  iron ore.
- Five districts with no 2011 census area (Mirpur and Muzaffarabad in Pakistan-administered Kashmir; three new
  districts drawn from sub-districts that straddle older ones).

## Running it

```sh
uv pip install rasterio numpy xlrd pymupdf   # fetch only: WorldCover, census .xls tables, NITI MPI PDF
uv run python -m pipeline all            # fetch → process → build → check
uv run python -m pipeline serve          # http://127.0.0.1:8765
uv run python -m pipeline package        # indiaciv.zip: the static site, ready to upload
```

The pipeline is standard-library Python (Excel files are read with a small built-in reader, `pipeline/core/xlsx.py`).
The web app is static: serve `web/` from any static host. Tests: `PYTHONPATH=. uv run --with pytest pytest -q`.

## Licences

The code is MIT (see `LICENSE`). The data keeps its sources' licences, listed above and in the Almanac. One of them
is share-alike and non-commercial: the figures built from **SHRUG** (Economic Census 2013 jobs, SECC consumption
estimates and PM2.5, in `cities.json`, `states.json`, `counties.json` and `lenses.json`) are shared under
[CC BY-NC-SA 4.0](http://creativecommons.org/licenses/by-nc-sa/4.0/), credited to the Development Data Lab, and
published with SHRUG's identifiers (each city's `shrug_ua`; 2011 census sub-district codes for districts). This
project is non-commercial; a commercial use of those figures needs the Development Data Lab's permission.

## Credits

Engine, art and app: [usaciv](https://karpathy.ai/usaciv/) by Andrej Karpathy, MIT licence. Country-agnostic pipeline:
[iranciv](https://github.com/zanganeh/iranciv) contributors, MIT licence. India data pipeline: this repository. See
`LICENSE`.
