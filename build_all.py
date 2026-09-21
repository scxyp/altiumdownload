"""
一键打包脚本：
    python build_all.py

依次打包 CLI 版和 GUI 版，输出到 dist/。
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd, timeout=1200):
    print(f"\n>>> {' '.join(cmd)}")
    print("-" * 70)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
    )
    # 只打印末尾 40 行
    lines = (r.stdout or "").splitlines()
    if len(lines) > 40:
        print("\n".join(lines[:5]))
        print(f"...(省略 {len(lines) - 45} 行)...")
        print("\n".join(lines[-40:]))
    else:
        print(r.stdout or "(无输出)")

    if r.stderr:
        err_lines = r.stderr.splitlines()
        if len(err_lines) > 20:
            print("STDERR (末尾20行):")
            print("\n".join(err_lines[-20:]))
        else:
            print("STDERR:", r.stderr)
    print(f"exit code: {r.returncode}")
    return r


def main():
    project_dir = Path(__file__).parent.resolve()
    os.chdir(project_dir)

    # 检查 PyInstaller 是否可用
    try:
        import PyInstaller  # noqa
    except ImportError:
        print("[错误] PyInstaller 未安装")
        print("请运行: pip install pyinstaller")
        sys.exit(1)

    # 检查新增依赖
    missing = []
    for lib in ["pyqtgraph", "OpenGL"]:
        try:
            __import__(lib)
        except ImportError:
            missing.append(lib)
    if missing:
        print(f"[警告] 缺少依赖: {', '.join(missing)}")
        print(f"请运行: pip install {' '.join(missing)}")
        print("（继续打包可能导致 GUI 3D 模型无法显示）\n")

    # 清理旧产物
    for d in ["build", "dist"]:
        p = project_dir / d
        if p.exists():
            print(f"清理 {d}/...")
            shutil.rmtree(p, ignore_errors=True)

    # 自动生成的 spec（避免冲突）
    for f in ["LCEDA_Altium_Downloader.spec", "lceda-downloader.spec"]:
        p = project_dir / f
        if p.exists():
            p.unlink()

    print("=" * 70)
    print("第 1 步：打包 CLI 版本")
    print("=" * 70)
    r = run([
        sys.executable, "-m", "PyInstaller",
        "build_cli.spec", "--clean", "--noconfirm",
    ])
    if r.returncode != 0:
        print("[失败] CLI 打包失败")
        sys.exit(1)

    cli_exe = project_dir / "dist" / "lceda-downloader.exe"
    if not cli_exe.exists():
        print(f"[失败] CLI exe 未生成: {cli_exe}")
        sys.exit(1)
    size_mb = cli_exe.stat().st_size / 1024 / 1024
    print(f"\n[成功] CLI exe: {cli_exe.name} ({size_mb:.1f} MB)")

    print()
    print("=" * 70)
    print("第 2 步：打包 GUI 版本")
    print("=" * 70)
    r = run([
        sys.executable, "-m", "PyInstaller",
        "build.spec", "--clean", "--noconfirm",
    ])
    if r.returncode != 0:
        print("[失败] GUI 打包失败")
        sys.exit(1)

    gui_exe = project_dir / "dist" / "LCEDA_Altium_Downloader.exe"
    if not gui_exe.exists():
        print(f"[失败] GUI exe 未生成: {gui_exe}")
        sys.exit(1)
    size_mb = gui_exe.stat().st_size / 1024 / 1024
    print(f"\n[成功] GUI exe: {gui_exe.name} ({size_mb:.1f} MB)")

    # 最终统计
    print()
    print("=" * 70)
    print("打包完成")
    print("=" * 70)
    print(f"输出目录: {project_dir / 'dist'}")
    print()
    for f in sorted((project_dir / "dist").iterdir()):
        size_mb = f.stat().st_size / 1024 / 1024
        print(f"  {f.name}  ({size_mb:.1f} MB)")
    print()
    print("请手动双击 dist/LCEDA_Altium_Downloader.exe 验证 GUI 是否正常启动。")


if __name__ == "__main__":
    main()