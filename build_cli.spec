# -*- mode: python ; coding: utf-8 -*-
"""
CLI 版打包配置（onedir 模式）。

打包命令：
    python -m PyInstaller build_cli.spec --clean --noconfirm

输出: dist/lceda-downloader/lceda-downloader.exe
"""

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules


PROJECT_ROOT = Path(SPECPATH).resolve()

npnp_bin = PROJECT_ROOT / "bin" / "npnp.exe"
if not npnp_bin.exists():
    npnp_bin = PROJECT_ROOT / "bin" / "npnp"

datas = []
if npnp_bin.exists():
    datas.append((str(npnp_bin), "bin"))
    print(f"[build_cli.spec] 打包 npnp: {npnp_bin}")

try:
    easyeda_datas = collect_data_files("easyeda2kicad")
    datas.extend(easyeda_datas)
except Exception:
    pass

project_modules = [
    "lceda_client",
    "downloader",
]

easyeda_hidden = collect_submodules("easyeda2kicad")

hiddenimports = (
    easyeda_hidden
    + project_modules
    + [
        "easyeda2kicad",
        "easyeda2kicad.easyeda.easyeda_api",
        "easyeda2kicad.easyeda.easyeda_importer",
        "requests",
        "lz4",
        "lz4.block",
        "lz4.frame",
    ]
)

a = Analysis(
    ["cli.py"],
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
        "PyQt6",
        "PySide2",
        "PySide6",
        "pyqtgraph",
        "OpenGL",
        "PIL",
        "numpy.testing",
        "pandas",
        "pandas.tests",
        "scipy",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="lceda-downloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="lceda-downloader",
)