"""
交互式 3D 模型视图。

用画家算法 + 屏幕空间 winding 剔除背面。
比 3D 法线更可靠，不受 OBJ 内部法线方向影响。
支持：
  - 鼠标左键拖动：旋转
  - 滚轮：缩放
  - 双击：重置视图
"""

import numpy as np
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QImage, QPainter, QPolygonF, QColor, QPixmap
from PyQt6.QtWidgets import QWidget


# 全分辨率最大面数
FULL_MAX_FACES = 15000
# 拖动时最大面数
DRAG_MAX_FACES = 3000


class Model3DView(QWidget):
    """可交互的 3D 模型视图"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(200)
        self.setStyleSheet("background: white;")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # 模型数据
        self._verts_full = None
        self._faces_full = None

        self._verts_drag = None
        self._faces_drag = None

        # 视图参数
        self._yaw = 45.0
        self._pitch = 30.0
        self._zoom = 1.0

        # 交互
        self._last_mouse = None
        self._is_dragging = False

        # 颜色
        self._base_color = np.array([90, 90, 100], dtype=np.float32)

        # 缓存
        self._cached_pixmap = None
        self._cached_key = None

        # 提示
        self._hint = "（暂无 3D 模型）"
        self._show_hint = True

    # ============================================================
    # 公开接口
    # ============================================================

    def set_model(self, verts, faces, base_color=None):
        if verts is None or faces is None:
            self.clear()
            return

        verts = np.asarray(verts, dtype=np.float32)
        faces = np.asarray(faces, dtype=np.int32)

        if len(verts) == 0 or len(faces) == 0:
            self.clear()
            return

        # 归一化到 [-1, 1]
        vmin = verts.min(axis=0)
        vmax = verts.max(axis=0)
        center = (vmin + vmax) / 2
        verts = verts - center
        extent = np.abs(verts).max()
        if extent > 0:
            verts = verts / extent

        if base_color is not None:
            self._base_color = np.array(base_color, dtype=np.float32)

        # 全分辨率降采样
        if len(faces) > FULL_MAX_FACES:
            step = len(faces) // FULL_MAX_FACES + 1
            faces = faces[::step]
            print(f"[model_3d_view] 面数降采样到 {len(faces)}")

        self._verts_full = verts
        self._faces_full = faces

        # 拖动版本
        if len(faces) > DRAG_MAX_FACES:
            step = len(faces) // DRAG_MAX_FACES + 1
            self._verts_drag = verts
            self._faces_drag = faces[::step]
        else:
            self._verts_drag = verts
            self._faces_drag = faces

        # 清缓存
        self._cached_pixmap = None
        self._cached_key = None

        self._show_hint = False
        self._yaw = 45.0
        self._pitch = 30.0
        self._zoom = 1.0
        self.update()

    def clear(self):
        self._verts_full = None
        self._faces_full = None
        self._verts_drag = None
        self._faces_drag = None
        self._cached_pixmap = None
        self._cached_key = None
        self._show_hint = True
        self._hint = "（暂无 3D 模型）"
        self.update()

    def set_hint(self, text):
        self._hint = text
        self._show_hint = True
        self._cached_pixmap = None
        self._cached_key = None
        self.update()

    # ============================================================
    # 内部：旋转矩阵
    # ============================================================

    def _build_rotation_matrix(self):
        a = np.radians(self._yaw)
        ca, sa = np.cos(a), np.sin(a)
        R_y = np.array([
            [ca, 0, sa],
            [0, 1, 0],
            [-sa, 0, ca],
        ], dtype=np.float32)

        b = np.radians(self._pitch)
        cb, sb = np.cos(b), np.sin(b)
        R_x = np.array([
            [1, 0, 0],
            [0, cb, -sb],
            [0, sb, cb],
        ], dtype=np.float32)

        return R_x @ R_y

    # ============================================================
    # 内部：渲染
    # ============================================================

    def _render(self, verts, faces, W, H):
        """画家算法 + 屏幕空间 winding 剔除背面"""
        if verts is None or faces is None or len(faces) == 0:
            return None

        # 1. 旋转
        R = self._build_rotation_matrix()
        verts_r = verts @ R.T

        # 2. 投影到屏幕
        pad = 20
        scale = (min(W, H) / 2.0 - pad) * self._zoom
        sx = verts_r[:, 0] * scale + W / 2.0
        sy = -verts_r[:, 1] * scale + H / 2.0
        sz = verts_r[:, 2]

        # 3. 三角形坐标（按面索引）
        v0 = faces[:, 0]
        v1 = faces[:, 1]
        v2 = faces[:, 2]

        x0 = sx[v0]; y0 = sy[v0]; z0 = sz[v0]
        x1 = sx[v1]; y1 = sy[v1]; z1 = sz[v1]
        x2 = sx[v2]; y2 = sy[v2]; z2 = sz[v2]

        # 4. 屏幕空间 winding（Y 已翻转，正面为 signed_area < 0）
        signed_area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)

        front_mask = signed_area < 0

        # 如果正面太少（可能是 OBJ winding 相反），反转
        if front_mask.sum() < len(front_mask) * 0.1:
            front_mask = signed_area > 0

        visible_idx = np.where(front_mask)[0]
        if len(visible_idx) == 0:
            return None

        # 5. 深度排序：远（z 小）先画
        mean_z = (z0 + z1 + z2) / 3.0
        visible_depths = mean_z[visible_idx]
        sort_order = np.argsort(visible_depths)  # 升序 = 远到近
        sorted_idx = visible_idx[sort_order]

        # 6. 光照：用 3D 法线的绝对值（双面）
        va = verts_r[v0]
        vb = verts_r[v1]
        vc = verts_r[v2]
        normals = np.cross(vb - va, vc - va)
        norms = np.linalg.norm(normals, axis=1, keepdims=True)
        norms = np.where(norms > 1e-8, norms, 1.0)
        normals = normals / norms

        light = np.array([-0.3, 0.6, 0.7], dtype=np.float32)
        light = light / np.linalg.norm(light)
        intensity = np.abs(normals @ light)
        intensity = 0.35 + 0.65 * intensity
        np.clip(intensity, 0.0, 1.0, out=intensity)

        # 7. 用 QImage + QPainter 绘制
        img = QImage(W, H, QImage.Format.Format_RGB32)
        img.fill(QColor(255, 255, 255))

        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        base = self._base_color

        for fi in sorted_idx:
            f = faces[fi]
            i = intensity[fi]
            color = QColor(
                int(base[0] * i),
                int(base[1] * i),
                int(base[2] * i),
            )
            painter.setPen(color)
            painter.setBrush(color)
            poly = QPolygonF([
                QPointF(sx[f[0]], sy[f[0]]),
                QPointF(sx[f[1]], sy[f[1]]),
                QPointF(sx[f[2]], sy[f[2]]),
            ])
            painter.drawPolygon(poly)

        painter.end()
        return QPixmap.fromImage(img)

    # ============================================================
    # 交互事件
    # ============================================================

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_mouse = event.position()
            self._is_dragging = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._cached_pixmap = None
            self._cached_key = None
            self.update()

    def mouseMoveEvent(self, event):
        if not self._is_dragging or self._last_mouse is None:
            return
        delta = event.position() - self._last_mouse
        self._yaw += delta.x() * 0.5
        self._pitch += delta.y() * 0.5
        self._pitch = max(-89.0, min(89.0, self._pitch))
        self._last_mouse = event.position()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_mouse = None
            self._is_dragging = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self._cached_pixmap = None
            self._cached_key = None
            self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 1.1 if delta > 0 else 1.0 / 1.1
        self._zoom *= factor
        self._zoom = max(0.2, min(5.0, self._zoom))
        self._cached_pixmap = None
        self._cached_key = None
        self.update()

    def mouseDoubleClickEvent(self, event):
        self._yaw = 45.0
        self._pitch = 30.0
        self._zoom = 1.0
        self._cached_pixmap = None
        self._cached_key = None
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._cached_pixmap = None
        self._cached_key = None

    # ============================================================
    # 绘制
    # ============================================================

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(255, 255, 255))

        if self._show_hint or self._verts_full is None:
            painter.setPen(QColor(153, 153, 153))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                self._hint,
            )
            painter.end()
            return

        W = self.width()
        H = self.height()

        # 缓存键
        key = (
            round(self._yaw, 1),
            round(self._pitch, 1),
            round(self._zoom, 3),
            W, H,
            self._is_dragging,
        )

        if self._cached_key == key and self._cached_pixmap is not None:
            painter.drawPixmap(0, 0, self._cached_pixmap)
            painter.end()
            return

        # 选择数据源
        if self._is_dragging:
            verts = self._verts_drag
            faces = self._faces_drag
        else:
            verts = self._verts_full
            faces = self._faces_full

        pixmap = self._render(verts, faces, W, H)

        if pixmap is None:
            painter.end()
            return

        self._cached_pixmap = pixmap
        self._cached_key = key

        painter.drawPixmap(0, 0, pixmap)
        painter.end()