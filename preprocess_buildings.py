"""
preprocess_buildings.py
============================================================
Download & preprocess OSM building footprints, classify them,
join with parish polygons, add simple energy‑demand metrics
(HDD / CDD, E_heating, E_cooling) using ERA‑like daily T2M grid.

Output  ........  ./datasets/buildings.csv
Columns ......... classification , parish , lat , lon ,
                  area_m2 , HDD , CDD , E_Heating , E_Cooling
------------------------------------------------------------
Author: Thiago C. Jesus
Part of the UNEED microgrid-positioning framework (MIT License).
"""

#How to use in the larger project
#    from preprocess_buildings import process_buildings  # or just run the script

# --------------------------------------------------------------------
#                            IMPORTS
# --------------------------------------------------------------------
from pathlib import Path
from typing import Final, List, Tuple, Optional

import geopandas as gpd
import osmnx as ox
import pandas as pd
from shapely.geometry.base import BaseGeometry
from shapely.geometry import Point

from get_parishes import get_or_create_parish_geojson  #  already built

import math

# --------------------------------------------------------------------
#                         CONSTANTS
# --------------------------------------------------------------------
COUNTRY:              Final[str] = "Portugal"
CITY:                 Final[str] = "Porto"

# CRS
CRS_WGS84:            Final[int] = 4326
CRS_AREA_PT:          Final[int] = 3763          # ETRS89 / Portugal Mainland

# (temp) comfort temperature for HDD / CDD
T_COMFORT:            Final[float] = 18.0

# Building age threshold
YEAR_THRESHOLD:       Final[int]   = 1990

# Directories
RAW_DIR:              Final[Path] = Path("./rawData")
DATASET_DIR:          Final[Path] = Path("./datasets")
DATASET_DIR.mkdir(parents=True, exist_ok=True)

RAW_TEMP_FILE:        Final[Path] = RAW_DIR / "temp.csv"
OUT_CSV:              Final[Path] = DATASET_DIR / "preprocessed_buildings.csv"

# --------------------------------------------------------------------
#                      AUXILIARY – ENERGY HELPERS
# --------------------------------------------------------------------
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great‑circle distance (km)."""
    R = 6371.0
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def get_hdd(base: float, temps: List[float]) -> float:
    return sum(max(base - t, 0) for t in temps)


def get_cdd(base: float, temps: List[float]) -> float:
    return sum(max(t - base, 0) for t in temps)


def heating_load(area: float, hdd: float,
                 u_avg: float, cop: float) -> float:
    return area * hdd * u_avg * 24.0 / cop


def cooling_load(area: float, cdd: float,
                 u_avg: float, cop: float) -> float:
    return area * cdd * u_avg * 24.0 / cop


def u_value(classif: str) -> float:
    c = classif.lower()
    if "old" in c:
        return 2.0
    if "new" in c:
        return 0.55
    if "commercial" in c:
        return 2.0
    return 1.5


def cop_heating(classif: str) -> float:
    c = classif.lower()
    return 0.875 if "old" in c else 3.25


def cop_cooling(classif: str) -> float:
    c = classif.lower()
    return 1.0 if "old" in c else 4.0


# --------------------------------------------------------------------
#            BUILDING FETCH / CLASSIFICATION / GEOMETRY
# --------------------------------------------------------------------
#def fetch_buildings(city_polygon: BaseGeometry) -> gpd.GeoDataFrame:
    """OSM request restricted to the union polygon of the city."""
    #tags = {"building": True}
    #gdf = ox.features_from_polygon(city_polygon, tags=tags)
    #gdf = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])]
    #return gdf.to_crs(epsg=CRS_WGS84)

def fetch_buildings(poly: BaseGeometry) -> gpd.GeoDataFrame:
    tags = {"building": True}
    gdf = ox.features_from_polygon(poly, tags=tags)
    gdf = gdf[gdf.geometry.type.isin(["Polygon","MultiPolygon"])]\
            .to_crs(epsg=CRS_WGS84)
    # --- de‑duplicate by geometry -----
    gdf["geom_wkb"] = gdf.geometry.apply(lambda g: g.wkb)
    gdf = gdf.drop_duplicates(subset="geom_wkb").drop(columns="geom_wkb")
    return gdf


def classify_building(row: pd.Series, year_threshold=1990) -> str:
    """
    Classifies a building into:
      - 'Heritage building'
      - 'Historic building'
      - 'Old building'
      - 'Commercial building'
      - 'New building'
    in that order of precedence.

    This aims to increase the likelihood of classifying buildings as "New" when
    insufficient evidence suggests they are old, heritage, or otherwise.

    Return building class string.
    """


    # Safely retrieve strings
    b_value = str(row.get("building", "") or "").lower().strip()
    style = str(row.get("architectural_style", "") or "").lower().strip()
    material = str(row.get("building:material", "") or "").lower().strip()
    hist_tag = str(row.get("historic", "") or "").lower().strip()
    herit_tag = str(row.get("heritage", "") or "").lower().strip()

    
    # 2) Commercial building
    if any(word in b_value for word in ["commercial", "retail", "industrial", "office"]):
        return "Commercial building"

    # 3) Explicit year checks
    for year_tag in ["start_date", "building:year"]:
        val = row.get(year_tag)
        if val:
            try:
                year_val = int(str(val)[:4])  # e.g. "1987-01-01" => 1987
                if year_val >= year_threshold:
                    return "New building"
                else:
                    return "Old building"
            except ValueError:
                pass

    # 4) Modern style/material => new
    modern_materials = ["concrete", "glass", "steel", "metal"]
    modern_styles = ["modern", "contemporary", "postmodern"]
    if any(m in material for m in modern_materials):
        return "New building"
    if any(ms in style for ms in modern_styles):
        return "New building"

    # 5) Known old building indicators
    known_old_styles = ["roman", "medieval", "gothic", "baroque", "renaissance", "neoclassical"]
    known_old_materials = ["stone", "half-timbered", "timber_frame", "wattle_and_daub", "brick"]
    old_building_types = ["church", "cathedral", "castle", "chapel", "temple", "ruins"]

    if any(s in style for s in known_old_styles):
        return "Old building"
    if any(m in material for m in known_old_materials):
        return "Old building"
    if any(t in b_value for t in old_building_types):
        return "Old building"



    

    # 6) Special handling for building=yes
    #    If building=yes and STILL no classification, do a second pass.
    if b_value == "yes":
        # Example: check additional minor tags. 
        # If there's a partial date or a roof style that might be old, label old. 
        # Otherwise new.

        # a) Check for partial date or other potential old hints
        # e.g., maybe there's a tag "roof:material=tile" or "roof:shape=hipped" commonly old.
        roof_material = str(row.get("roof:material", "") or "").lower().strip()
        roof_shape = str(row.get("roof:shape", "") or "").lower().strip()
        # Arbitrary logic: tile or slate roofs might imply older building, but not always. 
        # Tweak these as necessary for your region:
        old_roof_materials = ["slate", "tile", "thatch", "wood"]

        if any(r in roof_material for r in old_roof_materials):
            return "Old building"
        # If we find no old hints, we treat it as new
        return "New building"

    
    # 1) Immediately classify heritage/historic
    if hist_tag:
        #print("########   ----   #########")
        #print(row.to_string())
        return "Old building"  #"Historic building"
    if herit_tag:
        return "Old building"  #"Heritage building"
    

    # 7) Final fallback
    return "Old building"


def add_area_centroid(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add columns area_m2, lat, lon."""
    gdf_proj = gdf.to_crs(CRS_AREA_PT)
    gdf["area_m2"] = gdf_proj.area
    cent = gdf_proj.centroid.to_crs(CRS_WGS84)
    gdf["lat"] = cent.y.values
    gdf["lon"] = cent.x.values
    return gdf


# --------------------------------------------------------------------
#                     CLIMATE DATA LOADER
# --------------------------------------------------------------------
def load_climate_grid(path: Path) -> pd.DataFrame:
    """
    Expect ERA‑like temp file with header line + daily rows:
    LAT,LON,YEAR,MO,DY,T2M
    """
    df = pd.read_csv(path, skiprows=1,
                     names=["LAT", "LON", "YEAR", "MO", "DY", "T2M"])
    return df


def nearest_grid_point(lat: float, lon: float,
                       locs: List[Tuple[float, float]]) -> Tuple[float, float, float]:
    """Return (lat, lon, distance_km) of the closest grid node."""
    best = (None, None, 1e9)
    for lt, ln in locs:
        d = haversine_km(lat, lon, lt, ln)
        if d < best[2]:
            best = (lt, ln, d)
    return best


# --------------------------------------------------------------------
#                       MASTER PROCESSOR
# --------------------------------------------------------------------
def process_buildings(city_polygon: BaseGeometry,
                      gdf_parish: gpd.GeoDataFrame,
                      df_temp: pd.DataFrame,
                      year_threshold=1990) -> pd.DataFrame:
    """End‑to‑end pipeline → tidy DataFrame ready for CSV."""

    # 1. Buildings
    gdf_bld = fetch_buildings(city_polygon)
    if gdf_bld.empty:
        raise RuntimeError("No buildings returned by OSM.")

    gdf_bld = add_area_centroid(gdf_bld)

    # 2. Attach parish
    gdf_parish = gdf_parish.rename(columns={"name": "parish_name"})
    gdf_bld["centroid_pt"] = gdf_bld.apply(
        lambda r: Point(r["lon"], r["lat"]), axis=1
    )
    gdf_pts = gpd.GeoDataFrame(gdf_bld, geometry="centroid_pt", crs=CRS_WGS84)
    join = gpd.sjoin(
        gdf_pts,
        gdf_parish[["parish_name", "geometry"]],
        how="inner",
        predicate="within",
    )

    # 3. Prepare temp grid
    #grid_locs = df_temp[["LAT", "LON"]].drop_duplicates().values.tolist()

    grid_locs = list(df_temp[["LAT","LON"]].drop_duplicates().itertuples(index=False,name=None))

    # 4. Loop & compute metrics
    records = []
    for _, row in join.iterrows():
        cls  = classify_building(row,year_threshold)
        area = row["area_m2"]
        lat, lon = row["lat"], row["lon"]

        g_lat, g_lon, dist = nearest_grid_point(lat, lon, grid_locs)
        temps = df_temp.query("LAT == @g_lat and LON == @g_lon")["T2M"].values

        hdd = get_hdd(T_COMFORT, temps)
        cdd = get_cdd(T_COMFORT, temps)

        u   = u_value(cls)
        cop_h = cop_heating(cls)
        cop_c = cop_cooling(cls)

        e_h = heating_load(area, hdd, u, cop_h)
        e_c = cooling_load(area, cdd, u, cop_c)

        records.append({
            "classification": cls,
            "parish": row["parish_name"],
            "lat": lat,
            "lon": lon,
            "area_m2": round(area, 2),
            "HDD": round(hdd, 2),
            "CDD": round(cdd, 2),
            "E_Heating": round(e_h, 2),
            "E_Cooling": round(e_c, 2),
            # extra – kept for possible debugging
            "_grid_lat": g_lat,
            "_grid_lon": g_lon,
            "_grid_dist_km": round(dist, 2),
        })

    df = pd.DataFrame.from_records(records)
    return df


# --------------------------------------------------------------------
#                             MAIN (TEST)
# --------------------------------------------------------------------
def main() -> None:
    """Unit‑test pipeline for Porto‑PT."""
    print("[STEP] Load / create parishes …")
    gdf_par = get_or_create_parish_geojson(city=CITY, country=COUNTRY)
    if "name" not in gdf_par.columns:
        raise KeyError("Parish GeoJSON missing 'name' column.")

    print("[STEP] Build city polygon …")
    city_poly = gdf_par.unary_union

    print("[STEP] Load climate grid …")
    df_temp = load_climate_grid(RAW_TEMP_FILE)

    print("[STEP] Process buildings …")
    df_bld = process_buildings(city_poly, gdf_par, df_temp,YEAR_THRESHOLD)

    print("[STEP] Save CSV …")
    keep_cols = [
        "classification", "parish", "lat", "lon", "area_m2",
        "HDD", "CDD", "E_Heating", "E_Cooling"
    ]
    df_bld[keep_cols].to_csv(OUT_CSV, index=False)
    print(f"[OK] {OUT_CSV} written ({len(df_bld)} rows)")

    print(df_bld[keep_cols].head())


     # ------- summary -----------------
    counts=df_bld["classification"].value_counts()
    total=len(df_bld)
    print("--- Classification Summary ---")
    for cat,c in counts.items():
        print(f"{cat}: {c} buildings ({c/total*100:.2f}%)")

# --------------------------------------------------------------------
if __name__ == "__main__":
    main()



#How to use in the larger project
# from preprocess_buildings import process_buildings  # or just run the script