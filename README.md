# UNEED — Urban Neighborhood Energy Demand

A data-driven, multi-criteria framework for **consumer-centric microgrid location planning** in smart
cities. The pipeline computes the **UNEED index**, a composite score assigned to every node of a regular
spatial grid laid over a city, that ranks candidate locations for deploying a microgrid.

UNEED combines six georeferenced dimensions, each captured by a dedicated sub-index, into a single
dimensionless score. The reference case study is **Porto, Portugal**, but the framework is parameterized
and can be adapted to other cities.

> This repository contains the source code behind the UNEED paper (see [Citation](#citation)).

---

## The UNEED index

The composite score for a grid node *i* is a weighted sum of six sub-indices (the weights must sum to 1):

| Sub-index    | Dimension                              | Built from                                            | Level       |
|--------------|----------------------------------------|-------------------------------------------------------|-------------|
| `RenewPot`   | Renewable potential                    | Solar irradiance (GHI) + wind speed                   | parish      |
| `SocEcon`    | Socioeconomic vulnerability            | Income, population density, age structure             | parish      |
| `PriorInfra` | Priority infrastructure coverage       | Hospitals, schools, banks                             | parish      |
| `HeatInfra`  | Heat-support infrastructure            | Industrial, water-treatment, waste facilities         | parish      |
| `EmgVuln`    | Emergency vulnerability                | Distance to fire / police / hospital services         | grid node   |
| `HeatLoad`   | Local heating demand                   | Building space-heating demand vs. distance            | grid node   |

Parish-level sub-indices are computed once per civil parish and mapped onto every grid node it contains;
the two distance-based sub-indices (`EmgVuln`, `HeatLoad`) are computed per grid node.

---

## How it works

```
get_parishes.py ───────────────► GeoJSONs/Portugal_Porto.geojson   (parish polygons, OSM cache)
                                  └── imported by every other script

preprocess_ghi.py    rawData/ghi.csv   ─► datasets/preprocessed_ghi.csv
preprocess_wind.py   rawData/wind.csv  ─► datasets/preprocessed_wind.csv
preprocess_buildings.py rawData/temp.csv + OSM ─► datasets/preprocessed_buildings.csv
preprocess_pois.py   OSM               ─► datasets/POIs_*.csv  (+ *_count.csv)
(provided manually)  ──────────────────  datasets/preprocessed_income.csv,
                                          preprocessed_popAge.csv, preprocessed_popDensity.csv

microgridPositioning.py  ◄── consumes all of the above
   └─► datasets/indexes/subindex_*.csv, index_UNEED*.csv
   └─► GeoJSONs/portugal_porto_grid.geojson   (mappable in QGIS)

plot_uneed_by_parish.py  ◄── reads index_UNEED.csv ─► per-parish bar chart
```

**Distances** between grid nodes and points of interest / buildings use the haversine (great-circle)
formula on WGS84 (EPSG:4326). The regular grid spacing and building-footprint areas are computed in the
projected metric system **ETRS89 / Portugal TM06 (EPSG:3763)** — this projection is Portugal-specific
(see [Adapting to another city](#adapting-to-another-city)).

---

## Repository structure

```
.
├── microgridPositioning.py     # MAIN pipeline: sub-indices + UNEED composite + GeoJSON
├── get_parishes.py             # download/cache civil-parish polygons from OpenStreetMap
├── preprocess_ghi.py           # aggregate raw GHI points → per-parish solar potential
├── preprocess_wind.py          # aggregate raw wind points → per-parish wind potential
├── preprocess_pois.py          # download & count emergency/priority/heat POIs from OSM
├── preprocess_buildings.py     # download building footprints, classify, compute heating demand
├── plot_uneed_by_parish.py     # grouped bar chart of sub-indices per parish
├── requirements.txt            # pinned Python dependencies
├── datasets/                   # input layers, intermediate CSVs, and computed indices
│   ├── preprocessed_*.csv       #   per-parish input layers (climate, census)
│   ├── POIs_*.csv               #   points of interest and per-parish counts
│   └── indexes/                 #   computed sub-indices + UNEED outputs
├── GeoJSONs/                   # parish polygons and the output grid (open in QGIS)
└── rawData/                    # raw source data + Links - Datasets.txt (provenance)
```

> `datasets/` also contains a few legacy/archived result folders (e.g. `indexes v0/`,
> `indexes v1 code_v6.3/`, scenario subfolders) kept from earlier runs. They are **not** used by the
> code and can be removed safely.

---

## Requirements & installation

- **Python 3.13** (developed and tested on 3.13.2; 3.10+ should work)
- The geospatial stack (GeoPandas, Shapely, pyproj, pyogrio, rasterio) — installed via `requirements.txt`

```bash
# from the repository root
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

The pinned versions are listed in [`requirements.txt`](requirements.txt). The geospatial packages ship
binary wheels for common platforms, so no system GDAL/GEOS/PROJ install is normally required. If you hit
build issues, use a `conda`/`mamba` environment instead.

**Optional — maps:** the output GeoJSON layers are styled and exported as figures using
**QGIS 3.36 "Maidenhead"** (a desktop GIS, installed separately — not a Python package).

---

## Data sources

Raw data and their origins are documented in [`rawData/Links - Datasets.txt`](rawData/Links%20-%20Datasets.txt):

| Layer                         | Source                                                            |
|-------------------------------|------------------------------------------------------------------|
| GHI, wind, temperature        | NASA Langley POWER Project (data-access viewer)                   |
| Income, population, age       | Statistics Portugal (INE), 2021 census                           |
| Buildings, POIs, parishes     | OpenStreetMap, harvested via OSMnx                                |

> `preprocessed_income.csv`, `preprocessed_popAge.csv`, and `preprocessed_popDensity.csv` are provided
> directly (curated from the INE census) — there is no preprocessing script for them.

---

## Usage

The pipeline runs as plain scripts from the repository root. Steps that query OpenStreetMap
(`get_parishes`, `preprocess_pois`, `preprocess_buildings`) require an internet connection.

```bash
# 1. (optional) cache the civil-parish polygons — otherwise it is fetched on first use
python get_parishes.py

# 2. build the per-parish and per-grid input layers
python preprocess_ghi.py
python preprocess_wind.py
python preprocess_pois.py
python preprocess_buildings.py
#    (income / popAge / popDensity CSVs are already provided in datasets/)

# 3. compute the six sub-indices and the UNEED composite (also writes the grid GeoJSON)
python microgridPositioning.py

# 4. (optional) plot the per-parish sub-index bar chart
python plot_uneed_by_parish.py
```

**Smart cache:** `microgridPositioning.py` reuses any sub-index CSV that already exists in
`datasets/indexes/` instead of recomputing it. Delete the relevant CSVs (or the whole `datasets/indexes/`
folder) to force a fresh computation.

### Outputs

Written to `datasets/indexes/`:

- `index_UNEED.csv` — UNEED plus all six sub-indices, one row per grid node
- `index_UNEED_by_point.csv` — UNEED per grid node (compact)
- `index_UNEED_by_parish.csv` — mean UNEED aggregated per parish
- `subindex_*.csv` — each sub-index, cached

And to `GeoJSONs/`:

- `portugal_porto_grid.geojson` — grid nodes (with all metrics), parish polygons, and city outline,
  ready to open and style in QGIS.

---

## Configuring weighting scenarios

The composite UNEED weights live near the top of [`microgridPositioning.py`](microgridPositioning.py)
(the `W_RENEW`, `W_EMGVULN`, `W_PRIORINF`, `W_HEATINF`, `W_HEATLOAD`, `W_SOCECON` block). Several
ready-made scenarios are included as commented blocks (equal weights, emergency-vulnerability priority,
heating-infrastructure priority). To switch scenario, comment out the active block and uncomment the one
you want. **The six weights must sum to 1.**

The intra-index weights (e.g. `ALPHA_SOLAR`/`ALPHA_WIND`) are also defined there.

---

## Adapting to another city

1. Change the `COUNTRY` / `CITY` constants at the top of each script.
2. Provide the raw climate (`rawData/ghi.csv`, `wind.csv`, `temp.csv`) and census layers for the new city.
3. **Change the projected CRS:** `CRS_METRIC_PT = 3763` (ETRS89 / Portugal TM06) is specific to mainland
   Portugal. Replace it with the appropriate national/UTM metric CRS for your study area.
4. Re-run the pipeline (clear `datasets/indexes/` so cached results are recomputed).

---

## Citation

If you use this code, please cite the UNEED paper:

```bibtex
@inproceedings{jesus2026uneed,
  author    = {Jesus, Thiago C. and Santos, S{\'e}rgio F. and Bittencourt, Jo{\~a}o Carlos N. and
               Flores, Thommas K. S. and Costa, Daniel G. and Catal{\~a}o, Jo{\~a}o P. S.},
  title     = {Toward Consumer-centric Microgrid Location Planning in Smart Cities},
  year      = {2026},
  note      = {Forthcoming}
}
```

> Update the `@inproceedings` venue/pages once publication details are final.

---

## License

Released under the [MIT License](LICENSE).

---

## Acknowledgments

This work was supported in part by the EU Horizon Europe Programme under GA ID 101160614 (EU-DREAM) and
GA ID 101230578 (INNO-TREC); by COMPETE2030-FEDER-00883700 and FCT (INVINCIBLE,
DOI 10.54499/2023.17788.ICDT); by the Brazilian agency CNPq (grant 404637/2024-8); and by FAPESB
(grant 2465/2025).
