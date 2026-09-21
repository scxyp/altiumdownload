"""
从立创 OBJ 数据解析 3D 模型。

- parse_obj_to_arrays(): 只解析顶点和面（兼容旧接口）
- parse_obj_with_materials(): 额外返回每个面的 Kd 颜色
- render_obj_to_image(): 静态渲染为 PIL Image（备用）
"""

import io
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw


def _parse_obj_minimal(obj_text: str):
    """轻量 OBJ 解析（只关心 v 和 f）"""
    vertices = []
    faces = []

    for line in obj_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("v "):
            parts = line.split()
            if len(parts) >= 4:
                try:
                    vertices.append([
                        float(parts[1]),
                        float(parts[2]),
                        float(parts[3]),
                    ])
                except ValueError:
                    continue
        elif line.startswith("f "):
            parts = line.split()[1:]
            try:
                idx = [int(p.split("/")[0]) - 1 for p in parts]
            except (ValueError, IndexError):
                continue
            for i in range(1, len(idx) - 1):
                faces.append([idx[0], idx[i], idx[i + 1]])

    if not vertices or not faces:
        return None, None

    return (
        np.array(vertices, dtype=np.float32),
        np.array(faces, dtype=np.int32),
    )


def parse_obj_to_arrays(obj_text: str):
    """兼容旧接口：解析 OBJ 文本为 numpy 数组"""
    return _parse_obj_minimal(obj_text)


def parse_obj_with_materials(obj_text: str):
    """
    解析 OBJ，返回 (verts, faces, face_colors)。

    face_colors: (M, 3) float32，每个面的 RGB 颜色（0~1）。
    颜色来自 OBJ 里的 Kd（漫反射）字段。
    没有材质信息的 OBJ 会返回默认灰色。

    Returns:
        (verts, faces, face_colors) 或 (None, None, None)
    """
    vertices = []
    faces = []
    face_colors = []

    materials = {}                # 材质名 -> (r, g, b)
    current_mtl_in_block = None   # 正在 newmtl 块内定义的材质名
    current_mtl_for_faces = None  # 当前 f 使用的材质名
    in_mtl_block = False

    for line in obj_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("v "):
            parts = line.split()
            if len(parts) >= 4:
                try:
                    vertices.append([
                        float(parts[1]),
                        float(parts[2]),
                        float(parts[3]),
                    ])
                except ValueError:
                    continue

        elif line.startswith("newmtl "):
            current_mtl_in_block = line[7:].strip()
            # 默认色
            materials.setdefault(current_mtl_in_block, (0.5, 0.5, 0.5))
            in_mtl_block = True

        elif line.startswith("Kd ") and in_mtl_block and current_mtl_in_block:
            parts = line.split()
            if len(parts) >= 4:
                try:
                    materials[current_mtl_in_block] = (
                        float(parts[1]),
                        float(parts[2]),
                        float(parts[3]),
                    )
                except ValueError:
                    pass

        elif line.startswith("endmtl"):
            in_mtl_block = False
            current_mtl_in_block = None

        elif line.startswith("usemtl "):
            current_mtl_for_faces = line[7:].strip()

        elif line.startswith("f "):
            parts = line.split()[1:]
            try:
                idx = [int(p.split("/")[0]) - 1 for p in parts]
            except (ValueError, IndexError):
                continue
            color = materials.get(
                current_mtl_for_faces, (0.5, 0.5, 0.5)
            )
            for i in range(1, len(idx) - 1):
                faces.append([idx[0], idx[i], idx[i + 1]])
                face_colors.append(color)

    if not vertices or not faces:
        return None, None, None

    return (
        np.array(vertices, dtype=np.float32),
        np.array(faces, dtype=np.int32),
        np.array(face_colors, dtype=np.float32),
    )


# 保留旧接口
def render_obj_to_image(
    obj_text: str,
    output_size=(500, 500),
    bg_color=(245, 245, 250),
    base_color=(90, 90, 100),
    max_faces: int = 50000,
) -> Optional[Image.Image]:
    """静态渲染（保留兼容）"""
    verts, faces = _parse_obj_minimal(obj_text)
    if verts is None:
        return None
    print(f"[3d_renderer] 顶点数={len(verts)}, 面数={len(faces)}")
    # ...（此处省略旧的渲染逻辑，GUI 不再调用此函数）
    return None


def render_obj_text_to_png_bytes(
    obj_text: str,
    output_size=(500, 500),
) -> Optional[bytes]:
    return None