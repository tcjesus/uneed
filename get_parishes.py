"""
get_parishes.py  (v2)
================================================
Reusable helper for downloading (or loading) parish polygons
(admin_level 8, or any level you pass) strictly contained inside
a municipality (admin_level 7 by default, but configurable).

Key points
----------
* All hard‑coded values are collected as DEFAULT_* constants.
* get_or_create_parish_geojson(...) receives city / country /
  admin levels / clip flag / output directory as **parameters**.
* main() keeps a simple unit test for Porto‑PT.

Author: Thiago C. Jesus
Part of the UNEED microgrid-positioning framework (MIT License).
"""


'''
How to use in other modules
from get_parishes import get_or_create_parish_geojson

# Example for Lisbon
lisbon_parishes = get_or_create_parish_geojson(
    city="Lisboa",
    country="Portugal",
    admin_level_city="7",
    admin_level_parish="8",
    clip_to_city=True,
)
'''


# ------------------------------------------------------------------
# Imports
# ------------------------------------------------------------------
from pathlib import Path
from typing import Final, Optional

import geopandas as gpd
import osmnx as ox
from shapely.geometry import Polygon, MultiPolygon, base

# ------------------------------------------------------------------
# ----------------------  DEFAULT CONSTANTS  ----------------------
# ------------------------------------------------------------------
DEFAULT_COUNTRY:          Final[str] = "Portugal"
DEFAULT_CITY:             Final[str] = "Porto"
DEFAULT_ADMIN_LVL_CITY:   Final[str] = "7"   # municipality
DEFAULT_ADMIN_LVL_PAR:    Final[str] = "8"   # parish
DEFAULT_CLIP:             Final[bool] = True

DEFAULT_GEOJSON_DIR:      Final[Path] = Path("./GeoJSONs")
DEFAULT_GEOJSON_DIR.mkdir(parents=True, exist_ok=True)

CRS_WGS84:                Final[int] = 4326


# ------------------------------------------------------------------
# --------------------------  HELPERS  ----------------------------
# ------------------------------------------------------------------
def download_city_boundary(
    city: str,
    country: str,
    admin_level: str = DEFAULT_ADMIN_LVL_CITY,
) -> gpd.GeoDataFrame:
    """Download the admin_level‑X boundary for the city."""
    place_name = f"{city}, {country}"
    print(f"[INFO] Requesting admin_level={admin_level} for '{place_name}'")

    tags = {"boundary": "administrative"}
    gdf_raw = ox.features_from_place(place_name, tags=tags)
    if gdf_raw.empty:
        raise RuntimeError("No administrative boundaries returned by OSM.")

    mask = (gdf_raw["admin_level"] == admin_level) & (gdf_raw["name"] == city)
    gdf = gdf_raw.loc[mask]
    gdf = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])]
    if gdf.empty:
        raise RuntimeError(f"No admin_level={admin_level} called '{city}' found.")

    return gdf.to_crs(epsg=CRS_WGS84).reset_index(drop=True)


def download_parishes_within_city(
    city_geom: base.BaseGeometry,
    admin_level_parish: str = DEFAULT_ADMIN_LVL_PAR,
    clip_to_city: bool = DEFAULT_CLIP,
) -> gpd.GeoDataFrame:
    """Download every admin_level parish whose centroid lies inside city_geom."""
    if not isinstance(city_geom, (Polygon, MultiPolygon)):
        raise ValueError("City geometry must be Polygon/MultiPolygon")

    tags = {"boundary": "administrative", "admin_level": admin_level_parish}
    print(f"[INFO] Requesting admin_level={admin_level_parish} parishes…")
    gdf_raw = ox.features_from_polygon(city_geom, tags=tags)
    gdf_raw = gdf_raw[gdf_raw.geometry.type.isin(["Polygon", "MultiPolygon"])]

    inside_mask = gdf_raw.geometry.centroid.within(city_geom)
    gdf = gdf_raw.loc[inside_mask].copy()

    if gdf.empty:
        raise RuntimeError("No parishes found inside the municipality boundary.")

    if clip_to_city:
        gdf = gpd.overlay(
            gdf,
            gpd.GeoDataFrame(geometry=[city_geom], crs=gdf.crs),
            how="intersection",
        )

    # ENSURE name survives
    if "name_left" in gdf.columns and "name" not in gdf.columns:
        gdf = gdf.rename(columns={"name_left": "name"})


    gdf = (
        gdf[gdf["admin_level"] == admin_level_parish][["name", "geometry"]]
        .to_crs(epsg=CRS_WGS84)
        .drop_duplicates()
        .reset_index(drop=True)
    )
    print(f"[INFO] Parishes downloaded (features = {len(gdf)})")
    return gdf


# ------------------------------------------------------------------
# -------------  PUBLIC FUNCTION (import‑friendly)  ---------------
# ------------------------------------------------------------------
def get_or_create_parish_geojson(
    city: str                 = DEFAULT_CITY,
    country: str              = DEFAULT_COUNTRY,
    admin_level_city: str     = DEFAULT_ADMIN_LVL_CITY,
    admin_level_parish: str   = DEFAULT_ADMIN_LVL_PAR,
    clip_to_city: bool        = DEFAULT_CLIP,
    output_dir: Optional[Path] = None,
) -> gpd.GeoDataFrame:
    """
    Retrieve parish polygons inside a municipality and save them as GeoJSON.
    If the cache file already exists it is loaded instead.

    Parameters
    ----------
    city : str
    country : str
    admin_level_city : str
        Admin level for the municipality (default '7').
    admin_level_parish : str
        Admin level for the parishes (default '8').
    clip_to_city : bool
        Whether to clip parish geometries to the city boundary.
    output_dir : Path or None
        Directory to store GeoJSON; defaults to DEFAULT_GEOJSON_DIR.

    Returns
    -------
    GeoDataFrame
        Parishes in EPSG:4326.
    """
    out_dir = output_dir or DEFAULT_GEOJSON_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{country}_{city}.geojson".replace(" ", "_")

    if out_file.exists():
        print(f"[OK] GeoJSON already present → {out_file}")
        return gpd.read_file(out_file)

    # Download sequence
    gdf_city = download_city_boundary(city, country, admin_level_city)
    city_poly = gdf_city.unary_union
    gdf_par   = download_parishes_within_city(city_poly,
                                              admin_level_parish,
                                              clip_to_city)

    gdf_par.to_file(out_file, driver="GeoJSON")
    print(f"[OK] GeoJSON written → {out_file}")
    return gdf_par


# ------------------------------------------------------------------
# --------------------------  UNIT TEST  ---------------------------
# ------------------------------------------------------------------
def main() -> None:
    """Unit‑test for Porto using default constants."""
    gdf_par = get_or_create_parish_geojson()
    print(f"[SUMMARY] {len(gdf_par)} parishes for {DEFAULT_CITY}:")
    print("          ", ", ".join(sorted(gdf_par['name'].astype(str)))[:120], "…")


# ------------------------------------------------------------------
if __name__ == "__main__":
    main()



'''
How to use in other modules
from get_parishes import get_or_create_parish_geojson

# Example for Lisbon
lisbon_parishes = get_or_create_parish_geojson(
    city="Lisboa",
    country="Portugal",
    admin_level_city="7",
    admin_level_parish="8",
    clip_to_city=True,
)
'''