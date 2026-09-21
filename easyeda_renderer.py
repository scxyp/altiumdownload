"""
基于 easyeda2kicad 的 SVG 渲染器 + 3D 模型本地渲染。

数据来源优先 lceda_client（带重试），失败时回退到 easyeda2kicad 的 API。
本模块只负责渲染，不发起网络请求（除 fetch_cad_data 外）。
"""

import re
from typing import Optional


# ============================================================
# 数据获取（双源 fallback）
# ============================================================

def fetch_cad_data(lcsc: str) -> tuple:
    """
    获取元器件 CAD 数据。

    依次尝试：
      1. lceda_client（我们自己的，带重试 + 多域名）
      2. easyeda2kicad.EasyedaApi（备用）

    Returns:
        (api_result_dict, source_name, error_message)
    """
    if not lcsc.upper().startswith("C"):
        lcsc = "C" + lcsc

    errors = []

    try:
        from lceda_client import LCEDAClient
        client = LCEDAClient()
        raw = client.get_component_data(lcsc)
        if raw:
            result = raw.get("result", {})
            has_data = (
                result.get("dataStr") or
                result.get("subparts") or
                result.get("packageDetail")
            )
            if has_data:
                return (result, "lceda_client", "")
            else:
                errors.append("lceda_client: result 无有效数据")
        else:
            errors.append("lceda_client: API 返回空")
    except Exception as e:
        errors.append(f"lceda_client: {type(e).__name__}: {e}")

    try:
        from easyeda2kicad.easyeda.easyeda_api import EasyedaApi
        api = EasyedaApi()
        data = api.get_cad_data_of_component(lcsc_id=lcsc)
        if data:
            return (data, "easyeda2kicad", "")
        errors.append("easyeda2kicad: API 返回空")
    except Exception as e:
        errors.append(f"easyeda2kicad: {type(e).__name__}: {e}")

    return (None, "", " | ".join(errors))


# ============================================================
# SVG 后处理
# ============================================================

def _force_white_background(svg: str, bg_color: str = "white") -> str:
    if not svg:
        return svg
    match = re.search(r'(<svg[^>]*?>)', svg)
    if not match:
        return svg
    insert_pos = match.end()
    bg_rect = (
        f'<rect x="-100000" y="-100000" width="200000" height="200000" '
        f'fill="{bg_color}"/>'
    )
    return svg[:insert_pos] + bg_rect + svg[insert_pos:]


def _simplify_dense_pads(svg: str) -> str:
    if not svg:
        return svg
    text_count = len(re.findall(r'<text\b', svg))
    if text_count <= 100:
        return svg
    svg = re.sub(
        r'(<text[^>]*?font-size=")2("[^>]*?>)',
        r'\g<1>1.2\g<2>',
        svg,
    )
    svg = re.sub(
        r'(<text\b(?![^>]*?opacity))',
        r'\1 opacity="0.5"',
        svg,
    )
    print(f"[renderer] 大封装：简化 {text_count} 个文字标签")
    return svg


def _postprocess(svg: str, bg_color: str = "white",
                 simplify: bool = False) -> str:
    if not svg:
        return svg
    svg = _force_white_background(svg, bg_color=bg_color)
    if simplify:
        svg = _simplify_dense_pads(svg)
    return svg


def _error_svg(message: str) -> str:
    safe = (
        message.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    lines = []
    if len(safe) > 60:
        lines.append(safe[:60])
        lines.append(safe[60:120])
    else:
        lines.append(safe)
    text_elems = []
    for i, line in enumerate(lines):
        text_elems.append(
            f'<text x="200" y="{70 + i * 18}" text-anchor="middle" '
            f'font-family="Arial, sans-serif" font-size="11" fill="#666">'
            f'{line}</text>'
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="140" '
        'viewBox="0 0 400 140">'
        '<rect x="0" y="0" width="400" height="140" fill="white"/>'
        '<text x="200" y="45" text-anchor="middle" '
        'font-family="Arial, sans-serif" font-size="14" fill="#c00">'
        '渲染失败</text>'
        + "".join(text_elems)
        + '</svg>'
    )


def _no_cad_data_svg(message: str = "该元器件暂无 CAD 数据") -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="140" '
        'viewBox="0 0 400 140">'
        '<rect x="0" y="0" width="400" height="140" fill="#fafafa"/>'
        '<rect x="0" y="0" width="400" height="140" fill="none" '
        'stroke="#e0e0e0" stroke-dasharray="4,4"/>'
        '<text x="200" y="60" text-anchor="middle" '
        'font-family="Arial, sans-serif" font-size="14" fill="#999">'
        '○</text>'
        '<text x="200" y="85" text-anchor="middle" '
        'font-family="Arial, sans-serif" font-size="13" fill="#666">'
        f'{message}</text>'
        '<text x="200" y="108" text-anchor="middle" '
        'font-family="Arial, sans-serif" font-size="11" fill="#aaa">'
        '立创EDA 未提供此元器件的符号/封装</text>'
        '</svg>'
    )


def get_no_cad_svg() -> str:
    return _no_cad_data_svg()


# ============================================================
# 部件信息
# ============================================================

def get_symbol_parts_from_data(api_result: dict) -> tuple:
    if not api_result:
        return (0, [])

    subparts = api_result.get("subparts")
    main_shapes = api_result.get("dataStr", {}).get("shape", [])

    if not subparts or not isinstance(subparts, list):
        return (1, [])
    if len(main_shapes) > 0:
        return (1, [])

    titles = []
    for i, sub in enumerate(subparts):
        t = None
        if isinstance(sub, dict):
            t = sub.get("title")
        if not t:
            t = f"Part {i + 1}"
        titles.append(t)

    return (len(subparts), titles)


# ============================================================
# 符号 / 封装渲染
# ============================================================

def _render_single_part_svg(part_data: dict, bg_color: str,
                             part_label: str = "") -> str:
    from easyeda2kicad.easyeda.easyeda_svg_renderer import (
        render_symbol_svg as _render,
    )
    try:
        ds = part_data.get("dataStr", {})
        shape_count = len(ds.get("shape", [])) if isinstance(ds, dict) else 0
        if shape_count == 0:
            return _error_svg(f"{part_label} 无图形数据")

        svg = _render(part_data, bg_color=bg_color)
        if not svg:
            return _error_svg(f"{part_label} 渲染返回空")
        return _postprocess(svg, bg_color=bg_color)
    except Exception as e:
        import traceback
        print(f"[renderer] {part_label} 渲染异常: {type(e).__name__}: {e}")
        traceback.print_exc()
        return _error_svg(f"{part_label}: {type(e).__name__}")


def render_symbol_svg_from_data(api_result: dict,
                                 part_index: Optional[int] = None,
                                 bg_color: str = "white") -> str:
    from easyeda2kicad.easyeda.easyeda_svg_renderer import (
        render_symbol_svg as _render,
    )

    if not api_result:
        return _error_svg("无数据")

    subparts = api_result.get("subparts")
    main_shapes = api_result.get("dataStr", {}).get("shape", [])

    if subparts and isinstance(subparts, list) and len(main_shapes) == 0:
        if part_index is None:
            part_index = 0
        if part_index < 0 or part_index >= len(subparts):
            return _error_svg(
                f"Part {part_index + 1} 超出范围 (共 {len(subparts)})"
            )
        sub = subparts[part_index]
        sub_api = {
            "dataStr": sub.get("dataStr", {}),
            "title": sub.get("title", f"Part {part_index + 1}"),
        }
        label = f"Part {part_index + 1}"
        return _render_single_part_svg(sub_api, bg_color, label)

    try:
        svg = _render(api_result, bg_color=bg_color)
        return _postprocess(svg, bg_color=bg_color)
    except Exception as e:
        import traceback
        print(f"[renderer] 符号渲染失败: {type(e).__name__}: {e}")
        traceback.print_exc()
        return _error_svg(f"{type(e).__name__}: {e}")


def render_footprint_svg_from_data(api_result: dict,
                                    bg_color: str = "white",
                                    simplify: bool = True) -> str:
    from easyeda2kicad.easyeda.easyeda_svg_renderer import (
        render_footprint_svg as _render,
    )

    if not api_result:
        return _error_svg("无数据")

    try:
        svg = _render(api_result, bg_color=bg_color)
        return _postprocess(svg, bg_color=bg_color, simplify=simplify)
    except Exception as e:
        import traceback
        print(f"[renderer] 封装渲染失败: {type(e).__name__}: {e}")
        traceback.print_exc()
        return _error_svg(f"{type(e).__name__}: {e}")


# ============================================================
# 3D 模型渲染（新增）
# ============================================================

def render_3d_from_lcsc(lcsc: str, output_size=(500, 500)) -> Optional[bytes]:
    """
    下载 3D 模型（OBJ 数据）并渲染为 PNG 字节。

    使用 easyeda2kicad 下载 OBJ 数据，然后用 easyeda_3d_renderer 本地渲染。
    不需要 OpenGL，纯 PIL + numpy。

    Args:
        lcsc: LCSC 编号
        output_size: PNG 尺寸

    Returns:
        PNG 字节流，失败返回 None
    """
    if not lcsc.upper().startswith("C"):
        lcsc = "C" + lcsc

    try:
        from easyeda2kicad.easyeda.easyeda_api import EasyedaApi
        from easyeda2kicad.easyeda.easyeda_importer import (
            Easyeda3dModelImporter,
        )
        from easyeda_3d_renderer import render_obj_text_to_png_bytes

        api = EasyedaApi()
        cad_data = api.get_cad_data_of_component(lcsc_id=lcsc)
        if not cad_data:
            print(f"[renderer] {lcsc} 无法获取 CAD 数据")
            return None

        importer = Easyeda3dModelImporter(
            easyeda_cp_cad_data=cad_data,
            download_raw_3d_model=True,
            api=api,
        )
        model = importer.output
        if not model:
            print(f"[renderer] {lcsc} 无 3D 模型")
            return None

        raw_obj = getattr(model, "raw_obj", None)
        if not raw_obj:
            print(f"[renderer] {lcsc} 3D 模型 raw_obj 为空")
            return None

        if isinstance(raw_obj, bytes):
            obj_text = raw_obj.decode("utf-8", errors="replace")
        else:
            obj_text = raw_obj

        print(f"[renderer] {lcsc} OBJ 长度: {len(obj_text)}")

        png_bytes = render_obj_text_to_png_bytes(
            obj_text, output_size=output_size
        )
        return png_bytes

    except Exception as e:
        import traceback
        print(f"[renderer] {lcsc} 3D 渲染失败: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None


# ============================================================
# 兼容旧接口
# ============================================================

def render_symbol_svg(lcsc: str, part_index: Optional[int] = None,
                      bg_color: str = "white") -> Optional[str]:
    api_result, _, err = fetch_cad_data(lcsc)
    if not api_result:
        return _error_svg(err or f"无法获取 {lcsc} 数据")
    return render_symbol_svg_from_data(api_result, part_index, bg_color)


def render_footprint_svg(lcsc: str, bg_color: str = "white",
                         simplify: bool = True) -> Optional[str]:
    api_result, _, err = fetch_cad_data(lcsc)
    if not api_result:
        return _error_svg(err or f"无法获取 {lcsc} 数据")
    return render_footprint_svg_from_data(api_result, bg_color, simplify)


def get_symbol_parts(lcsc: str) -> tuple:
    api_result, _, _ = fetch_cad_data(lcsc)
    if not api_result:
        return (0, [])
    return get_symbol_parts_from_data(api_result)