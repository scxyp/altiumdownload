@echo off
chcp 65001 >nul
echo ============================================
echo  LCEDA Altium Downloader - 清理临时文件
echo ============================================
echo.

cd /d "%~dp0"

echo [1/5] 删除探测脚本...
del /q probe_*.py 2>nul

echo [2/5] 删除探测产物...
del /q probe_*.svg 2>nul
del /q probe_*.obj 2>nul
del /q probe_*.step 2>nul
del /q probe_*.wrl 2>nul

echo [3/5] 删除 Python 缓存...
for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"

echo [4/5] 删除 PyInstaller 中间产物...
if exist "build" rmdir /s /q "build"

echo [5/5] 删除测试输出目录...
for /d %%d in (output_test* output_exe_test) do @if exist "%%d" rmdir /s /q "%%d"

echo.
echo ============================================
echo  清理完成
echo ============================================
echo.
echo 保留的核心文件：
echo   cli.py, gui_main.py, downloader.py
echo   lceda_client.py, symbol_parser.py, package_parser.py
echo   coord_transform.py, symbol_to_schlib.py
echo   package_to_pcblib.py, pcblib_with_step.py
echo   step_downloader.py, easyeda_renderer.py
echo   easyeda_3d_renderer.py, build.spec, build_cli.spec
echo   gui/ (5 个模块)
echo.
pause