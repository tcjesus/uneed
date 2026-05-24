"""
microgridPositioning.py  —  UNEED pipeline
Full UNEED pipeline for Porto, Portugal, with *smart caching*.

If the master file datasets/indexes/index_UNEED.csv already exists,
the grid-level sub-index CSVs are **not recomputed** – they are simply
loaded and reused.  Parish-level CSVs are skipped individually if they
already exist.

Outputs
 ├─ datasets/indexes/
 │     ├─ subindex_*.csv          (parish – cached)
 │     ├─ subindex_emgvuln.csv    (grid – cached)
 │     ├─ subindex_heatload.csv   (grid – cached)
 │     ├─ index_UNEED.csv         (all metrics, every grid point)
 │     ├─ index_UNEED_by_point.csv
 │     └─ index_UNEED_by_parish.csv
 └─ GeoJSONs/portugal_porto_grid.geojson

 
• Smart cache: parish CSVs & grid CSVs are reused if present
• Guarantees complete UNEED metrics when CSVs already exist
---------------------------------------------------------------
Author: Thiago C. Jesus
Part of the UNEED microgrid-positioning framework (MIT License).
"""
# ------------------------------------------------------------------
# IMPORTS
# ------------------------------------------------------------------
from pathlib import Path
from typing   import Final, List, Callable
import math

import numpy  as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon, MultiPolygon
from shapely.geometry.base import BaseGeometry

from get_parishes import get_or_create_parish_geojson

# ------------------------------------------------------------------
# CONSTANTS
# ------------------------------------------------------------------
COUNTRY: Final[str] = "Portugal"
CITY:    Final[str] = "Porto"

GRID_SPACING_M: Final[int] = 500          # grid spacing (m)

# CRS
CRS_WGS84:     Final[int] = 4326
CRS_METRIC_PT: Final[int] = 3763          # ETRS89 / Portugal Mainland

# ------------- folders & outputs ----------------------------------
DATASET_DIR = Path("datasets")
INDEX_DIR   = DATASET_DIR / "indexes"
DATASET_DIR.mkdir(exist_ok=True)
INDEX_DIR.mkdir(parents=True, exist_ok=True)

GEOJSON_DIR = Path("GeoJSONs")
GEOJSON_DIR.mkdir(exist_ok=True)

OUT_GEOJSON      = GEOJSON_DIR / f"{COUNTRY.lower()}_{CITY.lower()}_grid.geojson"

CSV_RENEW        = INDEX_DIR / "subindex_renewpot.csv"
CSV_SOCE         = INDEX_DIR / "subindex_socecon.csv"
CSV_PRIOR        = INDEX_DIR / "subindex_priorinfra.csv"
CSV_HEATINF      = INDEX_DIR / "subindex_heatinfra.csv"
CSV_EMG          = INDEX_DIR / "subindex_emgvuln.csv"      # grid level
CSV_HLOAD        = INDEX_DIR / "subindex_heatload.csv"     # grid level
CSV_UNEED_FULL   = INDEX_DIR / "index_UNEED.csv"
CSV_UNEED_PTS    = INDEX_DIR / "index_UNEED_by_point.csv"
CSV_UNEED_PAR    = INDEX_DIR / "index_UNEED_by_parish.csv"

# ---------- weights ------------------------------------------------
ALPHA_SOLAR, ALPHA_WIND                 = 0.6, 0.4
OMEGA_INC,  OMEGA_DENS,  OMEGA_DEP      = 0.4, 0.4, 0.2
GAMMA_BANK, GAMMA_SCH,   GAMMA_HOS      = 0.2, 0.4, 0.4
DELTA_IND,  DELTA_WATER, DELTA_WASTE    = 0.5, 0.3, 0.2
THETA_FIRE, THETA_POL,   THETA_HOS      = 0.3, 0.2, 0.5

# ---------- UNEED global weights (must sum to 1) -------------------
#
# Scenario selector: exactly ONE weight block below stays active; the others
# are wrapped in triple quotes (''' ... ''') so Python ignores them. To change
# scenario, comment out the active block and un-comment the desired one.
# The six weights must always sum to 1.
#
# Scenario: priority to Emergency Vulnerability
'''
W_RENEW     = 0.25
W_EMGVULN   = 0.35
W_PRIORINF  = 0.10
W_HEATINF   = 0.10
W_HEATLOAD  = 0.10
W_SOCECON   = 0.10
'''
'''
# Prority to Heat Infrastructure

W_RENEW     = 0.25
W_EMGVULN   = 0.10
W_PRIORINF  = 0.10
W_HEATINF   = 0.35
W_HEATLOAD  = 0.10
W_SOCECON   = 0.10
'''

'''
# ISO

W_RENEW     = 0.170
W_EMGVULN   = 0.166
W_PRIORINF  = 0.166
W_HEATINF   = 0.166
W_HEATLOAD  = 0.166
W_SOCECON   = 0.166
'''

'''
# Prority to Emergency Vulnerability v1

W_RENEW     = 0.125
W_EMGVULN   = 0.45
W_PRIORINF  = 0.05
W_HEATINF   = 0.125
W_HEATLOAD  = 0.125
W_SOCECON   = 0.125
'''

# Active scenario: priority to Heat Infrastructure (v1)

W_RENEW     = 0.125
W_EMGVULN   = 0.125
W_PRIORINF  = 0.05
W_HEATINF   = 0.45
W_HEATLOAD  = 0.125
W_SOCECON   = 0.125

#
#-------------------------------------------------------------------
# tiny offsets
EPS_LN   : Final[float] = 1e-6
EPS_DIST : Final[float] = 1e-6

# ------------------------------------------------------------------
# GRID-LEVEL CACHE  (fixed for rounding)
# ------------------------------------------------------------------
ROUND = 5          # <- must match the float_format used in .to_csv()


# ------------------------------------------------------------------
# GENERIC HELPERS
# ------------------------------------------------------------------
def _read_csv(path: Path) -> pd.DataFrame:
    """Robust CSV loader with latin-1 fallback."""
    try:
        return pd.read_csv(path, encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="latin-1")

def min_max(s: pd.Series) -> pd.Series:
    """Simple 0-1 min-max normalisation, keeps index."""
    vmin, vmax = s.min(), s.max()
    vmin = 0
    if vmax == vmin:
        return pd.Series(0.0, index=s.index)
    return (s - vmin) / (vmax - vmin)

def hav_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance in kilometres."""
    R = 6371.0
    dlat, dlon = map(math.radians, [lat2 - lat1, lon2 - lon1])
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon/2)**2)
    return 2 * R * math.asin(math.sqrt(a))

# ------------------------------------------------------------------
# PARISH helpers: when CSV has lat/lon instead of 'parish'
# ------------------------------------------------------------------
def parish_series(csv: str, value_col: str,
                  gdf_par: gpd.GeoDataFrame) -> pd.Series:
    """Return Series indexed by parish key (lower-case)."""
    df = _read_csv(DATASET_DIR / csv)

    # 1️⃣ Already aggregated?
    if "parish" in df.columns:
        s = df.set_index("parish")[value_col]
        s.index = s.index.str.strip().str.lower()
        return s

    # 2️⃣ Otherwise: point → polygon aggregation
    req = {"lat", "lon", value_col}
    if req.difference(df.columns):
        raise KeyError(f"{csv} missing {req}")

    gdf_pts = gpd.GeoDataFrame(df,
                geometry=gpd.points_from_xy(df.lon, df.lat, crs=CRS_WGS84))
    gdf_join = gpd.sjoin(gdf_pts,
                         gdf_par[["name", "geometry"]],
                         how="left", predicate="within")
    s = gdf_join.groupby("name")[value_col].mean()
    s.index = s.index.str.strip().str.lower()
    return s

# ------------------------------------------------------------------
# SUB-INDEX FUNCTIONS  (unchanged math)
# ------------------------------------------------------------------
def sub_renew(gdf_par):
    idx = gdf_par["name"].str.strip().str.lower()
    ghi  = parish_series("preprocessed_ghi.csv",  "ghi",        gdf_par).reindex(idx)
    wind = parish_series("preprocessed_wind.csv", "wind_speed", gdf_par).reindex(idx)
    return (ALPHA_SOLAR*min_max(ghi) + ALPHA_WIND*min_max(wind)).rename("RenewPot")


def sub_soce(gdf_par):
    idx   = gdf_par["name"].str.strip().str.lower()
    inc   = parish_series("preprocessed_income.csv",     "income",  gdf_par).reindex(idx)
    dens  = parish_series("preprocessed_popDensity.csv", "density", gdf_par).reindex(idx)
    # dependants
    df_age = _read_csv(DATASET_DIR / "preprocessed_popAge.csv")
    df_age["parish"] = df_age["parish"].str.strip().str.lower()
    dep = (df_age.set_index("parish")[["child", "senior"]].sum(axis=1)).reindex(idx).fillna(0)

    return (OMEGA_INC*(1-min_max(inc)) +
            OMEGA_DENS*min_max(dens)   +
            OMEGA_DEP*min_max(dep)).rename("SocEcon")

def sub_prior(gdf_par):
    df = _read_csv(DATASET_DIR / "POIs_priority_count.csv")
    df["pk"] = df["parish"].str.strip().str.lower()
    pv = df.pivot_table(index="pk", columns="category",
                        values="numPOIs", aggfunc="sum").fillna(0)
    idx = gdf_par["name"].str.strip().str.lower()
    bank = min_max(pv.get("bank",     pd.Series(0, idx)).reindex(idx))
    sch  = min_max(pv.get("school",   pd.Series(0, idx)).reindex(idx))
    hos  = min_max(pv.get("hospital", pd.Series(0, idx)).reindex(idx))
    return (GAMMA_BANK*bank + GAMMA_SCH*sch + GAMMA_HOS*hos).rename("PriorInfra")

def sub_heatinfra(gdf_par):
    df = _read_csv(DATASET_DIR / "POIs_heat_count.csv")
    df["pk"] = df["parish"].str.strip().str.lower()
    pv = df.pivot_table(index="pk", columns="category",
                        values="numPOIs", aggfunc="sum").fillna(0)
    idx = gdf_par["name"].str.strip().str.lower()
    ind   = min_max(pv.get("industrial", pd.Series(0, idx)).reindex(idx))
    water = min_max(pv.get("water",      pd.Series(0, idx)).reindex(idx))
    waste = min_max(pv.get("waste",      pd.Series(0, idx)).reindex(idx))
    return (DELTA_IND*ind + DELTA_WATER*water + DELTA_WASTE*waste).rename("HeatInfra")

def sub_emgvuln(gdf_grid):
    """Emergency-vulnerability sub-index (grid level).

    For each grid node, accumulate the weighted sum of squared haversine
    distances to every emergency POI (fire, police, hospital): larger
    cumulative distances mean emergency services are farther away, hence
    higher vulnerability. The raw value is log-compressed and min-max
    normalised to [0, 1]. Implements the EmgVuln equation in the paper.
    """
    pois = _read_csv(DATASET_DIR / "POIs_emergency.csv")
    cats = {"fire": THETA_FIRE, "police": THETA_POL, "hospital": THETA_HOS}
    raw=[]
    for _,pt in gdf_grid.iterrows():
        lat,lon=pt.lat,pt.lon; acc=0.0
        for c,w in cats.items():
            sub=pois[pois.category==c]
            if sub.empty: continue
            acc+=w*sum(hav_km(lat,lon,la,lo)**2 for la,lo in zip(sub.lat,sub.lon))
        raw.append(acc)
    ln_raw=(pd.Series(raw,index=gdf_grid.index)+EPS_LN).apply(math.log)
    return pd.DataFrame({"EmgVuln":min_max(ln_raw),"EmgVuln_LN":ln_raw})

def sub_heatload(gdf_grid):
    """Heating-load sub-index (grid level).

    For each grid node, sum every building's annual space-heating demand
    (E_Heating) divided by its squared distance to the node, so the closest
    buildings contribute most. The raw value is log-compressed and min-max
    normalised to [0, 1]. Implements the HeatLoad equation in the paper.
    """
    bld=_read_csv(DATASET_DIR/"preprocessed_buildings.csv")
    if {"lat","lon","E_Heating"}.difference(bld.columns):
        raise KeyError("preprocessed_buildings.csv needs lat,lon,E_Heating")
    raw=[]
    for _,pt in gdf_grid.iterrows():
        lat,lon=pt.lat,pt.lon
        acc=sum(row.E_Heating/(hav_km(lat,lon,row.lat,row.lon)**2+EPS_DIST)
                for _,row in bld.iterrows())
        raw.append(acc)
    ln_raw=(pd.Series(raw,index=gdf_grid.index)+EPS_LN).apply(math.log)
    return pd.DataFrame({"HeatLoad":min_max(ln_raw),"HeatLoad_LN":ln_raw})

# ------------------------------------------------------------------
# SPATIAL HELPERS
# ------------------------------------------------------------------
def city_polygon()->BaseGeometry:
    gdf = get_or_create_parish_geojson(country=COUNTRY, city=CITY)
    poly = gdf.geometry.union_all()
    if not isinstance(poly,(Polygon,MultiPolygon)):
        raise RuntimeError("City polygon invalid.")
    return poly

def make_grid(poly, spacing=GRID_SPACING_M):
    poly_m = gpd.GeoSeries([poly],crs=CRS_WGS84).to_crs(CRS_METRIC_PT).iloc[0]
    minx,miny,maxx,maxy = poly_m.bounds
    xs = np.arange(minx,maxx+spacing,spacing)
    ys = np.arange(miny,maxy+spacing,spacing)
    gdf = gpd.GeoDataFrame(
        geometry=[Point(x,y) for x in xs for y in ys], crs=CRS_METRIC_PT)
    gdf = gdf[gdf.within(poly_m)].to_crs(CRS_WGS84)
    gdf["id"]  = np.arange(1,len(gdf)+1)
    gdf["lon"] = gdf.geometry.x
    gdf["lat"] = gdf.geometry.y
    gdf["layer"]="grid_point"
    return gdf[["layer","id","lon","lat","geometry"]]

# ------------------------------------------------------------------
# CACHE HELPERS
# ------------------------------------------------------------------
def load_or_compute_parish(csv_path:Path,
                           fn:Callable[[gpd.GeoDataFrame],pd.Series],
                           gdf_par,col)->pd.Series:
    if csv_path.exists():
        s = _read_csv(csv_path).set_index("parish")[col]
        s.index = s.index.str.strip().str.lower()
        return s
    s = fn(gdf_par).round(5)
    pd.DataFrame({"parish":gdf_par["name"], col:s.values}) \
      .to_csv(csv_path,index=False,float_format="%.5f")
    return s

def load_or_compute_grid(csv_path : Path,
                         fn        : Callable[[gpd.GeoDataFrame], pd.DataFrame],
                         gdf_grid  : gpd.GeoDataFrame,
                         cols      : List[str]) -> pd.DataFrame:
    """
    Return df[cols] whose index EXACTLY matches gdf_grid.index.
    Uses a rounded lat/lon key to avoid precision-mismatch problems.
    """
    # helper --------------------------------------------------------
    def _add_keys(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["lat_key"] = df["lat"].round(ROUND)
        df["lon_key"] = df["lon"].round(ROUND)
        return df

    # ---------------------------------------------------------------
    if csv_path.exists():
        # ------- read cached file and build keys -------------------
        cached = _read_csv(csv_path)[["lat", "lon"] + cols]
        cached = _add_keys(cached)

        # ------- grid keys + original row order --------------------
        grid_keys          = _add_keys(gdf_grid[["lat", "lon"]])
        grid_keys["row_id"] = gdf_grid.index        # keep order

        merged = grid_keys.merge(
            cached, on=["lat_key", "lon_key"], how="left")

        merged = merged.sort_values("row_id")       # back to grid order
        merged.set_index("row_id", inplace=True)
        merged = merged[cols]
        merged.index.name = None                    # cosmetic
        return merged

    # ---------------------------------------------------------------
    # cache miss  → compute, save, and return -----------------------
    df_new   = fn(gdf_grid)                         # same index already
    df_write = gdf_grid[["lat", "lon"]].join(df_new)
    df_write.to_csv(csv_path, index=False, float_format="%.5f")
    return df_new[cols]

# ------------------------------------------------------------------
# PIPELINE
# ------------------------------------------------------------------
def run_pipeline() -> None:
    # 1 ▸ parishes ---------------------------------------------------
    gdf_par = get_or_create_parish_geojson(country=COUNTRY, city=CITY)
    gdf_par["pk"] = gdf_par["name"].str.strip().str.lower()

    renew  = load_or_compute_parish(CSV_RENEW,   sub_renew,   gdf_par,"RenewPot")
    soce   = load_or_compute_parish(CSV_SOCE,    sub_soce,    gdf_par,"SocEcon")
    prior  = load_or_compute_parish(CSV_PRIOR,   sub_prior,   gdf_par,"PriorInfra")
    heatin = load_or_compute_parish(CSV_HEATINF, sub_heatinfra,gdf_par,"HeatInfra")

    # 2 ▸ grid -------------------------------------------------------
    poly      = city_polygon()
    gdf_grid  = make_grid(poly)

    emg_df   = load_or_compute_grid(CSV_EMG,   sub_emgvuln, gdf_grid, ["EmgVuln"])
    hload_df = load_or_compute_grid(CSV_HLOAD, sub_heatload, gdf_grid, ["HeatLoad"])
    gdf_grid = gdf_grid.join(emg_df).join(hload_df)

    # 3 ▸ attach parish sub-indices to every point ------------------
    gdf_pts = gpd.sjoin(gdf_grid, gdf_par[["pk","geometry"]],
                        how="left", predicate="within")

    for col,ser in {"RenewPot":renew,
                    "SocEcon":soce,
                    "PriorInfra":prior,
                    "HeatInfra":heatin}.items():
        gdf_pts[col] = gdf_pts["pk"].map(ser.to_dict())

    # 4 ▸ (re)write the two grid-level CSVs in required layout ------
    gdf_pts[["pk","lat","lon","EmgVuln"]].rename(columns={"pk":"parish"}) \
          .to_csv(CSV_EMG, index=False, float_format="%.5f")

    gdf_pts[["pk","lat","lon","HeatLoad"]].rename(columns={"pk":"parish"}) \
          .to_csv(CSV_HLOAD, index=False, float_format="%.5f")

    # 5 ▸ UNEED composite index ------------------------------------
    gdf_pts["UNEED"] = (
        W_RENEW    * gdf_pts["RenewPot"]   +
        W_EMGVULN  * gdf_pts["EmgVuln"]    +
        W_PRIORINF * gdf_pts["PriorInfra"] +
        W_HEATINF  * gdf_pts["HeatInfra"]  +
        W_HEATLOAD * gdf_pts["HeatLoad"]   +
        W_SOCECON  * gdf_pts["SocEcon"]
    ).round(5)

    # 6 ▸ save CSVs -------------------------------------------------
    gdf_pts[["pk","lat","lon","UNEED",
             "RenewPot","EmgVuln","PriorInfra",
             "HeatInfra","HeatLoad","SocEcon"]] \
        .rename(columns={"pk":"parish"}) \
        .to_csv(CSV_UNEED_FULL, index=False, float_format="%.5f")

    gdf_pts[["pk","lat","lon","UNEED"]].rename(columns={"pk":"parish"}) \
        .to_csv(CSV_UNEED_PTS, index=False, float_format="%.5f")

    gdf_pts.dropna(subset=["pk"]).groupby("pk")["UNEED"].mean() \
        .round(5).reset_index().rename(columns={"pk":"parish"}) \
        .to_csv(CSV_UNEED_PAR, index=False, float_format="%.5f")

    print("[OK] all UNEED CSVs saved → datasets/indexes/")

    # 7 ▸ GeoJSON ---------------------------------------------------
    gdf_par_layer = gdf_par.rename(columns={"name":"parish"})[["parish","geometry"]]
    gdf_par_layer["layer"]="parish"
    outline = gpd.GeoDataFrame({"layer":["city_boundary"]},
                               geometry=[poly], crs=CRS_WGS84)
    gdf_out = pd.concat([gdf_pts, gdf_par_layer, outline], ignore_index=True)
    gdf_out.to_file(OUT_GEOJSON, driver="GeoJSON")
    print(f"[OK] GeoJSON saved → {OUT_GEOJSON}")

# ------------------------------------------------------------------
# UNIT TEST
# ------------------------------------------------------------------
if __name__ == "__main__":
    print("[STEP] Running UNEED pipeline for Porto-PT …")
    run_pipeline()