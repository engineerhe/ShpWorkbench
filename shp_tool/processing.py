from pathlib import Path
import geopandas as gpd
import pandas as pd

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

def export_one(input_path, output_path, config):
    gdf = read_shp(input_path, encoding=config.get("input_encoding", "UTF-8"))
    source_crs = gdf.crs
    if source_crs is None:
        if not config.get("missing_source_crs"):
            raise ValueError("原始 Shapefile 未定义坐标系，且未设置缺失源坐标系")
        # set_crs assigns CRS metadata; it does NOT alter coordinate values.
        gdf = gdf.set_crs(config["missing_source_crs"], allow_override=True)
    gdf = apply_filters(gdf, config["filters"])

    geometry_name = gdf.geometry.name
    mapping = config["mapping"]
    selected = {}
    for src, dst in mapping:
        if src and dst and src in gdf.columns:
            selected[dst] = gdf[src]
    out = gpd.GeoDataFrame(selected, geometry=gdf.geometry, crs=gdf.crs)
    target_crs = config.get("target_crs", "").strip()
    if target_crs:
        out = out.to_crs(target_crs)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    # Shapefile field names are limited to 10 characters; reject rather than silently collide.
    names = [c for c in out.columns if c != out.geometry.name]
    long_names = [n for n in names if len(n.encode("ascii", errors="ignore")) > 10 or len(n) > 10]
    if long_names:
        raise ValueError("Shapefile 字段名最长 10 个字符，请修改输出字段名：" + ", ".join(long_names))
    out.to_file(output_path, driver="ESRI Shapefile", encoding="UTF-8", engine="pyogrio")
    return len(gdf), len(out), source_crs, out.crs

def batch_export(input_dir, output_dir, config, recursive=True, progress=None):
    root, dest = Path(input_dir), Path(output_dir)
    files = sorted(root.rglob("*.shp") if recursive else root.glob("*.shp"))
    results = []
    for i, src in enumerate(files, 1):
        relative = src.relative_to(root)
        target = dest / relative
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            n0, n1, crs0, crs1 = export_one(src, target, config)
            results.append((str(src), "成功", f"{n0} 条输入 / {n1} 条导出"))
        except Exception as exc:
            results.append((str(src), "失败", str(exc)))
        if progress:
            progress(i, len(files), results[-1])
    return results
