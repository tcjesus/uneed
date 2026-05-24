"""
preprocess_pois.py
================================================
Pre‑processing script that downloads selected Points of Interest
inside the valid parishes of a city and stores them in tidy CSVs
ready for index computation.

Outputs:
  • datasets/POIs_emergency.csv        — Emergency Response Infrastructure
  • datasets/POIs_priority.csv         — Priority Infrastructure
  • datasets/POIs_heat.csv             — Heat Support Infrastructure
  • datasets/POIs_emergency_count.csv  — counts by parish & category
  • datasets/POIs_priority_count.csv   — counts by parish & category
  • datasets/POIs_heat_count.csv       — counts by parish & category
---------------------------

Emergency Response Infrastructure — police, fire, hospital
Priority Infrastructure — hospital, bank, school
Heat Support Infrastructure  — industrial, water, waste


Author: Thiago C. Jesus
Part of the UNEED microgrid-positioning framework (MIT License).
"""

# ------------------------------------------------------------------
# Imports
# ------------------------------------------------------------------
from pathlib import Path
from typing import Final, Dict, List, Tuple, Optional

import geopandas as gpd
import osmnx as ox
import pandas as pd
from shapely.geometry.base import BaseGeometry

from get_parishes import get_or_create_parish_geojson

# ------------------------------------------------------------------
# ------------------------  CONSTANTS  -----------------------------
# ------------------------------------------------------------------
COUNTRY:      Final[str] = "Portugal"
CITY:         Final[str] = "Porto"
CRS_WGS84:    Final[int] = 4326

DATASET_DIR:  Final[Path] = Path("./datasets")
DATASET_DIR.mkdir(parents=True, exist_ok=True)

# Output paths for each infrastructure group
OUT_POIS_ER:      Final[Path] = DATASET_DIR / "POIs_emergency.csv"
OUT_POIS_PRI:     Final[Path] = DATASET_DIR / "POIs_priority.csv"
OUT_POIS_HEAT:    Final[Path] = DATASET_DIR / "POIs_heat.csv"

OUT_COUNT_ER:     Final[Path] = DATASET_DIR / "POIs_emergency_count.csv"
OUT_COUNT_PRI:    Final[Path] = DATASET_DIR / "POIs_priority_count.csv"
OUT_COUNT_HEAT:   Final[Path] = DATASET_DIR / "POIs_heat_count.csv"

# Raw→mapped categories
CATEGORY_MAP: Final[Dict[str, str]] = {
    "police": "police",
    "fire_station": "fire",
    "hospital": "hospital",
    "bank": "bank",
    "school": "school",
    "industrial": "industrial",
    "factory": "industrial",
    "works": "industrial",
    "data_center": "industrial",
    "generator": "industrial",
    "plant": "industrial",
    "water_works": "water",
    "wastewater_plant": "waste",
}

# OSM tags to query
OSM_TAGS: Final[Dict[str, List[str]]] = {
    "amenity": ["police", "fire_station", "hospital", "bank", "school"],
    "landuse": ["industrial"],
    "man_made": ["factory", "works", "water_works", "wastewater_plant"],
    "office": ["data_center"],
    "power": ["generator", "plant"],
}

# Category groups
EMERGENCY_CATEGORIES: Final[List[str]] = ["police", "fire", "hospital"]
PRIORITY_CATEGORIES:  Final[List[str]] = ["hospital", "school", "bank"]
HEAT_CATEGORIES:      Final[List[str]] = ["industrial", "water", "waste"]

# ------------------------------------------------------------------
# ---------------------  PROCESSING FUNCTIONS  ---------------------
# ------------------------------------------------------------------
def fetch_city_polygon(gdf_parish: gpd.GeoDataFrame) -> BaseGeometry:
    """Return a unified city polygon built from parish geometries."""
    poly = gdf_parish.unary_union
    return poly.buffer(0) if poly.geom_type != "MultiPolygon" else poly


def fetch_pois(city_poly: BaseGeometry) -> gpd.GeoDataFrame:
    """Download POIs from OSM inside the city polygon."""
    print("[INFO] Fetching POIs from OSM …")
    gdf = ox.features_from_polygon(city_poly, tags=OSM_TAGS)
    gdf = gdf[gdf.geometry.type.isin(
        ["Point", "Polygon", "MultiPolygon", "LineString"]
    )]
    return gdf.to_crs(epsg=CRS_WGS84)


def classify_poi(row: pd.Series) -> Tuple[Optional[str], Optional[str]]:
    """
    Determine raw OSM tag value and mapped category.
    Returns (raw_value, mapped_category).
    """
    for key in ["amenity", "man_made", "power", "landuse", "office"]:
        val = row.get(key)
        if pd.notna(val) and str(val).strip():
            raw = str(val).strip()
            mapped = CATEGORY_MAP.get(raw)
            return raw, mapped
    return None, None


def build_address(row: pd.Series) -> str:
    """Construct a simple address from OSM addr:* tags."""
    full = row.get("addr:full", "")
    if pd.notna(full) and full.strip():
        return full.strip()
    parts = [
        row.get("addr:street", ""),
        row.get("addr:nhouse", ""),
        row.get("addr:city", ""),
        row.get("addr:postcode", ""),
    ]
    return ", ".join(p.strip() for p in parts if pd.notna(p) and p.strip())


def parse_pois(
    gdf_pois: gpd.GeoDataFrame,
    gdf_parish: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """
    Parse raw POIs → tidy DataFrame:
    columns (category, parish, lat, lon, name, address).
    """
    # rename parish 'name' to avoid collision
    gdf_par_ren = gdf_parish.rename(columns={"name": "parish_name"})

    # compute POI centroids for join
    gdf_pois["centroid"] = gdf_pois.geometry.centroid
    pts = gdf_pois.set_geometry("centroid")

    # spatial join: assign each POI to a parish
    joined = gpd.sjoin(
        pts,
        gdf_par_ren[["parish_name", "geometry"]],
        how="inner",
        predicate="within"
    )

    records = []
    for _, row in joined.iterrows():
        _, cat = classify_poi(row)
        if not cat:
            continue
        lon, lat = row.centroid.x, row.centroid.y
        addr = build_address(row)
        records.append({
            "category": cat,
            "parish": row["parish_name"],
            "lat": lat,
            "lon": lon,
            "name": row.get("name", "") or "",
            "address": addr,
        })

    df = pd.DataFrame(records)
    return df.sort_values(["parish", "category", "name"]).reset_index(drop=True)


def count_pois_by_parish_category(df_pois: pd.DataFrame) -> pd.DataFrame:
    """
    Count POIs per (parish, category).
    Returns DataFrame with columns: parish, category, numPOIs.
    """
    grp = df_pois.groupby(["parish", "category"]).size()
    return grp.reset_index(name="numPOIs")


def save_csv(df: pd.DataFrame, out_path: Path) -> None:
    """Save DataFrame to CSV."""
    df.to_csv(out_path, index=False)
    print(f"[OK] Saved {out_path} ({len(df)} rows)")


# ------------------------------------------------------------------
# ----------------------------  MAIN  ------------------------------
# ------------------------------------------------------------------
def main() -> None:
    """Unit test for Porto‑PT: produce separate POI files and counts."""
    print("[STEP] Load/create parish geometries …")
    gdf_par = get_or_create_parish_geojson(city=CITY, country=COUNTRY)

    # normalize parish name column
    if "name" not in gdf_par.columns:
        for alt in ("name_left", "name_right"):
            if alt in gdf_par.columns:
                gdf_par = gdf_par.rename(columns={alt: "name"})
                break
        else:
            raise KeyError("Parish GDF missing 'name' column.")

    print("[STEP] Build city polygon …")
    city_poly = fetch_city_polygon(gdf_par)

    print("[STEP] Fetch POIs …")
    gdf_pois = fetch_pois(city_poly)

    print("[STEP] Parse and filter POIs …")
    df_pois = parse_pois(gdf_pois, gdf_par)

    # Emergency Response Infrastructure
    df_er = df_pois[df_pois.category.isin(EMERGENCY_CATEGORIES)]
    save_csv(df_er, OUT_POIS_ER)
    save_csv(count_pois_by_parish_category(df_er), OUT_COUNT_ER)

    # Priority Infrastructure
    df_pri = df_pois[df_pois.category.isin(PRIORITY_CATEGORIES)]
    save_csv(df_pri, OUT_POIS_PRI)
    save_csv(count_pois_by_parish_category(df_pri), OUT_COUNT_PRI)

    # Heat Support Infrastructure
    df_heat = df_pois[df_pois.category.isin(HEAT_CATEGORIES)]
    save_csv(df_heat, OUT_POIS_HEAT)
    save_csv(count_pois_by_parish_category(df_heat), OUT_COUNT_HEAT)

    print("[SUMMARY]\nEmergency POIs:", df_er.shape[0],
          "Priority POIs:", df_pri.shape[0],
          "Heat POIs:", df_heat.shape[0])


if __name__ == "__main__":
    main()