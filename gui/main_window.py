"""
主窗口：搜索框 + 元件列表 + 预览 + 下载选项 + 日志区。

优化：
  - 搜索防抖（相同关键字不重复搜索）
  - 预览并行（符号/封装 + 3D 模型两条独立线程）
  - 切换元器件时取消旧的 3D 加载
  - 选中行深蓝高亮
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap, QColor
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QLabel, QCheckBox, QProgressBar, QTextEdit, QRadioButton,
    QGroupBox, QFileDialog, QSplitter, QHeaderView, QButtonGroup,
    QAbstractItemView, QMessageBox, QTabWidget, QScrollArea,
)

from gui.worker import (
    SearchAllWorker, DownloadWorker, PreviewWorker, Model3DWorker,
    SymbolPartWorker,
)
from gui.svg_view import SvgView

try:
    from gui.model_3d_view_gl import Model3DViewGL as _Model3DView
    _USE_GL = True
    print("[main_window] 使用 OpenGL 3D 视图")
except Exception as e:
    print(f"[main_window] OpenGL 不可用 ({e})，回退到 QPainter 视图")
    from gui.model_3d_view import Model3DView as _Model3DView
    _USE_GL = False


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LCEDA → Altium 元器件下载器")
        self.resize(1300, 850)

        # 后台线程引用
        self._search_worker = None
        self._download_worker = None
        self._preview_worker = None
        self._model_worker = None
        self._part_worker = None

        # 状态
        self._last_previewed_lcsc = None
        self._search_raw_cache = {}

        # 防抖：上次搜索的关键字
        self._last_search_keyword = ""

        # 当前元件的部件信息
        self._current_part_count = 1
        self._current_part_titles = []
        self._current_part_index = 0
        self._current_fp_svg = None
        self._current_thumb_bytes = None
        self._current_api_result = None
        self._current_model_3d = None

        self._build_ui()
        self._apply_styles()

    # ============================================================
    # UI 构建
    # ============================================================

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        root.addWidget(self._build_search_bar())

        h_splitter = QSplitter(Qt.Orientation.Horizontal)
        h_splitter.addWidget(self._build_left_panel())
        h_splitter.addWidget(self._build_preview_panel())
        h_splitter.setStretchFactor(0, 3)
        h_splitter.setStretchFactor(1, 2)
        root.addWidget(h_splitter, stretch=1)

        root.addWidget(self._build_options_bar())
        root.addWidget(self._build_library_bar())
        root.addWidget(self._build_progress_bar())

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        v_splitter = QSplitter(Qt.Orientation.Vertical)
        v_splitter.addWidget(self._build_result_table())
        v_splitter.addWidget(self._build_log_area())
        v_splitter.setStretchFactor(0, 3)
        v_splitter.setStretchFactor(1, 1)
        layout.addWidget(v_splitter)

        return panel

    def _build_preview_panel(self) -> QWidget:
        box = QGroupBox("元件预览")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self.preview_tabs = QTabWidget()

        # --- Tab 1：符号 ---
        sym_tab = QWidget()
        sym_layout = QVBoxLayout(sym_tab)
        sym_layout.setContentsMargins(0, 0, 0, 0)
        sym_layout.setSpacing(4)

        self.part_scroll = QScrollArea()
        self.part_scroll.setWidgetResizable(True)
        self.part_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.part_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.part_scroll.setFixedHeight(38)
        self.part_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        self.part_bar = QWidget()
        self.part_bar_layout = QHBoxLayout(self.part_bar)
        self.part_bar_layout.setContentsMargins(4, 2, 4, 2)
        self.part_bar_layout.setSpacing(4)
        self.part_bar_layout.addStretch(1)

        self.part_scroll.setWidget(self.part_bar)
        self.part_scroll.setVisible(False)
        sym_layout.addWidget(self.part_scroll)

        self.symbol_svg = SvgView()
        self.symbol_svg.setMinimumHeight(200)
        sym_layout.addWidget(self.symbol_svg, stretch=1)

        self.preview_tabs.addTab(sym_tab, "符号")

        # --- Tab 2：封装 ---
        fp_tab = QWidget()
        fp_layout = QVBoxLayout(fp_tab)
        fp_layout.setContentsMargins(0, 0, 0, 0)
        self.footprint_svg = SvgView()
        self.footprint_svg.setMinimumHeight(200)
        fp_layout.addWidget(self.footprint_svg)
        self.preview_tabs.addTab(fp_tab, "封装")

        # --- Tab 3：3D 模型 ---
        d3_tab = QWidget()
        d3_layout = QVBoxLayout(d3_tab)
        d3_layout.setContentsMargins(0, 0, 0, 0)
        self.model_3d_view = _Model3DView()
        self.model_3d_view.setMinimumHeight(200)
        d3_layout.addWidget(self.model_3d_view)
        self.preview_tabs.addTab(d3_tab, "3D 模型")

        layout.addWidget(self.preview_tabs)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)

        self.preview_status = QLabel("选中搜索结果中的一行以预览")
        self.preview_status.setStyleSheet("color: #666; font-size: 11px;")

        if _USE_GL:
            hint_text = "符号: 滚轮缩放 · 3D: 左键旋转 / 中键平移 / 滚轮缩放"
        else:
            hint_text = "符号: 滚轮缩放 · 3D: 拖动旋转 · 滚轮缩放 · 双击重置"

        hint = QLabel(hint_text)
        hint.setStyleSheet("color: #999; font-size: 11px;")

        status_row.addWidget(self.preview_status)
        status_row.addStretch(1)
        status_row.addWidget(hint)

        layout.addLayout(status_row)

        return box

    def _build_search_bar(self) -> QWidget:
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel("搜索:")
        label.setFixedWidth(50)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "输入型号、关键字或 LCSC 编号（如 TP4054、C668215、STM32）"
        )
        self.search_input.returnPressed.connect(self._on_search_clicked)

        self.search_button = QPushButton("搜索")
        self.search_button.setFixedWidth(90)
        self.search_button.clicked.connect(self._on_search_clicked)

        layout.addWidget(label)
        layout.addWidget(self.search_input, stretch=1)
        layout.addWidget(self.search_button)

        return box

    def _build_result_table(self) -> QWidget:
        box = QGroupBox("搜索结果")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 8, 8, 8)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["LCSC", "型号", "封装", "描述", "制造商", "库存", "CAD"]
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)

        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        layout.addWidget(self.table)
        return box

    def _build_log_area(self) -> QWidget:
        box = QGroupBox("运行日志")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 8, 8, 8)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))
        self.log.setPlaceholderText("操作日志会显示在这里...")

        layout.addWidget(self.log)
        return box

    def _build_options_bar(self) -> QWidget:
        box = QGroupBox("下载选项")
        layout = QHBoxLayout(box)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(14)

        self.opt_schlib = QCheckBox("生成 SchLib")
        self.opt_schlib.setChecked(True)

        self.opt_pcblib = QCheckBox("生成 PcbLib")
        self.opt_pcblib.setChecked(True)

        self.opt_step = QCheckBox("嵌入 STEP 3D 模型")
        self.opt_step.setChecked(False)

        self.opt_step_only = QCheckBox("仅下载 3D 模型")
        self.opt_step_only.setToolTip(
            "只下载 STEP 3D 模型文件到 output/step/ 目录，按元件型号命名"
        )
        self.opt_step_only.toggled.connect(self._on_step_only_toggled)

        layout.addWidget(self.opt_schlib)
        layout.addWidget(self.opt_pcblib)
        layout.addWidget(self.opt_step)

        sep = QLabel("|")
        sep.setStyleSheet("color: #bbb;")
        layout.addWidget(sep)

        layout.addWidget(self.opt_step_only)

        sep2 = QLabel("|")
        sep2.setStyleSheet("color: #bbb;")
        layout.addWidget(sep2)

        layout.addWidget(QLabel("输出目录:"))
        self.output_dir = QLineEdit("output")
        self.output_dir.setReadOnly(True)
        layout.addWidget(self.output_dir, stretch=1)

        self.browse_button = QPushButton("浏览...")
        self.browse_button.setFixedWidth(80)
        self.browse_button.clicked.connect(self._on_browse_clicked)
        layout.addWidget(self.browse_button)

        return box

    def _build_library_bar(self) -> QWidget:
        box = QGroupBox("库文件命名")
        layout = QHBoxLayout(box)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(14)

        self.lib_mode_group = QButtonGroup(self)

        self.rb_per_comp = QRadioButton("每个元器件独立库")
        self.rb_per_comp.setChecked(True)
        self.rb_per_comp.toggled.connect(self._on_lib_mode_changed)

        self.rb_shared = QRadioButton("所有元器件写入同一个库")

        self.lib_mode_group.addButton(self.rb_per_comp, 0)
        self.lib_mode_group.addButton(self.rb_shared, 1)

        layout.addWidget(self.rb_per_comp)
        layout.addWidget(self.rb_shared)

        self.opt_append = QCheckBox("追加到已有库")
        self.opt_append.setToolTip(
            "勾选后，如果库文件已存在，新元器件会追加进去；同名符号/封装自动覆盖。"
        )
        self.opt_append.setEnabled(False)
        self.opt_append.toggled.connect(self._on_lib_mode_changed)
        layout.addWidget(self.opt_append)

        sep = QLabel("|")
        sep.setStyleSheet("color: #bbb;")
        layout.addWidget(sep)

        self.lib_name_label = QLabel("库名:")
        self.lib_name_edit = QLineEdit()
        self.lib_name_edit.setPlaceholderText(
            "留空则使用第一个元器件的名称（追加时必填）"
        )
        self.lib_name_edit.setEnabled(False)
        self.lib_name_edit.setFixedWidth(260)

        layout.addWidget(self.lib_name_label)
        layout.addWidget(self.lib_name_edit)
        layout.addStretch(1)

        self.download_button = QPushButton("下载选中")
        self.download_button.setFixedWidth(120)
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self._on_download_clicked)
        layout.addWidget(self.download_button)

        return box

    def _build_progress_bar(self) -> QWidget:
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)

        self.status_label = QLabel("就绪")
        self.status_label.setFixedWidth(500)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setTextVisible(True)

        layout.addWidget(self.status_label)
        layout.addWidget(self.progress, stretch=1)

        return box

    def _apply_styles(self):
        self.setStyleSheet("""
            QMainWindow { background: #f5f5f7; }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #d0d0d5;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 6px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 4px;
                color: #333;
            }
            QPushButton {
                padding: 6px 12px;
                border: 1px solid #c0c0c5;
                border-radius: 4px;
                background: #ffffff;
            }
            QPushButton:hover { background: #eef2ff; }
            QPushButton:pressed { background: #dbe4ff; }
            QPushButton:disabled { color: #999; background: #f0f0f0; }
            QPushButton:checked {
                background: #2563eb;
                color: white;
                border: 1px solid #1d4ed8;
            }
            QLineEdit {
                padding: 6px 10px;
                border: 1px solid #c0c0c5;
                border-radius: 4px;
                background: white;
            }
            QLineEdit:disabled { background: #f5f5f5; color: #999; }

            /* ===== 表格样式 ===== */
            QTableWidget {
                background: white;
                border: none;
                gridline-color: #e5e5ea;
                selection-background-color: #2563eb;
                selection-color: white;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QTableWidget::item:selected {
                background-color: #2563eb;
                color: white;
                font-weight: bold;
            }
            QTableWidget::item:selected:!active {
                background-color: #2563eb;
                color: white;
                font-weight: bold;
            }
            QTableWidget::item:selected:active {
                background-color: #1d4ed8;
                color: white;
                font-weight: bold;
            }

            QHeaderView::section {
                background: #f0f0f5;
                padding: 6px;
                border: none;
                border-right: 1px solid #e0e0e5;
                border-bottom: 1px solid #e0e0e5;
                font-weight: bold;
            }
            QTabWidget::pane { border: 1px solid #e0e0e5; background: white; }
            QTabBar::tab {
                padding: 6px 16px;
                background: #f0f0f5;
                border: 1px solid #e0e0e5;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected { background: white; color: #2563eb; }
        """)

    # ============================================================
    # 事件处理
    # ============================================================

    def _on_step_only_toggled(self, checked):
        if checked:
            self.opt_schlib.setChecked(False)
            self.opt_pcblib.setChecked(False)
            self.opt_step.setChecked(False)
            self.opt_schlib.setEnabled(False)
            self.opt_pcblib.setEnabled(False)
            self.opt_step.setEnabled(False)
        else:
            self.opt_schlib.setEnabled(True)
            self.opt_pcblib.setEnabled(True)
            self.opt_step.setEnabled(True)
            self.opt_schlib.setChecked(True)
            self.opt_pcblib.setChecked(True)

    def _on_lib_mode_changed(self):
        shared = self.rb_shared.isChecked()
        self.lib_name_label.setEnabled(shared)
        self.lib_name_edit.setEnabled(shared)
        self.opt_append.setEnabled(shared)
        if not shared and self.opt_append.isChecked():
            self.opt_append.setChecked(False)

    # ---------- 搜索 ----------

    def _on_search_clicked(self):
        keyword = self.search_input.text().strip()
        if not keyword:
            QMessageBox.information(self, "提示", "请输入搜索关键字")
            return

        # 防抖：相同关键字且正在搜索，忽略
        if (self._search_worker is not None
                and self._search_worker.isRunning()
                and self._last_search_keyword == keyword):
            print(f"[main_window] 忽略重复搜索: {keyword}")
            return

        # 取消上一次搜索
        if self._search_worker is not None and self._search_worker.isRunning():
            self._search_worker.cancel()
            self._search_worker.wait(500)

        self._last_search_keyword = keyword

        self.search_button.setEnabled(False)
        self.search_button.setText("搜索中")
        self._set_status(f"搜索 '{keyword}'...")
        self._log(f"搜索: {keyword}")
        self.progress.setRange(0, 0)

        self.table.setRowCount(0)
        self.download_button.setEnabled(False)
        self._search_raw_cache = {}
        self._last_previewed_lcsc = None
        self._current_api_result = None

        self._search_worker = SearchAllWorker(keyword)
        self._search_worker.page_loaded.connect(self._on_search_page_loaded)
        self._search_worker.all_finished.connect(self._on_search_all_finished)
        self._search_worker.error.connect(self._on_search_error)
        self._search_worker.start()

    def _on_search_page_loaded(self, page: int, products: list):
        if not products:
            return

        for p in products:
            self._search_raw_cache[p["lcsc"]] = p

        start_row = self.table.rowCount()
        self.table.setRowCount(start_row + len(products))

        for i, p in enumerate(products):
            row = start_row + i
            cad_parts = [
                "S" if p.get("has_symbol") else "-",
                "F" if p.get("has_footprint") else "-",
                "3" if p.get("has_3d") else "-",
            ]
            cad_str = "".join(cad_parts)

            items = [
                p.get("lcsc", ""),
                p.get("mpn", ""),
                p.get("package", ""),
                p.get("description", ""),
                p.get("manufacturer", ""),
                str(p.get("stock", "")),
                cad_str,
            ]
            for col, text in enumerate(items):
                item = QTableWidgetItem(str(text))
                item.setToolTip(str(text))
                if cad_str == "---":
                    item.setForeground(QColor("#999999"))
                self.table.setItem(row, col, item)

        total = self.table.rowCount()
        self._set_status(f"搜索中... 已加载 {total} 个 (第 {page} 页)")

    def _on_search_all_finished(self, total: int, success: bool):
        self.search_button.setEnabled(True)
        self.search_button.setText("搜索")
        self.progress.setRange(0, 100)
        self.progress.setValue(100)

        if not success:
            self._set_status("搜索已取消")
            return

        if total == 0:
            self._set_status("未找到结果")
            self._log("搜索完成：0 个结果")
            return

        no_cad = sum(
            1 for p in self._search_raw_cache.values()
            if not (p.get("has_symbol") or p.get("has_footprint"))
        )
        status = f"已加载所有结果 ({total} 个)"
        if no_cad:
            status += f"，其中 {no_cad} 个无 CAD 数据"
        self._set_status(status)
        self._log("搜索完成：" + status)

    def _on_search_error(self, message: str):
        self.search_button.setEnabled(True)
        self.search_button.setText("搜索")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self._set_status("搜索失败")
        self._log(f"[错误] {message}")
        QMessageBox.critical(self, "搜索失败", message[:500])

    # ---------- 预览 ----------

    def _on_selection_changed(self):
        rows = self.table.selectionModel().selectedRows()
        has = len(rows) > 0
        self.download_button.setEnabled(has)

        if len(rows) == 1:
            row = rows[0].row()
            lcsc_item = self.table.item(row, 0)
            if lcsc_item:
                lcsc = lcsc_item.text()
                thumb_url = None
                if lcsc in self._search_raw_cache:
                    thumb_url = self._search_raw_cache[lcsc].get("thumb_url")
                self._start_preview(lcsc, thumb_url)

    def _start_preview(self, lcsc: str, thumb_url: str = None):
        if lcsc == self._last_previewed_lcsc:
            return
        self._last_previewed_lcsc = lcsc
        self._current_api_result = None
        self._current_model_3d = None

        # --- 取消上一个 3D 加载（关键） ---
        if (self._model_worker is not None
                and self._model_worker.isRunning()):
            self._model_worker.cancel()
            print(f"[main_window] 取消上一个 3D 加载")

        # 符号/封装 worker 也取消
        if (self._preview_worker is not None
                and self._preview_worker.isRunning()):
            self._preview_worker.cancel()

        self.preview_status.setText(f"正在加载 {lcsc} 的预览...")
        self.symbol_svg.load(b"")
        self.footprint_svg.load(b"")
        self.model_3d_view.clear()
        self.model_3d_view.set_hint("（正在加载 3D 模型...）")
        self._clear_part_buttons()

        self._preview_worker = PreviewWorker(lcsc, thumb_url)
        self._preview_worker.finished.connect(self._on_preview_partial)
        self._preview_worker.start()

        self._model_worker = Model3DWorker(lcsc)
        self._model_worker.finished.connect(self._on_model_3d_finished)
        self._model_worker.start()

    def _on_preview_partial(self, lcsc: str, sym_svg, fp_svg,
                            thumb_bytes, part_count: int,
                            part_titles: list, api_result,
                            error: str):
        if lcsc != self._last_previewed_lcsc:
            return

        raw = self._search_raw_cache.get(lcsc, {})
        no_cad = not (raw.get("has_symbol") or raw.get("has_footprint"))

        if error:
            if no_cad:
                self.preview_status.setText(
                    f"{lcsc} · 立创未提供 CAD 数据"
                )
            else:
                self.preview_status.setText(f"[失败] {error[:100]}")

            if no_cad:
                from easyeda_renderer import get_no_cad_svg
                placeholder = get_no_cad_svg().encode("utf-8")
                self.symbol_svg.load(placeholder)
                self.footprint_svg.load(placeholder)
            else:
                self.symbol_svg.load(b"")
                self.footprint_svg.load(b"")
            return

        self._current_part_count = part_count
        self._current_part_titles = list(part_titles or [])
        self._current_part_index = 0
        self._current_fp_svg = fp_svg
        self._current_thumb_bytes = thumb_bytes
        self._current_api_result = api_result

        if sym_svg:
            self.symbol_svg.load(sym_svg.encode("utf-8"))
        else:
            self.symbol_svg.load(b"")

        if fp_svg:
            self.footprint_svg.load(fp_svg.encode("utf-8"))
        else:
            self.footprint_svg.load(b"")

        self._build_part_buttons(part_count, part_titles)

        if part_count > 1:
            self.preview_status.setText(
                f"{lcsc} · 多部件 ({part_count} parts) · 当前 P1"
            )
        else:
            self.preview_status.setText(f"已加载: {lcsc}")

    def _on_model_3d_finished(self, lcsc: str, model_3d, error: str):
        """3D 模型异步加载完成"""
        if lcsc != self._last_previewed_lcsc:
            print(f"[main_window] 丢弃过期的 3D 结果: {lcsc}")
            return

        if error:
            print(f"[model_3d] {lcsc} 加载失败: {error[:200]}")
            self.model_3d_view.clear()
            self.model_3d_view.set_hint("（加载失败）")
            return

        if not model_3d:
            self.model_3d_view.clear()
            self.model_3d_view.set_hint("（该元器件无 3D 模型）")
            return

        self._current_model_3d = model_3d
        colors = model_3d.get("colors")
        try:
            self.model_3d_view.set_model(
                model_3d["verts"], model_3d["faces"],
                face_colors=colors,
            )
        except TypeError:
            self.model_3d_view.set_model(
                model_3d["verts"], model_3d["faces"]
            )

    # ---------- 部件切换 ----------

    def _clear_part_buttons(self):
        if not hasattr(self, "part_bar_layout"):
            return
        while self.part_bar_layout.count() > 1:
            item = self.part_bar_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.part_scroll.setVisible(False)

    def _build_part_buttons(self, part_count: int, part_titles: list):
        self._clear_part_buttons()

        if part_count <= 1:
            return

        self.part_scroll.setVisible(True)
        self.part_group = QButtonGroup(self)
        self.part_group.setExclusive(True)

        btn_style = """
            QPushButton {
                padding: 3px 10px;
                font-size: 11px;
                min-width: 32px;
                min-height: 20px;
                max-height: 22px;
            }
        """

        for i in range(part_count):
            full_title = (
                part_titles[i] if i < len(part_titles)
                else f"Part {i + 1}"
            )
            short = f"P{i + 1}"
            btn = QPushButton(short)
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setStyleSheet(btn_style)
            btn.setToolTip(full_title)
            self.part_group.addButton(btn, i)
            self.part_bar_layout.insertWidget(i, btn)

        self.part_group.idClicked.connect(self._on_part_clicked)

    def _on_part_clicked(self, part_index: int):
        if not self._last_previewed_lcsc:
            return
        if part_index == self._current_part_index:
            return
        if not self._current_api_result:
            return

        self._current_part_index = part_index
        self.preview_status.setText(
            f"{self._last_previewed_lcsc} · "
            f"正在加载 P{part_index + 1}..."
        )

        self._part_worker = SymbolPartWorker(
            self._last_previewed_lcsc,
            part_index,
            self._current_api_result,
        )
        self._part_worker.finished.connect(self._on_part_finished)
        self._part_worker.start()

    def _on_part_finished(self, lcsc: str, part_index: int,
                          svg, error: str):
        if lcsc != self._last_previewed_lcsc:
            return
        if part_index != self._current_part_index:
            return

        if error:
            self.preview_status.setText(
                f"[P{part_index + 1} 失败] {error[:80]}"
            )
            return
        if not svg:
            self.preview_status.setText(f"[P{part_index + 1}] 渲染为空")
            return

        self.symbol_svg.load(svg.encode("utf-8"))

        full_title = ""
        if part_index < len(self._current_part_titles):
            full_title = self._current_part_titles[part_index]
        self.preview_status.setText(
            f"{lcsc} · P{part_index + 1}"
            + (f" ({full_title})" if full_title else "")
        )

    # ---------- 下载 ----------

    def _on_download_clicked(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return

        lcsc_list = []
        no_cad_list = []
        step_only = self.opt_step_only.isChecked()

        for idx in rows:
            item = self.table.item(idx.row(), 0)
            if item:
                lcsc = item.text()
                if step_only:
                    lcsc_list.append(lcsc)
                    continue
                raw = self._search_raw_cache.get(lcsc, {})
                if raw and not (raw.get("has_symbol") or raw.get("has_footprint")):
                    no_cad_list.append(lcsc)
                else:
                    lcsc_list.append(lcsc)

        if not lcsc_list:
            QMessageBox.warning(
                self, "提示",
                f"选中的 {len(no_cad_list)} 个元器件都无 CAD 数据，无法下载。"
            )
            return

        if no_cad_list and not step_only:
            reply = QMessageBox.question(
                self, "确认",
                f"选中的元器件中有 {len(no_cad_list)} 个无 CAD 数据，"
                f"将被跳过：\n{', '.join(no_cad_list[:5])}"
                + ("..." if len(no_cad_list) > 5 else "")
                + f"\n\n继续下载剩余的 {len(lcsc_list)} 个？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        if step_only:
            make_schlib = False
            make_pcblib = False
            make_step = False
            shared = False
            append = False
            lib_name = None
            mode_desc = "仅 3D 模型"
        else:
            make_schlib = self.opt_schlib.isChecked()
            make_pcblib = self.opt_pcblib.isChecked()
            make_step = self.opt_step.isChecked()

            if not make_schlib and not make_pcblib:
                QMessageBox.warning(self, "提示", "至少勾选一种输出格式")
                return

            shared = self.rb_shared.isChecked()
            append = self.opt_append.isChecked() and shared
            lib_name = None

            if shared:
                user_lib_name = self.lib_name_edit.text().strip()
                if append:
                    if not user_lib_name:
                        QMessageBox.warning(
                            self, "提示",
                            "追加到已有库时必须填写库名。"
                        )
                        return
                    lib_name = user_lib_name
                else:
                    if user_lib_name:
                        lib_name = user_lib_name
                    else:
                        lib_name = "__AUTO_FROM_FIRST__"

            if shared:
                if append:
                    mode_desc = f"共享库-追加({lib_name})"
                elif lib_name == "__AUTO_FROM_FIRST__":
                    mode_desc = "共享库(自动命名)"
                else:
                    mode_desc = f"共享库({lib_name})"
            else:
                mode_desc = "独立库"

        out_dir = self.output_dir.text().strip() or "output"

        self._log(
            f"开始下载 {len(lcsc_list)} 个元器件 -> {out_dir} "
            f"[{mode_desc}] SchLib={make_schlib}, PcbLib={make_pcblib}, "
            f"3D={make_step}, 仅3D={step_only}"
        )

        self.download_button.setEnabled(False)
        self.search_button.setEnabled(False)
        self.progress.setRange(0, len(lcsc_list))
        self.progress.setValue(0)

        self._download_worker = DownloadWorker(
            lcsc_list,
            out_dir,
            make_schlib=make_schlib,
            make_pcblib=make_pcblib,
            make_step=make_step,
            lib_name=lib_name if shared else None,
            append=append,
            step_only=step_only,
        )
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_worker.log_line.connect(self._on_download_log)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.error.connect(self._on_download_error)
        self._download_worker.start()

    def _on_download_progress(self, current: int, total: int, message: str):
        self.progress.setValue(current)
        self._set_status(message)
        self._log(message)

    def _on_download_log(self, message: str):
        self._log(message)

    def _on_download_finished(self, results: list):
        self.search_button.setEnabled(True)
        self.download_button.setEnabled(True)

        ok = sum(1 for r in results if r.success)
        fail = len(results) - ok

        self._set_status(f"下载完成: {ok} 成功, {fail} 失败")
        self._log(f"===== 下载完成: {ok} 成功, {fail} 失败 =====")

        if fail:
            QMessageBox.warning(
                self, "部分失败",
                f"{ok} 成功, {fail} 失败\n\n详情见日志。"
            )
        else:
            QMessageBox.information(
                self, "完成", f"全部 {ok} 个元器件下载成功。"
            )

    def _on_download_error(self, message: str):
        self.search_button.setEnabled(True)
        self.download_button.setEnabled(True)
        self._set_status("下载失败")
        self._log(f"[错误] {message}")
        QMessageBox.critical(self, "下载失败", message[:500])

    def _on_browse_clicked(self):
        d = QFileDialog.getExistingDirectory(
            self, "选择输出目录",
            self.output_dir.text() or ".",
        )
        if d:
            self.output_dir.setText(d)
            self._log(f"输出目录: {d}")

    # ============================================================
    # 辅助
    # ============================================================

    def _log(self, message: str):
        self.log.append(message)
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _set_status(self, text: str):
        self.status_label.setText(text)