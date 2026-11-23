from pathlib import Path
import geopandas as gpd
import numpy as np
import pandas as pd
from .inundation import inundated_areas, load_land_use, write_report

TIME_GRADES = ((0.5, 1.0, 1.5, 2.0), ("<0.5h", "0.5-1.0h", "1.0-1.5h", "1.5-2h", ">=2h"))
GRADE_RULES = {
    "YMSS": ((0.5, 1.0, 2.0, 3.0), ("<0.5m", "0.5-1.0m", "1.0-2.0m", "2.0-3.0m", ">=3.0m")),
    "YMLS": TIME_GRADES,
    "DDSJ": TIME_GRADES,
    "HSLS": ((0.5, 1.0, 2.0, 3.0), ("<0.5m/s", "0.5-1.0m/s", "1.0-2.0m/s", "2.0-3.0m/s", ">=3m/s")),
}

OPS = {
    "等于": "==", "不等于": "!=", "大于": ">", "大于等于": ">=",
    "小于": "<", "小于等于": "<=", "包含": "contains", "不为空": "notnull",
    "为空": "isnull"
}

def read_shp(path, encoding="UTF-8"):
    # pyogrio is used explicitly for predictable and relatively fast vector IO.
    return gpd.read_file(path, engine="pyogrio", encoding=encoding)

def apply_filters(gdf, filters):
    result = gdf.copy()
    for f in filters:
        field, op, value = f["field"], f["op"], f.get("value", "")
        if field not in result.columns:
            raise ValueError(f"过滤字段不存在：{field}")
        s = result[field]
        if op == "等于":
            result = result[s.astype(str) == value]
        elif op == "不等于":
            result = result[s.astype(str) != value]
        elif op in ("大于", "大于等于", "小于", "小于等于"):
            numeric = pd.to_numeric(s, errors="coerce")
            try: v = float(value)
            except ValueError: raise ValueError(f"字段 {field} 的比较值必须是数字")
            mask = {"大于": numeric > v, "大于等于": numeric >= v,
                    "小于": numeric < v, "小于等于": numeric <= v}[op]
            result = result[mask]
        elif op == "包含":
            result = result[s.astype(str).str.contains(value, na=False, regex=False)]
        elif op == "不为空":
            result = result[s.notna() & (s.astype(str).str.strip() != "")]
        elif op == "为空":
            result = result[s.isna() | (s.astype(str).str.strip() == "")]
    return result

def export_one(input_path, output_path, config, summarize=None):
    mapping = config["mapping"]
    outputs = [dst for _, dst in mapping]
    if not outputs or any(dst not in GRADE_RULES for dst in outputs):
        raise ValueError("请选择至少一个有效的输出字段")
    if len(outputs) != len(set(outputs)):
        raise ValueError("输出字段名不能重复")
    gdf = read_shp(input_path, encoding=config.get("input_encoding", "UTF-8"))
    input_count = len(gdf)
    source_crs = gdf.crs
    if source_crs is None:
        if not config.get("missing_source_crs"):
            raise ValueError("原始 Shapefile 未定义坐标系，且未设置缺失源坐标系")
        # set_crs assigns CRS metadata; it does NOT alter coordinate values.
        gdf = gdf.set_crs(config["missing_source_crs"], allow_override=True)
    if summarize is not None:
        summarize(gdf)
    # Align the geometry and source attributes with the positional output arrays.
    gdf = apply_filters(gdf, config["filters"]).reset_index(drop=True)
    geometry = gdf.geometry.rename("geometry")
    target_crs = config.get("target_crs", "").strip()
    if target_crs:
        geometry = geometry.to_crs(target_crs)

    layers = []
    output_path = Path(output_path)
    for src, dst in mapping:
        if src not in gdf.columns or src == gdf.geometry.name:
            raise ValueError(f"源字段不存在：{src}")
        values = pd.to_numeric(gdf[src], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
        valid = np.isfinite(values)
        if dst in ("DDSJ", "YMLS"):
            values = values / 3600
        values = np.round(np.where(valid, values, np.nan), 3)
        thresholds, labels = GRADE_RULES[dst]
        bins = np.searchsorted(thresholds, values[valid], side="right")
        grades = pd.array(np.zeros(len(gdf), dtype=np.int16), dtype="Int16")
        grades[valid] = bins + 1
        grades[~valid] = pd.NA
        descriptions = np.full(len(gdf), None, dtype=object)
        descriptions[valid] = np.asarray(labels, dtype=object)[bins]
        out = gpd.GeoDataFrame({
            dst: values,
            "Grade": grades,
            "Describe": descriptions,
        }, geometry=geometry, crs=geometry.crs)
        target = output_path
        if len(mapping) > 1:
            target = target.with_name(f"{target.stem}_{dst}{target.suffix}")
        layers.append((target, out))

    for target, out in layers:
        target.parent.mkdir(parents=True, exist_ok=True)
        out.to_file(target, driver="ESRI Shapefile", encoding="UTF-8", engine="pyogrio", index=False)
    return input_count, len(gdf), source_crs, geometry.crs

def batch_export(input_dir, output_dir, config, recursive=True, progress=None):
    root, dest = Path(input_dir), Path(output_dir)
    files = sorted(root.rglob("*.shp") if recursive else root.glob("*.shp"))
    results = []
    report_dir = config.get("statistics_dir")
    rows = []
    if report_dir:
        try:
            import openpyxl
        except ModuleNotFoundError as exc:
            if exc.name != "openpyxl":
                raise
            raise RuntimeError("统计淹没面积需要 openpyxl，请在当前 Python 环境运行 python -m pip install openpyxl") from exc
        land = load_land_use()
        mapped_depth = next((src for src, dst in config["mapping"] if dst == "YMSS"), None)

        def summarize(gdf):
            depth_field = mapped_depth or next((name for name in ("YMSS", "最大水深") if name in gdf), "YMSS")
            areas = inundated_areas(gdf, depth_field, land)
            row.extend(areas.values())

    for i, src in enumerate(files, 1):
        relative = src.relative_to(root)
        target = dest / relative
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            row = [str(relative)]
            n0, n1, crs0, crs1 = export_one(src, target, config, summarize if report_dir else None)
            if report_dir:
                rows.append(row)
            results.append((str(src), "成功", f"{n0} 条输入 / {n1} 条导出"))
        except Exception as exc:
            results.append((str(src), "失败", str(exc)))
        if progress:
            progress(i, len(files), results[-1])
    if report_dir:
        write_report(report_dir, rows)
    return results
