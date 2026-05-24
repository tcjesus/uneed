"""
preprocess_wind.py
================================================
Pre‑processing script that aggregates raw point wind‑speed data
to parish level and stores a tidy CSV ready for the micro‑grid
index pipeline.

Pipeline
--------
1.  Load—or download through get_parishes.py—the parish
    geometries for the chosen city.
2.  Read the raw wind point file (./rawData/wind.csv).
3.  Spatially join points → parishes and compute the mean
    wind speed per parish.
4.  Save ./datasets/preprocessed_wind.csv with columns:
       parish, wind_speed

Each function is self‑contained and `main()` acts as a unit test.

Author: Thiago C. Jesus
Part of the UNEED microgrid-positioning framework (MIT License).
"""

# ------------------------------------------------------------------
# Imports
# ------------------------------------------------------------------
from pathlib import Path
from typing import Final

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

# Local dependency
from get_parishes import get_or_create_parish_geojson

# ------------------------------------------------------------------
# ------------------------  CONSTANTS  -----------------------------
# ------------------------------------------------------------------
COUNTRY: Final[str] = "Portugal"
CITY:    Final[str] = "Porto"

RAW_WIND_PATH: Final[Path]  = Path("./rawData/wind.csv")
DATASET_DIR:    Final[Path] = Path("./datasets")
DATASET_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV:        Final[Path] = DATASET_DIR / "preprocessed_wind.csv"

CRS_WGS84: Final[int] = 4326

# Column names in raw wind file
COL_LAT:  Final[str] = "lat"
COL_LON:  Final[str] = "lon"
COL_WSPD: Final[str] = "wind_speed"


# ------------------------------------------------------------------
# ---------------------  PROCESSING STEPS  -------------------------
# ------------------------------------------------------------------
def load_raw_wind_points(csv_path: Path) -> gpd.GeoDataFrame:
    """
    Load raw wind CSV → GeoDataFrame (EPSG:4326).
    Expected columns: lat, lon, wind_speed
    """
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    df = pd.read_csv(csv_path)
    gdf = gpd.GeoDataFrame(
        df,
        geometry=[Point(xy) for xy in zip(df[COL_LON], df[COL_LAT])],
        crs=f"EPSG:{CRS_WGS84}",
    )[[COL_WSPD, "geometry"]]
    return gdf


def compute_wind_average_by_parish(
    gdf_wind: gpd.GeoDataFrame,
    gdf_parish: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """
    Return a DataFrame with columns:
        parish, wind_speed
    """
    joined = gpd.sjoin(gdf_wind, gdf_parish, how="inner", predicate="within")
    grouped = (
        joined.groupby("index_right")[COL_WSPD]
        .mean()
        .reindex(gdf_parish.index, fill_value=float("nan"))
    )
    result = pd.DataFrame(
        {
            "parish": gdf_parish["name"].astype(str).values,
            "wind_speed": grouped.values,
        }
    )
    return result


def save_preprocessed_csv(df: pd.DataFrame, out_path: Path) -> None:
    df.to_csv(out_path, index=False, float_format="%.3f")
    print(f"[OK] Pre‑processed wind file written → {out_path}")


# ------------------------------------------------------------------
# ---------------------------  MAIN  -------------------------------
# ------------------------------------------------------------------
def main() -> None:
    """
    Unit test for Porto‑PT: produce preprocessed_wind.csv
    """
    print("[STEP] Loading or creating parish geometries …")
    gdf_par = get_or_create_parish_geojson(city=CITY, country=COUNTRY)

    print("[STEP] Loading raw wind points …")
    gdf_wind = load_raw_wind_points(RAW_WIND_PATH)

    print("[STEP] Aggregating wind speed by parish …")
    df_wind_avg = compute_wind_average_by_parish(gdf_wind, gdf_par)

    print("[STEP] Saving output CSV …")
    save_preprocessed_csv(df_wind_avg, OUT_CSV)

    print("[SUMMARY]")
    print(df_wind_avg.head())


# ------------------------------------------------------------------
if __name__ == "__main__":
    main()
