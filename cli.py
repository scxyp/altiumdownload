"""
命令行入口：
    python cli.py C668215 -o output/                       # 独立库
    python cli.py C668215 C1523 --lib-name mylib -o out/   # 共享库
    python cli.py C668215 --lib-name mylib --append -o out/ # 追加
    python cli.py C668215 --step-only -o out/              # 只下 STEP 模型
"""

import argparse
import sys
from pathlib import Path

from downloader import download_many


def parse_args():
    p = argparse.ArgumentParser(
        prog="lceda-altium-downloader",
        description="从立创EDA下载元器件并生成 Altium SchLib / PcbLib",
    )
    p.add_argument("lcsc", nargs="+",
                   help="一个或多个 LCSC 编号")
    p.add_argument("-o", "--output", default="output",
                   help="输出目录（默认 ./output）")
    p.add_argument("-n", "--name", default=None,
                   help="覆盖符号/封装名称（只在下载单个时有效）")
    p.add_argument("--lib-name", default=None,
                   help="把所有元器件写入同一个库文件 {lib-name}.SchLib/.PcbLib")
    p.add_argument("--append", action="store_true",
                   help="与 --lib-name 配合：追加到已有库（同名覆盖）")
    p.add_argument("--schlib-only", action="store_true", help="只生成 SchLib")
    p.add_argument("--pcblib-only", action="store_true", help="只生成 PcbLib")
    p.add_argument("--with-3d", action="store_true",
                   help="下载并嵌入 STEP 3D 模型")
    p.add_argument("--step-only", action="store_true",
                   help="只下载 STEP 3D 模型文件（不生成 SchLib/PcbLib）")
    p.add_argument("-q", "--quiet", action="store_true", help="静默模式")
    return p.parse_args()


def main():
    args = parse_args()

    if args.schlib_only and args.pcblib_only:
        print("[错误] --schlib-only 和 --pcblib-only 不能同时使用")
        sys.exit(1)

    if args.append and not args.lib_name:
        print("[错误] --append 必须与 --lib-name 一起使用")
        sys.exit(1)

    if args.step_only:
        make_schlib = False
        make_pcblib = False
        make_step = False
    else:
        make_schlib = not args.pcblib_only
        make_pcblib = not args.schlib_only
        make_step = args.with_3d and make_pcblib
        if args.with_3d and args.schlib_only:
            print("[警告] --with-3d 需要生成 PcbLib，已自动忽略")
            make_step = False

    if args.name and len(args.lcsc) > 1:
        print("[警告] --name 只在单个下载时有效，已忽略")

    output_dir = Path(args.output)
    verbose = not args.quiet

    print(f"输出目录: {output_dir.resolve()}")
    print(f"下载数量: {len(args.lcsc)}")

    if args.step_only:
        print("模式: 仅下载 3D 模型")
    elif args.lib_name:
        mode = "追加" if args.append else "共享库(重建)"
        print(f"库模式: {mode} (名称: {args.lib_name})")
    else:
        print(f"库模式: 每个元器件独立库")

    targets = []
    if make_schlib:
        targets.append("SchLib")
    if make_pcblib:
        targets.append("PcbLib" + ("(含3D)" if make_step else ""))
    if args.step_only:
        targets.append("STEP")
    if targets:
        print(f"生成: {' + '.join(targets)}")

    results = download_many(
        args.lcsc, output_dir,
        name_override=args.name,
        make_schlib=make_schlib,
        make_pcblib=make_pcblib,
        make_step=make_step,
        lib_name=args.lib_name,
        append=args.append,
        step_only=args.step_only,
        verbose=verbose,
    )

    ok = [r for r in results if r.success]
    fail = [r for r in results if not r.success]

    print()
    print("=" * 70)
    print(f"完成: {len(ok)} 成功, {len(fail)} 失败")
    print("=" * 70)
    for r in results:
        print(f"  {r.summary().splitlines()[0]}")

    sys.exit(0 if not fail else 1)


if __name__ == "__main__":
    main()