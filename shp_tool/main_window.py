from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QPushButton,
    QLabel, QLineEdit, QFileDialog, QComboBox, QTableWidget, QTableWidgetItem,
    QTabWidget, QMessageBox, QProgressBar, QCheckBox, QHeaderView, QGroupBox,
    QSplitter, QAbstractItemView
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from .processing import read_shp, batch_export, GRADE_RULES, OPS

DEFAULT_OUTPUTS = {
    "最大水深": "YMSS",
    "最大流速": "HSLS",
    "淹没历时": "YMLS",
    "fst": "DDSJ",
}

class MapCanvas(FigureCanvasQTAgg):
    def __init__(self):
        self.figure = Figure(figsize=(6, 4), tight_layout=True)
        self.ax = self.figure.add_subplot(111)
        super().__init__(self.figure)
    def show_gdf(self, gdf):
        self.ax.clear()
        if len(gdf):
            gdf.plot(ax=self.ax, linewidth=0.7, markersize=4)
            self.ax.set_aspect("equal", adjustable="datalim")
            self.ax.set_title(f"要素数：{len(gdf)}")
        else:
            self.ax.text(.5, .5, "无要素", ha="center", va="center")
        self.ax.set_axis_off()
        self.draw()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ShpWorkbench - Shapefile 处理工作台")
        self.resize(1280, 820)
        self.current_gdf = None
        self.current_path = ""
        self._build_ui()

    def _build_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        main = QVBoxLayout(root)
        tabs = QTabWidget(); main.addWidget(tabs)

        preview_tab = QWidget(); tabs.addTab(preview_tab, "数据预览")
        pv = QVBoxLayout(preview_tab)
        top = QHBoxLayout()
        self.preview_path = QLineEdit(); self.preview_path.setPlaceholderText("选择一个 .shp 文件")
        b = QPushButton("浏览…"); b.clicked.connect(self.choose_preview)
        load = QPushButton("加载预览"); load.clicked.connect(self.load_preview)
        top.addWidget(self.preview_path, 1); top.addWidget(b)
        top.addWidget(QLabel("输入编码："))
        self.input_encoding = QComboBox()
        self.input_encoding.addItems(["UTF-8", "GBK", "GB2312"])
        self.input_encoding.setCurrentText("UTF-8")
        self.input_encoding.setToolTip("指定 Shapefile DBF 属性表的读取编码；批量导出也使用该编码读取源文件")
        top.addWidget(self.input_encoding)
        top.addWidget(load); pv.addLayout(top)
        split = QSplitter(Qt.Horizontal)
        self.map_canvas = MapCanvas(); split.addWidget(self.map_canvas)
        self.attr_table = QTableWidget(); self.attr_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.attr_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        split.addWidget(self.attr_table); split.setSizes([550, 650]); pv.addWidget(split)

        config_tab = QWidget(); tabs.addTab(config_tab, "字段映射与过滤")
        cv = QVBoxLayout(config_tab)
        note = QLabel("先在“数据预览”加载一个代表性 Shapefile，再配置字段映射。批处理时将同一映射规则应用于文件夹内所有 Shapefile。")
        note.setWordWrap(True); cv.addWidget(note)
        self.mapping_table = QTableWidget(0, 2)
        self.mapping_table.setHorizontalHeaderLabels(["源字段", "输出字段"])
        self.mapping_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        cv.addWidget(QLabel("选择输出指标，留空跳过该行。选择多个指标时分别导出，每份自动添加 Grade 和 Describe。"))
        cv.addWidget(self.mapping_table)
        mb = QHBoxLayout()
        add_map = QPushButton("添加映射行"); add_map.clicked.connect(self.add_mapping_row)
        auto = QPushButton("按原字段自动映射"); auto.clicked.connect(self.auto_mapping)
        mb.addWidget(add_map); mb.addWidget(auto); mb.addStretch(); cv.addLayout(mb)
        cv.addWidget(QLabel("属性过滤（多条条件按 AND 关系组合）"))
        self.filter_table = QTableWidget(0, 3)
        self.filter_table.setHorizontalHeaderLabels(["字段", "条件", "比较值"])
        self.filter_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        cv.addWidget(self.filter_table)
        fb = QHBoxLayout()
        add_filter = QPushButton("添加过滤条件"); add_filter.clicked.connect(self.add_filter_row)
        del_filter = QPushButton("删除选中条件"); del_filter.clicked.connect(lambda: self.filter_table.removeRow(self.filter_table.currentRow()) if self.filter_table.currentRow() >= 0 else None)
        fb.addWidget(add_filter); fb.addWidget(del_filter); fb.addStretch(); cv.addLayout(fb)

        export_tab = QWidget(); tabs.addTab(export_tab, "批量导出")
        ev = QVBoxLayout(export_tab)
        form = QFormLayout()
        self.input_dir = QLineEdit(); ib = QPushButton("选择…"); ib.clicked.connect(self.choose_input)
        ir = QHBoxLayout(); ir.addWidget(self.input_dir); ir.addWidget(ib)
        iw = QWidget(); iw.setLayout(ir); form.addRow("输入文件夹：", iw)
        self.output_dir = QLineEdit(); ob = QPushButton("选择…"); ob.clicked.connect(self.choose_output)
        orow = QHBoxLayout(); orow.addWidget(self.output_dir); orow.addWidget(ob)
        ow = QWidget(); ow.setLayout(orow); form.addRow("输出文件夹：", ow)
        self.missing_crs = QLineEdit("EPSG:4547"); self.missing_crs.setPlaceholderText("例如 EPSG:4547")
        form.addRow("缺失源 CRS 时按此认定：", self.missing_crs)
        self.target_crs = QLineEdit("EPSG:4490"); self.target_crs.setPlaceholderText("例如 EPSG:4326；留空则保持源坐标系")
        form.addRow("输出目标 CRS：", self.target_crs)
        ev.addLayout(form)
        self.recursive = QCheckBox("递归处理输入文件夹的所有子目录"); self.recursive.setChecked(True); ev.addWidget(self.recursive)
        self.statistics_enabled = QCheckBox("统计淹没面积")
        self.statistics_enabled.setToolTip("将淹没面积统计表保存到输出文件夹")
        ev.addWidget(self.statistics_enabled)
        self.run_btn = QPushButton("开始批量处理"); self.run_btn.clicked.connect(self.run_batch); ev.addWidget(self.run_btn)
        self.progress = QProgressBar(); ev.addWidget(self.progress)
        self.log = QTableWidget(0, 3); self.log.setHorizontalHeaderLabels(["文件", "状态", "详情"])
        self.log.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.log.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        ev.addWidget(self.log)

        self.statusBar().showMessage("就绪")

    def choose_preview(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择 Shapefile", "", "Shapefile (*.shp)")
        if p: self.preview_path.setText(p); self.load_preview()

    def load_preview(self):
        p = self.preview_path.text().strip()
        if not p: return
        try:
            self.current_gdf = read_shp(p, encoding=self.input_encoding.currentText()); self.current_path = p
            self.map_canvas.show_gdf(self.current_gdf)
            attrs = self.current_gdf.drop(columns=[self.current_gdf.geometry.name], errors="ignore")
            self.attr_table.clear(); self.attr_table.setRowCount(min(len(attrs), 500))
            self.attr_table.setColumnCount(len(attrs.columns)); self.attr_table.setHorizontalHeaderLabels([str(c) for c in attrs.columns])
            for r in range(min(len(attrs), 500)):
                for c, name in enumerate(attrs.columns):
                    val = attrs.iloc[r, c]
                    self.attr_table.setItem(r, c, QTableWidgetItem("" if val is None else str(val)))
            self.attr_table.setToolTip("属性表最多展示前 500 条记录；导出处理全部记录。")
            self.auto_mapping()
            self.statusBar().showMessage(f"已加载：{p}；{len(self.current_gdf)} 条要素；CRS={self.current_gdf.crs}")
        except Exception as e:
            QMessageBox.critical(self, "加载失败", str(e))

    def auto_mapping(self):
        if self.current_gdf is None: return
        cols = [c for c in self.current_gdf.columns if c != self.current_gdf.geometry.name]
        self.mapping_table.setRowCount(len(cols))
        assigned = set()
        for r, c in enumerate(cols):
            combo = QComboBox(); combo.addItems(cols); combo.setCurrentText(c)
            self.mapping_table.setCellWidget(r, 0, combo)
            output = self.add_output_combo(r)
            preferred = c.upper() if c.upper() in GRADE_RULES else DEFAULT_OUTPUTS.get(c, "")
            if preferred and preferred not in assigned:
                output.setCurrentText(preferred)
                assigned.add(preferred)

    def add_mapping_row(self):
        r = self.mapping_table.rowCount(); self.mapping_table.insertRow(r)
        combo = QComboBox()
        if self.current_gdf is not None:
            combo.addItems([c for c in self.current_gdf.columns if c != self.current_gdf.geometry.name])
        self.mapping_table.setCellWidget(r, 0, combo)
        self.add_output_combo(r)

    def add_output_combo(self, row):
        combo = QComboBox()
        combo.addItems(["", *GRADE_RULES])
        self.mapping_table.setCellWidget(row, 1, combo)
        return combo

    def add_filter_row(self):
        r = self.filter_table.rowCount(); self.filter_table.insertRow(r)
        field = QComboBox()
        if self.current_gdf is not None:
            field.addItems([c for c in self.current_gdf.columns if c != self.current_gdf.geometry.name])
        op = QComboBox(); op.addItems(list(OPS.keys()))
        self.filter_table.setCellWidget(r, 0, field); self.filter_table.setCellWidget(r, 1, op)
        self.filter_table.setItem(r, 2, QTableWidgetItem(""))

    def get_config(self):
        mapping = []
        for r in range(self.mapping_table.rowCount()):
            combo = self.mapping_table.cellWidget(r, 0)
            dst = self.mapping_table.cellWidget(r, 1)
            if combo and dst and dst.currentText():
                mapping.append((combo.currentText(), dst.currentText()))
        if not mapping:
            raise ValueError("请选择至少一个输出字段")
        # Avoid duplicate output names.
        outputs = [x[1] for x in mapping]
        if len(outputs) != len(set(outputs)):
            raise ValueError("输出字段名不能重复")
        filters = []
        for r in range(self.filter_table.rowCount()):
            field = self.filter_table.cellWidget(r, 0); op = self.filter_table.cellWidget(r, 1)
            value = self.filter_table.item(r, 2)
            if field and op:
                filters.append({"field": field.currentText(), "op": op.currentText(),
                                "value": value.text() if value else ""})
        return {"mapping": mapping, "filters": filters,
                "missing_source_crs": self.missing_crs.text().strip(),
                "target_crs": self.target_crs.text().strip(),
                 "input_encoding": self.input_encoding.currentText()}

    def choose_input(self):
        p = QFileDialog.getExistingDirectory(self, "选择输入文件夹")
        if p: self.input_dir.setText(p)
    def choose_output(self):
        p = QFileDialog.getExistingDirectory(self, "选择输出文件夹")
        if p: self.output_dir.setText(p)

    def run_batch(self):
        src, dst = self.input_dir.text().strip(), self.output_dir.text().strip()
        if not src or not dst:
            QMessageBox.warning(self, "参数不完整", "请先选择输入文件夹和输出文件夹"); return
        try:
            config = self.get_config()
            if self.statistics_enabled.isChecked():
                config["statistics_dir"] = dst
        except Exception as e:
            QMessageBox.critical(self, "配置错误", str(e)); return
        self.log.setRowCount(0); self.progress.setValue(0); self.run_btn.setEnabled(False)
        def on_progress(i, total, result):
            self.progress.setMaximum(max(total, 1)); self.progress.setValue(i)
            r = self.log.rowCount(); self.log.insertRow(r)
            for c, value in enumerate(result):
                self.log.setItem(r, c, QTableWidgetItem(str(value)))
        try:
            results = batch_export(src, dst, config, self.recursive.isChecked(), on_progress)
            ok = sum(1 for x in results if x[1] == "成功")
            QMessageBox.information(self, "处理完成", f"处理 {len(results)} 个文件，成功 {ok} 个，失败 {len(results)-ok} 个。")
        except Exception as e:
            QMessageBox.critical(self, "处理失败", str(e))
        finally:
            self.run_btn.setEnabled(True)
