# ShpWorkbench：PySide6 + GeoPandas Shapefile 处理工作台

## 1. 功能
- Shapefile 地图预览及属性表预览（属性表最多显示前 500 条，导出处理全部记录）。
- 查看输入数据 CRS。
- 字段映射：选择源字段并定义输出字段名。
- 属性过滤：支持等于、不等于、大于、大于等于、小于、小于等于、包含、为空、不为空；多条件 AND。
- 批量处理输入目录，可递归子目录；输出目录保留相对目录结构。
- 原始 SHP 缺少 CRS 时，按“缺失源 CRS”参数给输入坐标赋予 CRS，再转换到目标 CRS。

## 2. 安装
建议 Python 3.11/3.12，Windows 10/11 64 位。使用独立环境：

```bash
conda create -n shpworkbench python=3.11 -y
conda activate shpworkbench
python -m pip install -r requirements.txt
python main.py
```

如果 pip 安装 geopandas/pyogrio 时遇到 GDAL 二进制依赖问题，推荐用 conda-forge：

```bash
conda create -n shpworkbench -c conda-forge python=3.11 geopandas pyogrio pyproj shapely matplotlib pyside6 -y
conda activate shpworkbench
python main.py
```

## 3. CRS 语义（务必区分）
- **缺失源 CRS 时按此认定**：仅当源 SHP 没有 `.prj` / 无法识别 CRS 时使用。该操作是 `set_crs`，只补充坐标系元数据，不改变坐标数值。
- **输出目标 CRS**：执行 `to_crs`，会进行真正的坐标转换并改变坐标数值。
- 如果源文件已有 CRS，则以源文件 CRS 为准，不会被“缺失源 CRS”覆盖。
- 如果源 CRS 缺失，必须确认“缺失源 CRS”填写的确实是原始坐标实际所属 CRS，否则转换结果会错误。
- 目标 CRS 留空表示不转换，沿用源 CRS。

## 4. 字段映射规则
- 每行表示“源字段 -> 输出字段”。
- 默认自动映射所有属性字段；可修改输出字段名、删除不需要的行（选中行后可删除，当前示例 UI 仅提供添加行，删除可直接清空输出字段名）。
- Shapefile 字段名最多 10 个字符；字段名重复或超长会报错，不静默截断。
- 当前版本保留几何字段，属性字段按映射表输出。

## 5. 批处理行为
- 仅扫描 `.shp`，依赖同目录下 `.shx/.dbf/.prj` 等配套文件。
- 输出路径保持输入目录相对路径；不要将输出目录放在输入目录内部，否则递归模式可能再次扫描输出文件。
- 每个文件单独捕获异常，失败文件不会中断后续文件。
- 同名输出文件会被覆盖，请先备份重要数据。

## 6. 推荐的后续架构演进
将处理能力拆成独立 Processor/Algorithm：
- `io`: 读取、写入、格式适配（SHP、GeoPackage、GeoJSON、GeoTIFF）。
- `crs`: CRS 识别、赋值、转换、坐标检查。
- `attribute`: 字段映射、字段计算、过滤、统计。
- `geometry`: 修复、简化、缓冲、裁剪、相交、合并、空间连接。
- `workflow`: 算法参数、任务队列、批处理、日志、断点与结果报告。
- `ui`: 只负责参数收集、预览、任务状态展示，不直接承载 GIS 算法。

后续建议引入统一算法接口、参数模型、执行上下文和任务管理器；耗时任务迁移到 QThreadPool/QRunnable，避免当前同步批处理阻塞 GUI。当前版本以可运行的单机 MVP 为目标，批处理期间界面会短暂阻塞，适合先验证业务流程。

## 7.打包操作
python -m PyInstaller --clean --noconfirm ShpWorkbench.spec