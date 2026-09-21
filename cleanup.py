"""
项目清理脚本。

用法：
    python cleanup.py           # 预演，只列出会删什么
    python cleanup.py --apply   # 真的执行删除
"""

import argparse
import shutil
import sys
from pathlib import Path


# ============================================================
# 保留白名单（这些文件/目录不动）
# ============================================================

KEEP_FILES = {
    # 核心程序
    "gui_main.py",
    "cli.py",
    "downloader.py",
    "lceda_client.py",
    "easyeda_renderer.py",
    "easyeda_3d_renderer.py",
    # 打包配置
    "build.spec",
    "build_cli.spec",
    # 本项目清理脚本自身
    "cleanup.py",
    # GUI 子目录
    "gui/__init__.py",
    "gui/main_window.py",
    "gui/worker.py",
    "gui/svg_view.py",
    "gui/model_3d_view.py",
    "gui/model_3d_view_gl.py",
    # npnp
    "bin/npnp.exe",
    "bin/npnp",
}

KEEP_DIRS = {
    "gui",
    "bin",
    "output",       # 用户下载结果，看情况删
    "libs",         # 用户下载结果，看情况删
    ".git",
    ".vscode",
    ".idea",
}

# 明确删除的目录（无论内容）
DELETE_DIRS = {
    "__pycache__",
    "gui/__pycache__",
    "test_npnp_single",
    "test_npnp_shared",
    "test_npnp_step",
    "test_exe_output",
    "build",
    "dist",
    ".pytest_cache",
}


# ============================================================
# 清理逻辑
# ============================================================

def should_delete_file(name: str) -> bool:
    """判断文件是否应删"""
    # 白名单不动
    if name in KEEP_FILES:
        return False

    # Python 缓存
    if name.endswith(".pyc"):
        return True

    # 测试/探测脚本
    if name.startswith("probe_") and name.endswith(".py"):
        return True
    if name.startswith("test_") and name.endswith(".py"):
        return True
    if name.startswith("test_step") and name.endswith(".py"):
        return True

    # 探测产物
    for suffix in [".txt", ".svg", ".obj", ".step", ".stp"]:
        if name.startswith("probe_") and name.endswith(suffix):
            return True

    # 测试输出
    if name.startswith("output_test"):
        return True
        # 旧架构文件（已被 npnp 取代）
    legacy_files = {
        "symbol_parser.py",
        "package_parser.py",
        "coord_transform.py",
        "symbol_to_schlib.py",
        "package_to_pcblib.py",
        "pcblib_with_step.py",
        "step_downloader.py",
    }
    if name in legacy_files:
        return True

    return False

    return False


def should_delete_dir(name: str) -> bool:
    """判断目录是否应删"""
    if name in KEEP_DIRS:
        return False
    if name in DELETE_DIRS:
        return True
    return False


def collect_items(root: Path):
    """收集要删除的文件和目录"""
    files_to_del = []
    dirs_to_del = []

    for item in root.iterdir():
        # 顶层
        if item.is_dir():
            # 处理子目录（如 gui/）
            if item.name in DELETE_DIRS:
                dirs_to_del.append(item)
                continue
            if item.name in KEEP_DIRS:
                # 检查保留目录内部的子目录（如 gui/__pycache__）
                for sub in item.iterdir():
                    if sub.is_dir() and sub.name in DELETE_DIRS:
                        dirs_to_del.append(sub)
                    elif sub.is_dir() and sub.name == "__pycache__":
                        dirs_to_del.append(sub)
                continue
            # 不认识的目录，如果是 test_/output_test 开头，删
            if item.name.startswith("output_test") or item.name.startswith("test_"):
                dirs_to_del.append(item)
                continue
        elif item.is_file():
            if should_delete_file(item.name):
                files_to_del.append(item)
        # 其他情况：保留

    return files_to_del, dirs_to_del


def print_report(files_to_del, dirs_to_del, root: Path):
    print("=" * 70)
    print("将要删除的内容")
    print("=" * 70)

    if dirs_to_del:
        print(f"\n[目录] {len(dirs_to_del)} 个")
        for d in sorted(dirs_to_del):
            try:
                rel = d.relative_to(root)
            except ValueError:
                rel = d
            print(f"  {rel}/")

    if files_to_del:
        print(f"\n[文件] {len(files_to_del)} 个")
        for f in sorted(files_to_del):
            try:
                rel = f.relative_to(root)
            except ValueError:
                rel = f
            size = f.stat().st_size
            print(f"  {rel}  ({size:,} bytes)")

    print()
    print("=" * 70)
    print(f"合计: {len(dirs_to_del)} 个目录 + {len(files_to_del)} 个文件")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="真的执行删除（不加此参数只预演）")
    parser.add_argument("--root", default=".", help="项目根目录")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"[错误] 目录不存在: {root}")
        sys.exit(1)

    print(f"项目根目录: {root}\n")

    files_to_del, dirs_to_del = collect_items(root)

    if not files_to_del and not dirs_to_del:
        print("没有需要删除的内容")
        return

    print_report(files_to_del, dirs_to_del, root)

    if not args.apply:
        print()
        print(">>> 预演模式，未执行删除")
        print(">>> 确认无误后，运行: python cleanup.py --apply")
        return

    # 确认
    print()
    answer = input("确认删除以上内容？(yes/no): ").strip().lower()
    if answer != "yes":
        print("已取消")
        return

    # 执行
    deleted_dirs = 0
    deleted_files = 0

    for d in dirs_to_del:
        try:
            shutil.rmtree(d)
            deleted_dirs += 1
        except Exception as e:
            print(f"[失败] 删除目录 {d}: {e}")

    for f in files_to_del:
        try:
            f.unlink()
            deleted_files += 1
        except Exception as e:
            print(f"[失败] 删除文件 {f}: {e}")

    print()
    print("=" * 70)
    print(f"完成: 删除 {deleted_dirs} 个目录 + {deleted_files} 个文件")
    print("=" * 70)


if __name__ == "__main__":
    main()