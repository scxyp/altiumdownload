"""
后台线程：搜索、下载、预览（支持取消 + 缓存）。
"""

import threading
from PyQt6.QtCore import QThread, pyqtSignal

from lceda_client import LCEDAClient
from downloader import download_many


# ============================================================
# 3D 模型缓存（模块级，跨 worker 共享）
# ============================================================

_model_3d_cache = {}          # {lcsc: {"verts", "faces", "colors"}}
_model_3d_cache_lock = threading.Lock()


# ============================================================
# 搜索
# ============================================================

class SearchAllWorker(QThread):
    """流式搜索所有页（支持取消）"""

    page_loaded = pyqtSignal(int, list)
    all_finished = pyqtSignal(int, bool)
    error = pyqtSignal(str)

    MAX_PAGES = 10
    PAGE_SIZE = 15

    def __init__(self, keyword: str):
        super().__init__()
        self.keyword = keyword
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @staticmethod
    def _normalize(p: dict) -> dict:
        attrs = (p.get("device_info") or {}).get("attributes") or {}
        images = p.get("image") or []
        thumb_url = None
        if images and isinstance(images, list):
            img = images[0]
            if isinstance(img, dict):
                thumb_url = (
                    img.get("224x224")
                    or img.get("96x96")
                    or img.get("900x900")
                )
        return {
            "lcsc": p.get("number", ""),
            "mpn": p.get("mpn", ""),
            "package": p.get("package", ""),
            "description": (
                attrs.get("LCSC Part Name")
                or attrs.get("The Chip Type")
                or p.get("mpn", "")
            ),
            "manufacturer": p.get("manufacturer", ""),
            "stock": p.get("stock", 0),
            "thumb_url": thumb_url,
            "has_symbol": bool(attrs.get("Symbol")),
            "has_footprint": bool(attrs.get("Footprint")),
            "has_3d": bool(attrs.get("3D Model")),
            "raw": p,
        }

    def run(self):
        try:
            client = LCEDAClient()
            total = 0

            for page in range(1, self.MAX_PAGES + 1):
                if self._cancelled:
                    self.all_finished.emit(total, False)
                    return

                try:
                    data = client.search_components(
                        self.keyword, page=page, page_size=self.PAGE_SIZE
                    )
                except Exception as e:
                    print(f"[search] 第 {page} 页失败: {e}")
                    if page == 1:
                        self.error.emit(f"搜索失败: {e}")
                        return
                    break

                if self._cancelled:
                    self.all_finished.emit(total, False)
                    return

                if not data:
                    break

                result = data.get("result", {})
                products = result.get("productList", [])
                if not products or not isinstance(products, list):
                    break

                normalized = [self._normalize(p) for p in products]
                self.page_loaded.emit(page, normalized)
                total += len(normalized)

                if len(products) < self.PAGE_SIZE:
                    break

            self.all_finished.emit(total, True)

        except Exception as e:
            import traceback
            self.error.emit(
                f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            )


# ============================================================
# 下载
# ============================================================

class DownloadWorker(QThread):
    """下载一批元器件"""

    progress = pyqtSignal(int, int, str)
    log_line = pyqtSignal(str)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(
        self,
        lcsc_list: list,
        output_dir: str,
        make_schlib: bool = True,
        make_pcblib: bool = True,
        make_step: bool = False,
        lib_name: str = None,
        append: bool = False,
        step_only: bool = False,
    ):
        super().__init__()
        self.lcsc_list = lcsc_list
        self.output_dir = output_dir
        self.make_schlib = make_schlib
        self.make_pcblib = make_pcblib
        self.make_step = make_step
        self.lib_name = lib_name
        self.append = append
        self.step_only = step_only

    def run(self):
        try:
            from pathlib import Path
            import builtins

            worker = self
            original_print = builtins.print

            def custom_print(*args, **kwargs):
                msg = " ".join(str(a) for a in args)
                if msg.strip():
                    worker.log_line.emit(msg)

            def on_progress(cur, total, msg):
                worker.progress.emit(cur, total, msg)

            builtins.print = custom_print
            try:
                results = download_many(
                    self.lcsc_list,
                    Path(self.output_dir),
                    make_schlib=self.make_schlib,
                    make_pcblib=self.make_pcblib,
                    make_step=self.make_step,
                    lib_name=self.lib_name,
                    append=self.append,
                    step_only=self.step_only,
                    verbose=True,
                    progress_callback=on_progress,
                )
            finally:
                builtins.print = original_print

            self.finished.emit(results)

        except Exception as e:
            import traceback
            self.error.emit(
                f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            )


# ============================================================
# 预览：符号 + 封装
# ============================================================

class PreviewWorker(QThread):
    """预览第一部分：符号 + 封装 + 缩略图（快）"""

    finished = pyqtSignal(str, object, object, object, int, list, object, str)

    def __init__(self, lcsc: str, thumb_url: str = None):
        super().__init__()
        self.lcsc = lcsc
        self.thumb_url = thumb_url
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            from easyeda_renderer import (
                fetch_cad_data,
                get_symbol_parts_from_data,
                render_symbol_svg_from_data,
                render_footprint_svg_from_data,
            )

            api_result, source, fetch_err = fetch_cad_data(self.lcsc)
            if self._cancelled:
                return
            if not api_result:
                msg = fetch_err or "未知错误"
                print(f"[preview] {self.lcsc} 获取数据失败: {msg}")
                self.finished.emit(
                    self.lcsc, None, None, None, 0, [], None, msg,
                )
                return

            print(f"[preview] {self.lcsc} 数据源: {source}")

            part_count, part_titles = get_symbol_parts_from_data(api_result)
            if self._cancelled:
                return

            part_index = 0 if part_count > 1 else None
            sym_svg = render_symbol_svg_from_data(
                api_result, part_index=part_index
            )
            if self._cancelled:
                return

            fp_svg = render_footprint_svg_from_data(api_result)
            if self._cancelled:
                return

            thumb_bytes = None
            if self.thumb_url:
                try:
                    import requests
                    img_headers = {
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36"
                        ),
                        "Referer": "https://item.szlcsc.com/",
                    }
                    r = requests.get(
                        self.thumb_url, headers=img_headers, timeout=20
                    )
                    if r.status_code == 200:
                        thumb_bytes = r.content
                except Exception:
                    pass

            if self._cancelled:
                return

            self.finished.emit(
                self.lcsc, sym_svg, fp_svg, thumb_bytes,
                part_count, list(part_titles), api_result, "",
            )
        except Exception as e:
            import traceback
            self.finished.emit(
                self.lcsc, None, None, None, 0, [], None,
                f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            )


# ============================================================
# 预览：3D 模型（带缓存 + 取消）
# ============================================================

class Model3DWorker(QThread):
    """
    预览第二部分：3D 模型。

    支持：
      - 模块级缓存（避免重复下载）
      - 取消（用户切换元器件时停掉旧的）
    """

    finished = pyqtSignal(str, object, str)

    def __init__(self, lcsc: str, api_result: dict = None):
        super().__init__()
        self.lcsc = lcsc
        self.api_result = api_result
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            import time as _time

            # 1. 检查缓存
            with _model_3d_cache_lock:
                if self.lcsc in _model_3d_cache:
                    cached = _model_3d_cache[self.lcsc]
                    print(f"[model_3d] {self.lcsc} 使用缓存")
                    self.finished.emit(self.lcsc, cached, "")
                    return

            if self._cancelled:
                return

            from easyeda2kicad.easyeda.easyeda_api import EasyedaApi
            from easyeda2kicad.easyeda.easyeda_importer import (
                Easyeda3dModelImporter,
            )
            from easyeda_3d_renderer import parse_obj_with_materials

            t0 = _time.time()

            cad_data = self.api_result
            api = EasyedaApi()
            if not cad_data:
                cad_data = api.get_cad_data_of_component(lcsc_id=self.lcsc)

            if self._cancelled:
                return
            if not cad_data:
                self.finished.emit(self.lcsc, None, "无 CAD 数据")
                return

            if self._cancelled:
                return

            importer = Easyeda3dModelImporter(
                easyeda_cp_cad_data=cad_data,
                download_raw_3d_model=True,
                api=api,
            )

            if self._cancelled:
                return

            model = importer.output
            if not model:
                self.finished.emit(self.lcsc, None, "")
                return

            raw_obj = getattr(model, "raw_obj", None)
            if not raw_obj:
                self.finished.emit(self.lcsc, None, "")
                return

            if isinstance(raw_obj, bytes):
                obj_text = raw_obj.decode("utf-8", errors="replace")
            else:
                obj_text = raw_obj

            if self._cancelled:
                return

            verts, faces, colors = parse_obj_with_materials(obj_text)
            if verts is None or faces is None:
                self.finished.emit(self.lcsc, None, "OBJ 解析失败")
                return

            if self._cancelled:
                return

            payload = {
                "verts": verts,
                "faces": faces,
                "colors": colors,
            }

            # 存入缓存
            with _model_3d_cache_lock:
                _model_3d_cache[self.lcsc] = payload
                # 限制缓存大小（最多 10 个）
                if len(_model_3d_cache) > 10:
                    first_key = next(iter(_model_3d_cache))
                    del _model_3d_cache[first_key]

            elapsed = _time.time() - t0
            print(
                f"[model_3d] {self.lcsc} 3D 模型加载完成: "
                f"verts={len(verts)}, faces={len(faces)}, "
                f"耗时={elapsed:.2f}s"
            )

            self.finished.emit(self.lcsc, payload, "")
        except Exception as e:
            import traceback
            self.finished.emit(
                self.lcsc, None,
                f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            )


# ============================================================
# 符号部件切换
# ============================================================

class SymbolPartWorker(QThread):
    """切换部件时只重新渲染符号"""

    finished = pyqtSignal(str, int, object, str)

    def __init__(self, lcsc: str, part_index: int, api_result: dict):
        super().__init__()
        self.lcsc = lcsc
        self.part_index = part_index
        self.api_result = api_result

    def run(self):
        try:
            from easyeda_renderer import render_symbol_svg_from_data
            svg = render_symbol_svg_from_data(
                self.api_result, part_index=self.part_index
            )
            self.finished.emit(self.lcsc, self.part_index, svg, "")
        except Exception as e:
            import traceback
            self.finished.emit(
                self.lcsc, self.part_index, None,
                f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            )


# ============================================================
# 缓存管理接口（供 main_window 调用）
# ============================================================

def clear_model_3d_cache():
    """清空 3D 模型缓存"""
    with _model_3d_cache_lock:
        _model_3d_cache.clear()