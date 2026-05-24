"""
preprocess_ghi.py
================================================
Pre‑processing script that aggregates raw Global Horizontal
Irradiance (GHI) point data to parish level and saves the tidy
CSV used later by the Renewable‑Potential sub‑index.

Steps
-----
1.  Obtain parish polygons through get_parishes.get_or_create_parish_geojson().
2.  Load raw point file ./rawData/ghi.csv.
3.  Compute mean GHI for each parish.
4.  Write ./datasets/preprocessed_ghi.csv with:
        parish, ghi

Every parameter path or label appears exactly once as a constant.
`main()` provides a quick unit test for Porto‑PT.

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

RAW_GHI_PATH: Final[Path] = Path("./rawData/ghi.csv")

DATASET_DIR: Final[Path] = Path("./datasets")
DATASET_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV: Final[Path] = DATASET_DIR / "preprocessed_ghi.csv"

CRS_WGS84: Final[int] = 4326

# Expected column names in raw file
COL_LAT: Final[str] = "lat"
COL_LON: Final[str] = "lon"
COL_GHI: Final[str] = "ghi"


# ------------------------------------------------------------------
# ---------------------  PROCESSING STEPS  -------------------------
# ------------------------------------------------------------------
def load_raw_ghi_points(csv_path: Path) -> gpd.GeoDataFrame:
    """
    Load raw GHI CSV and return GeoDataFrame (EPSG:4326)
    """
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    df = pd.read_csv(csv_path)
    required = {COL_LAT, COL_LON, COL_GHI}
    if not required.issubset(df.columns):
        raise ValueError(f"Input CSV must contain columns {required}")

    gdf = gpd.GeoDataFrame(
        df,
        geometry=[Point(xy) for xy in zip(df[COL_LON], df[COL_LAT])],
        crs=f"EPSG:{CRS_WGS84}",
    )[[COL_GHI, "geometry"]]
    return gdf


def compute_ghi_average_by_parish(
    gdf_ghi: gpd.GeoDataFrame,
    gdf_parish: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """
    Return DataFrame with columns:
        parish, ghi
    """
    joined = gpd.sjoin(gdf_ghi, gdf_parish, how="inner", predicate="within")
    grouped = (
        joined.groupby("index_right")[COL_GHI]
        .mean()
        .reindex(gdf_parish.index, fill_value=float("nan"))
    )
    return pd.DataFrame(
        {
            "parish": gdf_parish["name"].astype(str).values,
            "ghi": grouped.values,
        }
    )


def save_preprocessed_csv(df: pd.DataFrame, out_path: Path) -> None:
    df.to_csv(out_path, index=False, float_format="%.2f")
    print(f"[OK] Pre‑processed GHI file written → {out_path}")


# ------------------------------------------------------------------
# ----------------------------  MAIN  ------------------------------
# ------------------------------------------------------------------
def main() -> None:
    """Unit test for Porto‑PT."""
    print("[STEP] Loading or creating parish geometries …")
    gdf_par = get_or_create_parish_geojson(city=CITY, country=COUNTRY)

    print("[STEP] Loading raw GHI points …")
    gdf_ghi = load_raw_ghi_points(RAW_GHI_PATH)

    print("[STEP] Aggregating GHI by parish …")
    df_ghi_avg = compute_ghi_average_by_parish(gdf_ghi, gdf_par)

    print("[STEP] Saving output CSV …")
    save_preprocessed_csv(df_ghi_avg, OUT_CSV)

    print("[SUMMARY]")
    print(df_ghi_avg.head())


# ------------------------------------------------------------------
if __name__ == "__main__":
    main()
