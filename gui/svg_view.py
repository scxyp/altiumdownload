"""
可缩放/平移的 SVG 视图组件。

基于 QGraphicsView + QGraphicsSvgItem 实现：
  - 鼠标滚轮：缩放
  - 按住左键拖拽：平移
  - 双击：适应窗口
  - 调用 load() 加载新的 SVG 内容
"""

from PyQt6.QtCore import Qt, QByteArray
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtSvgWidgets import QGraphicsSvgItem
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView


class SvgView(QGraphicsView):
    """可缩放/平移的 SVG 视图"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        # 渲染质量
        self.setRenderHints(
            self.renderHints()
            | self.renderHints().SmoothPixmapTransform
        )
        # 背景
        self.setBackgroundBrush(Qt.GlobalColor.white)
        # 抗锯齿
        self.setRenderHint(self.renderHints().Antialiasing)
        # 拖拽模式
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        # 不显示滚动条
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._svg_item = None
        self._renderer = None

    def load(self, svg_data):
        """
        加载 SVG。

        Args:
            svg_data: bytes 或 str，空内容则清空
        """
        # 清空
        self._scene.clear()
        self._svg_item = None
        self._renderer = None

        if not svg_data:
            return

        if isinstance(svg_data, str):
            svg_data = svg_data.encode("utf-8")
        elif not isinstance(svg_data, (bytes, bytearray)):
            return

        if len(svg_data) == 0:
            return

        try:
            byte_array = QByteArray(svg_data)
            self._renderer = QSvgRenderer(byte_array)
            if not self._renderer.isValid():
                return

            self._svg_item = QGraphicsSvgItem()
            self._svg_item.setSharedRenderer(self._renderer)
            self._scene.addItem(self._svg_item)

            # 场景大小 = SVG 大小
            rect = self._svg_item.boundingRect()
            self._scene.setSceneRect(rect)

            # 自动适应窗口
            self.fit_to_window()
        except Exception as e:
            print(f"[SvgView] 加载失败: {type(e).__name__}: {e}")

    def fit_to_window(self):
        """让 SVG 适应窗口"""
        if self._svg_item is None:
            return
        self.fitInView(
            self._svg_item,
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        # 缩放到 95%，留点边距
        self.scale(0.95, 0.95)

    def wheelEvent(self, event):
        """滚轮缩放"""
        if self._svg_item is None:
            return
        factor = 1.15
        if event.angleDelta().y() < 0:
            factor = 1.0 / factor
        self.scale(factor, factor)

    def mouseDoubleClickEvent(self, event):
        """双击恢复适应窗口"""
        self.fit_to_window()

    def resizeEvent(self, event):
        """窗口变化时保持适应（仅在首次加载时自动适应）"""
        super().resizeEvent(event)