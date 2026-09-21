# -*- mode: python ; coding: utf-8 -*-
"""
GUI 版打包配置（onedir 模式，启动更快）。

打包命令：
    python -m PyInstaller build.spec --clean --noconfirm

输出: dist/LCEDA_Altium_Downloader/LCEDA_Altium_Downloader.exe
"""

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules


PROJECT_ROOT = Path(SPECPATH).resolve()

# --- npnp.exe 打包 ---
npnp_bin = PROJECT_ROOT / "bin" / "npnp.exe"
if not npnp_bin.exists():
    npnp_bin = PROJECT_ROOT / "bin" / "npnp"

datas = []
if npnp_bin.exists():
    datas.append((str(npnp_bin), "bin"))
    print(f"[build.spec] 打包 npnp: {npnp_bin}")
else:
    print(f"[build.spec] ⚠ 未找到 npnp 可执行文件，请放到 bin/ 目录")

# --- easyeda2kicad 数据 ---
try:
    easyeda_datas = collect_data_files("easyeda2kicad")
    datas.extend(easyeda_datas)
except Exception:
    pass

# --- 项目模块 ---
project_modules = [
    "lceda_client",
    "downloader",
    "easyeda_renderer",
    "easyeda_3d_renderer",
    "gui",
    "gui.main_window",
    "gui.worker",
    "gui.svg_view",
    "gui.model_3d_view_gl",
    "gui.model_3d_view",
]

# --- 第三方库 ---
easyeda_hidden = collect_submodules("easyeda2kicad")
pyqtgraph_hidden = collect_submodules("pyqtgraph")

hiddenimports = (
    easyeda_hidden
    + pyqtgraph_hidden
    + project_modules
    + [
        "easyeda2kicad",
        "easyeda2kicad.easyeda.easyeda_api",
        "easyeda2kicad.easyeda.easyeda_importer",
        "easyeda2kicad.easyeda.easyeda_svg_renderer",
        "easyeda2kicad.kicad.export_kicad_3d_model",
        "requests",
        "lz4",
        "lz4.block",
        "lz4.frame",
        "PyQt6",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.QtSvg",
        "PyQt6.QtSvgWidgets",
        "PyQt6.QtOpenGL",
        "PyQt6.QtOpenGLWidgets",
        "pyqtgraph",
        "pyqtgraph.opengl",
        "pyqtgraph.opengl.GLGraphicsItem",
        "pyqtgraph.opengl.shaders",
        "OpenGL",
        "OpenGL.GL",
        "OpenGL.GLU",
        "OpenGL.platform",
        "OpenGL.arrays",
        "numpy",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
    ]
)

a = Analysis(
    ["gui_main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "PyQt5",
        "PySide2",
        "PySide6",
        "IPython",
        "jupyter",
        "pytest",
        "numpy.testing",
        "pandas",
        "pandas.tests",
        "scipy",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# ★ 关键：exclude_binaries=True，把所有二进制文件交给 COLLECT
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,       # ← onedir 模式核心
    name="LCEDA_Altium_Downloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

# ★ COLLECT 收集所有依赖到目录
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="LCEDA_Altium_Downloader",
)