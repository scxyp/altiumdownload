"""
基于 OpenGL 的 3D 模型视图（pyqtgraph.opengl）。

带 hint 提示层：无数据时显示文字，有数据时显示 3D 模型。
"""

import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QStackedLayout
from PyQt6.QtCore import Qt


class Model3DViewGL(QWidget):
    """OpenGL 3D 模型视图（带 hint 提示）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(200)

        try:
            import pyqtgraph.opengl as gl
            self._gl = gl
            self._available = True
        except Exception as e:
            self._gl = None
            self._available = False
            print(f"[Model3DViewGL] pyqtgraph.opengl 不可用: {e}")

        # 用 QStackedLayout 在两个界面之间切换
        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)

        # ---- 页面 1：提示文字 ----
        self._hint_label = QLabel("（暂无 3D 模型）")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setStyleSheet(
            "background: white; color: #999; font-size: 13px;"
        )
        self._stack.addWidget(self._hint_label)

        # ---- 页面 2：OpenGL 视图 ----
        if self._available:
            self._view = gl.GLViewWidget()
            self._view.setBackgroundColor((255, 255, 255))
            self._view.setCameraPosition(distance=3, elevation=25, azimuth=45)
            self._stack.addWidget(self._view)
        else:
            self._view = None
            fallback = QLabel(
                "OpenGL 不可用\n\n"
                "请运行: pip install pyqtgraph PyOpenGL"
            )
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback.setStyleSheet("color: #999;")
            self._stack.addWidget(fallback)

        self._mesh_item = None

        # 默认显示提示
        self._stack.setCurrentIndex(0)

    # ============================================================
    # 公开接口
    # ============================================================

    def set_model(self, verts, faces, face_colors=None, base_color=None):
        """设置 3D 模型。"""
        if not self._available:
            return

        if verts is None or faces is None:
            self.clear()
            return

        verts = np.asarray(verts, dtype=np.float32).copy()
        faces = np.asarray(faces, dtype=np.int32)

        if len(verts) == 0 or len(faces) == 0:
            self.clear()
            return

        # 归一化
        vmin = verts.min(axis=0)
        vmax = verts.max(axis=0)
        center = (vmin + vmax) / 2
        verts = verts - center
        extent = np.abs(verts).max()
        if extent > 0:
            verts = verts / extent

        # 绕 X 轴旋转 180°（Y 和 Z 都取反）—— 文字正立
        verts[:, 1] = -verts[:, 1]
        verts[:, 2] = -verts[:, 2]

        # 移除旧 mesh
        if self._mesh_item is not None:
            try:
                self._view.removeItem(self._mesh_item)
            except Exception:
                pass
            self._mesh_item = None

        # 展开：每个面 3 个独立顶点
        n_faces = len(faces)
        new_verts = np.empty((n_faces * 3, 3), dtype=np.float32)

        v0 = verts[faces[:, 0]]
        v1 = verts[faces[:, 1]]
        v2 = verts[faces[:, 2]]
        # 反转 winding（v1↔v2），光照正常
        new_verts[0::3] = v0
        new_verts[1::3] = v2
        new_verts[2::3] = v1

        new_faces = np.arange(n_faces * 3, dtype=np.uint32).reshape(-1, 3)

        # 顶点颜色
        if face_colors is not None:
            face_colors = np.asarray(face_colors, dtype=np.float32)
            if len(face_colors) != n_faces:
                face_colors = np.full((n_faces, 3), 0.5, dtype=np.float32)
        else:
            if base_color is None:
                base_color = (0.35, 0.35, 0.40)
            bc = np.array(base_color, dtype=np.float32)
            if bc.max() > 1.0:
                bc = bc / 255.0
            face_colors = np.tile(bc, (n_faces, 1))

        face_colors = np.clip(face_colors * 1.3 + 0.15, 0.0, 1.0)

        new_colors = np.empty((n_faces * 3, 4), dtype=np.float32)
        new_colors[0::3, :3] = face_colors
        new_colors[1::3, :3] = face_colors
        new_colors[2::3, :3] = face_colors
        new_colors[:, 3] = 1.0

        try:
            mesh_data = self._gl.MeshData(
                vertexes=new_verts,
                faces=new_faces,
                vertexColors=new_colors,
            )
        except Exception as e:
            print(f"[Model3DViewGL] MeshData 创建失败: {e}")
            return

        try:
            self._mesh_item = self._gl.GLMeshItem(
                meshdata=mesh_data,
                smooth=True,
                shader='shaded',
                glOptions='opaque',
                drawEdges=False,
                drawFaces=True,
            )
            self._view.addItem(self._mesh_item)
        except Exception as e:
            print(f"[Model3DViewGL] GLMeshItem 创建失败: {e}")
            return

        self._view.setCameraPosition(distance=3, elevation=25, azimuth=45)

        # 切换到 GL 视图
        self._stack.setCurrentIndex(1)

    def clear(self):
        """清空模型，显示默认提示"""
        if self._mesh_item is not None and self._available:
            try:
                self._view.removeItem(self._mesh_item)
            except Exception:
                pass
            self._mesh_item = None
        self._stack.setCurrentIndex(0)
        self._hint_label.setText("（暂无 3D 模型）")

    def set_hint(self, text):
        """显示提示文字（切换回提示页）"""
        self._hint_label.setText(text)
        self._stack.setCurrentIndex(0)

    def reset_view(self):
        if not self._available:
            return
        self._view.setCameraPosition(distance=3, elevation=25, azimuth=45)