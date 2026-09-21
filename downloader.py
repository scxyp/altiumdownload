"""
立创元器件下载器核心逻辑（基于 npnp）。

npnp 参数说明（v1.2.0）：
  npnp altium [OPTIONS] [COMPONENT]
    -i, --input <FILE>       多元器件 ID 文件
    -o, --output <OUTPUT>    输出目录
    --schlib                 仅导出 SchLib
    --pcblib                 仅导出 PcbLib
    --append                 追加到已有库
    --name <NAME>            库名
    -j <PARALLEL>            并发数（默认 4）
    --language <auto|en|zh>  元数据语言
    --force                  覆盖已有输出
"""

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


# ============================================================
# 查找 npnp 可执行文件
# ============================================================

def find_npnp() -> Optional[str]:
    """按优先级查找 npnp 可执行文件"""
    candidates = []

    # 1. 环境变量
    env_path = os.environ.get("NPNP_PATH")
    if env_path:
        candidates.append(Path(env_path))

    # 2. PyInstaller 解包目录
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "bin" / "npnp.exe")
            candidates.append(Path(meipass) / "bin" / "npnp")

    # 3. 程序同级 bin/
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
    else:
        exe_dir = Path(__file__).parent
    candidates.append(exe_dir / "bin" / "npnp.exe")
    candidates.append(exe_dir / "bin" / "npnp")

    # 4. 系统 PATH
    path_exe = shutil.which("npnp") or shutil.which("npnp.exe")
    if path_exe:
        candidates.append(Path(path_exe))

    for c in candidates:
        try:
            if c.exists():
                return str(c)
        except Exception:
            continue
    return None


def npnp_is_available() -> bool:
    return find_npnp() is not None


def npnp_version() -> Optional[str]:
    npnp = find_npnp()
    if not npnp:
        return None
    try:
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW

        r = subprocess.run(
            [npnp, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            creationflags=creationflags,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return None


# ============================================================
# 结果数据结构
# ============================================================

@dataclass
class DownloadResult:
    lcsc: str
    name: str = ""
    schlib_path: Optional[Path] = None
    pcblib_path: Optional[Path] = None
    step_path: Optional[Path] = None
    footprint_name: str = ""
    step_embedded: bool = False
    appended: bool = False
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and (
            self.schlib_path is not None
            or self.pcblib_path is not None
            or self.step_path is not None
        )

    def summary(self) -> str:
        if not self.success:
            return f"[失败] {self.lcsc}: {self.error}"
        parts = [f"[成功] {self.lcsc}  ({self.name})"]
        if self.schlib_path:
            mark = " (追加)" if self.appended else ""
            parts.append(f"  SchLib{mark}: {self.schlib_path}")
        if self.pcblib_path:
            mark = " (追加)" if self.appended else ""
            if self.step_embedded:
                mark += " (含 3D)"
            parts.append(f"  PcbLib{mark}: {self.pcblib_path}")
        if self.step_path:
            parts.append(f"  STEP:   {self.step_path}")
        return "\n".join(parts)


# ============================================================
# 内部工具
# ============================================================

def _sanitize_filename(s: str) -> str:
    bad = '<>:"/\\|?*'
    for ch in bad:
        s = s.replace(ch, "_")
    return s.strip() or "unnamed"


def _fetch_component_name(lcsc: str) -> str:
    """用 lceda_client 拿元器件名（用于独立库命名）"""
    try:
        from lceda_client import LCEDAClient
        client = LCEDAClient()
        data = client.get_component_data(lcsc)
        if not data:
            return lcsc
        result = data.get("result", {})
        data_str = result.get("dataStr", {})
        head = data_str.get("head", {})
        c_para = head.get("c_para", {})
        raw = c_para.get("name") or lcsc
        # 去掉 _Cxxxxx 后缀
        base = raw.split("_")[0] if "_" in raw else raw
        return _sanitize_filename(base)
    except Exception as e:
        print(f"[警告] 无法获取 {lcsc} 的名称: {e}")
        return _sanitize_filename(lcsc)


def _stream_subprocess(cmd: list, verbose: bool,
                       log_callback: Optional[Callable] = None,
                       timeout: float = None) -> tuple:
    """
    运行子进程并实时转发输出（Windows 下隐藏控制台窗口）。

    Returns:
        (returncode, stdout_text, stderr_text)
    """
    stdout_lines = []
    stderr_lines = []

    # Windows: 隐藏子进程控制台窗口
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )
    except FileNotFoundError:
        return (-1, "", f"找不到命令: {cmd[0]}")
    except Exception as e:
        return (-2, "", f"{type(e).__name__}: {e}")

    def _read(pipe, sink, tag):
        try:
            for line in iter(pipe.readline, ""):
                if not line:
                    break
                sink.append(line)
                if verbose:
                    stripped = line.rstrip("\n")
                    if stripped:
                        print(stripped)
                        if log_callback:
                            log_callback(stripped)
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    t_out = threading.Thread(target=_read, args=(proc.stdout, stdout_lines, "out"))
    t_err = threading.Thread(target=_read, args=(proc.stderr, stderr_lines, "err"))
    t_out.daemon = True
    t_err.daemon = True
    t_out.start()
    t_err.start()

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        t_out.join(timeout=2)
        t_err.join(timeout=2)
        return (-3, "".join(stdout_lines), "命令超时")

    t_out.join(timeout=5)
    t_err.join(timeout=5)

    return (proc.returncode, "".join(stdout_lines), "".join(stderr_lines))


# ============================================================
# 核心调用：npnp altium
# ============================================================

def _run_npnp_altium(
    lcsc_list: list,
    output_dir: Path,
    lib_name: Optional[str] = None,
    make_schlib: bool = True,
    make_pcblib: bool = True,
    append: bool = False,
    language: str = "auto",
    parallel: int = 4,
    verbose: bool = True,
    log_callback: Optional[Callable] = None,
) -> tuple:
    """
    调用 npnp altium 命令。

    Returns:
        (success: bool, error_msg: str)
    """
    npnp = find_npnp()
    if npnp is None:
        return False, "未找到 npnp 可执行文件"

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [npnp, "altium"]

    tmp_file = None
    if len(lcsc_list) == 1:
        cmd.append(lcsc_list[0])
    else:
        # 多元器件写入临时文件
        fd, tmp_name = tempfile.mkstemp(
            prefix="npnp_ids_", suffix=".txt",
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lcsc_list))
        tmp_file = tmp_name
        cmd.extend(["-i", tmp_name])

    cmd.extend(["-o", str(output_dir)])

    if lib_name:
        cmd.extend(["--name", _sanitize_filename(lib_name)])

    if make_schlib and not make_pcblib:
        cmd.append("--schlib")
    elif make_pcblib and not make_schlib:
        cmd.append("--pcblib")

    if append:
        cmd.append("--append")
    else:
        # 非追加模式，强制覆盖
        cmd.append("--force")

    if language and language != "auto":
        cmd.extend(["--language", language])

    if parallel and parallel > 1:
        cmd.extend(["-j", str(parallel)])

    if verbose:
        print(f"[npnp] 执行: {' '.join(cmd)}")

    try:
        rc, out, err = _stream_subprocess(
            cmd, verbose=verbose, log_callback=log_callback,
        )
    finally:
        if tmp_file:
            try:
                os.unlink(tmp_file)
            except Exception:
                pass

    if rc != 0:
        err_msg = (err or "").strip() or f"npnp 退出码 {rc}"
        return False, err_msg

    return True, ""


# ============================================================
# 独立库模式
# ============================================================

def download_one(
    lcsc: str,
    output_dir: Path,
    name_override: Optional[str] = None,
    make_schlib: bool = True,
    make_pcblib: bool = True,
    make_step: bool = False,
    verbose: bool = True,
    log_callback: Optional[Callable] = None,
) -> DownloadResult:
    """下载单个元器件，生成独立库文件。"""
    result = DownloadResult(lcsc=lcsc)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 确定库名
    if name_override:
        name = _sanitize_filename(name_override)
    else:
        if verbose:
            print(f"[{lcsc}] 获取元器件名称...")
        name = _fetch_component_name(lcsc)
    result.name = name

    # 2. 记录调用前的文件快照（用于识别新文件）
    before = set()
    for p in output_dir.iterdir():
        if p.is_file():
            before.add(p.name)

    # 3. 调用 npnp
    ok, err = _run_npnp_altium(
        [lcsc], output_dir,
        lib_name=name,
        make_schlib=make_schlib,
        make_pcblib=make_pcblib,
        append=False,
        verbose=verbose,
        log_callback=log_callback,
    )
    if not ok:
        result.error = err
        return result

    # 4. 找出新生成的文件（diff）
    after = set()
    for p in output_dir.iterdir():
        if p.is_file():
            after.add(p.name)
    new_files = after - before

    # 5. 按扩展名分类
    #    独立库文件命名格式: {任意名}__{lcsc}.SchLib / .PcbLib
    #    3D 可能嵌入 PcbLib 中，或单独的 .step
    suffix = f"__{lcsc}"

    for fname in new_files:
        full = output_dir / fname
        lower = fname.lower()

        if lower.endswith(".schlib"):
            result.schlib_path = full
        elif lower.endswith(".pcblib"):
            result.pcblib_path = full
            # 从 PcbLib 文件名推断 footprint 名（去掉后缀）
            stem = full.stem  # 如 "LQFP-100_...__C8315"
            if stem.endswith(suffix):
                result.footprint_name = stem[:-len(suffix)]
            else:
                result.footprint_name = stem
        elif lower.endswith(".step") or lower.endswith(".stp"):
            result.step_path = full

    # 6. 如果 diff 为空（比如 --force 覆盖了同名旧文件），
    #    退回后缀匹配
    if not new_files:
        if verbose:
            print(f"[{lcsc}] 未检测到新文件，尝试后缀匹配...")
        for p in output_dir.iterdir():
            if not p.is_file():
                continue
            if not p.stem.endswith(suffix):
                continue
            lower = p.name.lower()
            if lower.endswith(".schlib") and not result.schlib_path:
                result.schlib_path = p
            elif lower.endswith(".pcblib") and not result.pcblib_path:
                result.pcblib_path = p

    # 7. 检查成功
    if not result.success and result.error is None:
        result.error = "npnp 执行成功但未生成输出文件"

    return result


# ============================================================
# 共享库模式
# ============================================================

def download_to_shared_library(
    lcsc_list: list,
    output_dir: Path,
    lib_name: str,
    make_schlib: bool = True,
    make_pcblib: bool = True,
    make_step: bool = False,
    append: bool = False,
    verbose: bool = True,
    progress_callback: Optional[Callable] = None,
    log_callback: Optional[Callable] = None,
) -> list:
    """把所有元器件写入同一个库文件。"""
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _sanitize_filename(lib_name)
    results = []

    # 一次 npnp 调用导出全部
    if verbose:
        print(f"[共享库] 目标: {safe_name}.SchLib/.PcbLib")
        print(f"[共享库] 元器件数: {len(lcsc_list)}")
        print(f"[共享库] 模式: {'追加' if append else '覆盖'}")

    if progress_callback:
        progress_callback(0, len(lcsc_list),
                          f"调用 npnp 处理 {len(lcsc_list)} 个元器件...")

    t0 = time.time()
    ok, err = _run_npnp_altium(
        lcsc_list, output_dir,
        lib_name=safe_name,
        make_schlib=make_schlib,
        make_pcblib=make_pcblib,
        append=append,
        verbose=verbose,
        log_callback=log_callback,
    )
    elapsed = time.time() - t0

    # 输出文件路径
    schlib_path = output_dir / f"{safe_name}.SchLib"
    pcblib_path = output_dir / f"{safe_name}.PcbLib"

    # 为每个元器件构造结果（先并发拿名字）
    name_cache = {}
    if verbose:
        print("[共享库] 获取元器件名称...")
    for lcsc in lcsc_list:
        name_cache[lcsc] = _fetch_component_name(lcsc)

    for i, lcsc in enumerate(lcsc_list, 1):
        r = DownloadResult(lcsc=lcsc)
        r.name = name_cache.get(lcsc, lcsc)
        r.appended = append

        if ok:
            if make_schlib and schlib_path.exists():
                r.schlib_path = schlib_path
            if make_pcblib and pcblib_path.exists():
                r.pcblib_path = pcblib_path
            if not r.success:
                r.error = "输出文件未找到"
        else:
            r.error = err

        results.append(r)

        if progress_callback:
            progress_callback(
                i, len(lcsc_list),
                f"[{i}/{len(lcsc_list)}] {lcsc}"
            )

    if verbose:
        print(f"[共享库] 耗时 {elapsed:.1f}s")

    return results


# ============================================================
# 仅下载 3D 模型
# ============================================================

def download_step_only(
    lcsc: str,
    output_dir: Path,
    verbose: bool = True,
    log_callback: Optional[Callable] = None,
) -> DownloadResult:
    """只下载 STEP 3D 模型文件。"""
    result = DownloadResult(lcsc=lcsc)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    npnp = find_npnp()
    if npnp is None:
        result.error = "未找到 npnp 可执行文件"
        return result

    step_dir = output_dir / "step"
    step_dir.mkdir(parents=True, exist_ok=True)

    cmd = [npnp, "model", lcsc, "-o", str(step_dir), "--force"]
    if verbose:
        print(f"[npnp] 执行: {' '.join(cmd)}")

    rc, out, err = _stream_subprocess(
        cmd, verbose=verbose, log_callback=log_callback,
    )

    if rc != 0:
        result.error = (err or "").strip() or f"npnp 退出码 {rc}"
        return result

    # 查找生成的 .step / .stp 文件
    step_files = (
        list(step_dir.glob("*.step"))
        + list(step_dir.glob("*.stp"))
        + list(step_dir.glob("*.STEP"))
    )
    if step_files:
        result.step_path = step_files[0]
        result.step_embedded = True
        result.name = step_files[0].stem
    else:
        result.error = "未生成 STEP 文件"

    return result


# ============================================================
# 公共批量接口（保持签名兼容）
# ============================================================

def download_many(
    lcsc_list: list,
    output_dir: Path,
    name_override: Optional[str] = None,
    make_schlib: bool = True,
    make_pcblib: bool = True,
    make_step: bool = False,
    lib_name: Optional[str] = None,
    append: bool = False,
    step_only: bool = False,
    verbose: bool = True,
    progress_callback: Optional[Callable] = None,
    log_callback: Optional[Callable] = None,
) -> list:
    """批量下载入口（兼容旧接口）"""
    if not npnp_is_available():
        error_msg = "未找到 npnp。请把 npnp.exe 放到 bin/ 目录，或加入系统 PATH"
        print(f"[错误] {error_msg}")
        results = []
        for lcsc in lcsc_list:
            r = DownloadResult(lcsc=lcsc)
            r.error = error_msg
            results.append(r)
        return results

    # 仅 3D
    if step_only:
        results = []
        for i, lcsc in enumerate(lcsc_list, 1):
            if progress_callback:
                progress_callback(i, len(lcsc_list),
                                   f"[{i}/{len(lcsc_list)}] {lcsc}")
            r = download_step_only(
                lcsc, output_dir, verbose=verbose, log_callback=log_callback,
            )
            results.append(r)
        return results

    # 共享库
    if lib_name:
        return download_to_shared_library(
            lcsc_list, output_dir, lib_name,
            make_schlib=make_schlib,
            make_pcblib=make_pcblib,
            make_step=make_step,
            append=append,
            verbose=verbose,
            progress_callback=progress_callback,
            log_callback=log_callback,
        )

    # 独立库
    results = []
    total = len(lcsc_list)
    for i, lcsc in enumerate(lcsc_list, 1):
        if progress_callback:
            progress_callback(i, total, f"[{i}/{total}] {lcsc}")
        if verbose:
            print(f"\n[{i}/{total}] {lcsc}")
        r = download_one(
            lcsc, output_dir,
            name_override=name_override,
            make_schlib=make_schlib,
            make_pcblib=make_pcblib,
            make_step=make_step,
            verbose=verbose,
            log_callback=log_callback,
        )
        results.append(r)
        if verbose:
            print(r.summary())
    return results