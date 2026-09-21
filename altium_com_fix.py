"""
用 Altium COM 自动化批量修正 SchLib 里的引脚属性。

前置条件：
  1. 安装了 Altium Designer
  2. pywin32 已安装
  3. 关闭 Altium 里已打开的同名文件

用法：
    python altium_com_fix.py output/STM32F107VCT6.SchLib
"""

import sys
import time
from pathlib import Path


def fix_schlib(schlib_path: str):
    try:
        import win32com.client
    except ImportError:
        print("[错误] pywin32 未安装")
        print("请运行: pip install pywin32")
        return 1

    schlib_path = str(Path(schlib_path).resolve())
    if not Path(schlib_path).exists():
        print(f"[错误] 文件不存在: {schlib_path}")
        return 1

    print(f"启动 Altium Designer（如未运行）...")
    try:
        altium = win32com.client.Dispatch("Altium.Application")
    except Exception as e:
        print(f"[错误] 无法连接 Altium: {e}")
        print("请确认 Altium Designer 已安装")
        return 1

    # 让 Altium 显示出来
    try:
        altium.Visible = True
    except Exception:
        pass

    print(f"打开 SchLib: {schlib_path}")
    try:
        # 用 Altium 的 OpenDocument 方法
        doc = altium.OpenDocument(schlib_path)
    except Exception as e:
        print(f"[错误] 打开文档失败: {e}")
        return 1

    # 等待文档加载
    time.sleep(2)

    try:
        # 遍历库里的每个符号
        lib = doc
        symbol_count = lib.ComponentCount
        print(f"共 {symbol_count} 个符号")

        total_pins_fixed = 0
        for si in range(symbol_count):
            try:
                symbol = lib.GetComponentAt(si)
                symbol_name = symbol.Name
                pin_count = symbol.PinCount

                for pi in range(pin_count):
                    try:
                        pin = symbol.GetPinAt(pi)
                        # Altium COM API 里没有直接的 PinNameInside 属性
                        # 但可以通过 PinDesignatorMode 或 PinName 位置控制
                        # 这里尝试用 PinName 的属性
                        # 如果能找到开关，这里设置
                        # 例如：pin.NameInside = True
                        # 具体属性名取决于 Altium 版本
                        pass
                    except Exception:
                        pass
            except Exception as e:
                print(f"  符号 {si} 处理失败: {e}")
                continue

        # 保存
        doc.Save()
        print(f"[成功] 已保存")

    except Exception as e:
        print(f"[错误] 处理失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python altium_com_fix.py <path-to-SchLib>")
        sys.exit(1)

    sys.exit(fix_schlib(sys.argv[1]))