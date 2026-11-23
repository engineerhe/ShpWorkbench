from pathlib import Path

import geopandas as gpd
import pandas as pd


LAND_USE_CLASSES = {
    "耕地": ("水田", "水浇地", "旱地"),
    "园地": ("茶园", "果园", "其他园地"),
    "林地": ("其他林地", "竹林地", "乔木林地", "灌木林地"),
    "草地": ("其他草地",),
    "水域 / 水利": ("干渠", "水库水面", "水工建筑用地", "可调整养殖坑塘", "坑塘水面", "沟渠", "河流水面", "养殖坑塘"),
}
LAND_USE_FILE = Path(__file__).parent / "data" / "土地利用.gpkg"
REPORT_NAME = "淹没面积统计.xlsx"


def load_land_use():
    land = gpd.read_file(LAND_USE_FILE, engine="pyogrio", columns=["DLMC"])
    if land.crs is None or "DLMC" not in land:
        raise ValueError("土地利用数据必须包含 DLMC 字段和坐标系")
    classes = {name: category for category, names in LAND_USE_CLASSES.items() for name in names}
    land["类别"] = land["DLMC"].astype("string").str.strip().map(classes)
    land = land.loc[land["类别"].notna() & land.geometry.notna(), ["类别", land.geometry.name]].copy()
    land.geometry = land.geometry.make_valid()
    land.sindex
    return land


def inundated_areas(gdf, depth_field, land):
    if depth_field not in gdf or depth_field == gdf.geometry.name:
        raise ValueError(f"找不到水深字段 {depth_field}，请将源水深字段映射到 YMSS")
    areas = dict.fromkeys(LAND_USE_CLASSES, 0.0)
    depth = pd.to_numeric(gdf[depth_field], errors="coerce")
    wet = gdf.geometry.loc[(depth > 0) & gdf.geometry.notna() & ~gdf.geometry.is_empty]
    if wet.empty:
        return areas
    footprint = wet.to_crs(land.crs).make_valid().union_all()
    candidates = land.iloc[land.sindex.query(footprint, predicate="intersects")]
    for category, group in candidates.groupby("类别"):
        intersection = group.geometry.intersection(footprint).union_all()
        areas[category] = float(gpd.GeoSeries([intersection], crs=land.crs).to_crs(6933).area.iloc[0])
    return areas


def write_report(directory, rows):
    from openpyxl import Workbook

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    columns = ["淹没结果", *(f"{category}（平方米）" for category in LAND_USE_CLASSES)]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "淹没面积统计"
    sheet.append(columns)
    for row in rows:
        sheet.append(row)
    workbook.save(directory / REPORT_NAME)
