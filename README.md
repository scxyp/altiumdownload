# LCEDA → Altium 元器件下载器

从立创EDA（LCSC）搜索、预览并批量下载元器件，一键生成 Altium Designer 可直接使用的原理图库（`.SchLib`）和 PCB 封装库（`.PcbLib`），支持嵌入 STEP 3D 模型。

## ✨ 功能特性

### 搜索与预览

- 🔍 **关键字搜索**：支持型号、描述、LCSC 编号
- 🎨 **符号预览**：SVG 渲染，可缩放拖拽
- 📐 **封装预览**：SVG 渲染，白底适配大封装
- 🧊 **3D 模型预览**：OpenGL 硬件加速，可旋转/缩放
- 🔢 **多部件切换**：自动识别多 part 符号（如双运放、多路逻辑门）

### 下载与转换

- 📚 **独立库模式**：每个元器件生成单独的库文件
- 📦 **共享库模式**：多个元器件合并到一个库文件
- ➕ **追加模式**：向已有库追加新元器件（同名自动覆盖）
- 🎯 **仅下载 3D**：只保存 STEP 模型文件
- 🏷️ **元数据语言**：支持中文 / 英文 / 自动选择

### 用户体验

- 🖥️ **图形界面**（PyQt6）+ **命令行**（CLI）双入口
- 📊 **实时日志**：下载进度、每个元器件状态一目了然
- 🚫 **无控制台弹窗**：子进程静默执行
- ⚡ **快速启动**：onedir 打包，2-3 秒出界面

## 🖥️ 系统要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10 / 11（64位） |
| Altium Designer | **23.x 或更高版本** |
| 网络 | 需要访问 easyeda.com 和 lcsc.com |

> ⚠️ **重要**：npnp 生成的库文件采用高版本 Altium 格式。用 Altium 23 以下版本打开会报 `Access violation in AdvSch.dll` 错误。请确保使用 Altium 23.x 或更新版本。

## 🚀 快速开始

### 方式一：使用打包好的可执行文件（推荐给最终用户）

1. 下载 `dist/LCEDA_Altium_Downloader/` 文件夹
2. 双击 `LCEDA_Altium_Downloader.exe` 启动
3. 在搜索框输入型号（如 `STM32F107VCT6` 或 `C8315`）
4. 选中结果，点击"下载选中"

> **注意**：不要单独复制 exe 文件，必须保留整个文件夹（包含 `_internal/` 目录）。分发给他人时压缩整个文件夹为 zip 即可。

### 方式二：命令行（适合脚本集成）

**单个元器件**：

```bash
lceda-downloader.exe C8315 -o output
```

**批量下载**：

```bash
lceda-downloader.exe C8315 C668215 C1523 -o output
```

**共享库（合并到一个库文件）**：

```bash
lceda-downloader.exe C8315 C668215 --lib-name MyLib -o output
```

**追加到已有库**：

```bash
lceda-downloader.exe C1523 --lib-name MyLib --append -o output
```

**仅生成 SchLib**：

```bash
lceda-downloader.exe C8315 --schlib-only -o output
```

**仅下载 3D 模型**：

```bash
lceda-downloader.exe C8315 --step-only -o output
```

### 方式三：从源码运行（开发者）

**1. 安装依赖**：

```bash
pip install requests easyeda2kicad altium-monkey PyQt6 pyqtgraph PyOpenGL PyOpenGL_accelerate
```

**2. 下载 npnp.exe 到 bin/ 目录**：

从 `https://github.com/ref42/npnp/releases` 下载对应版本，放到 `bin/npnp.exe`。

**3. 运行**：

```bash
python gui_main.py
```

```bash
python cli.py C8315
```

## 📖 使用说明

### GUI 界面

| 区域 | 功能 |
| --- | --- |
| 顶部搜索栏 | 输入型号/关键字/LCSC 编号，回车或点击搜索 |
| 结果表格 | 显示 LCSC、型号、封装、描述、制造商、库存、CAD 状态 |
| 预览标签页 | 符号 / 封装 / 3D 模型，多部件时顶部有 P1/P2... 切换按钮 |
| 下载选项 | 勾选输出格式，选择是否嵌入 3D 模型 |
| 库命名 | 选择独立库 / 共享库 / 追加模式 |
| 运行日志 | 实时显示下载过程 |

**CAD 列图例**：

| 标记 | 含义 |
| --- | --- |
| `SF3` | 有符号 + 有封装 + 有 3D |
| `SF-` | 有符号 + 有封装，无 3D |
| `S--` | 只有符号 |
| `---` | 立创未提供 CAD 数据（显示灰色） |

### 输出文件命名

| 模式 | SchLib | PcbLib |
| --- | --- | --- |
| 独立库 | `{元件名}__{LCSC}.SchLib` | `{封装名}__{LCSC}.PcbLib` |
| 共享库 | `{库名}.SchLib` | `{库名}.PcbLib` |
| STEP | `{封装名}__{LCSC}.step` | — |

例如 `C8315`（STM32F107VCT6）会生成：

```
STM32F107VCT6__C8315.SchLib
LQFP-100_L14.0-W14.0-P0.50-LS16.0-BL__C8315.PcbLib
```

### CLI 参数

| 参数 | 说明 |
| --- | --- |
| `lcsc` | 一个或多个 LCSC 编号（如 `C8315 C668215`） |
| `-o, --output` | 输出目录（默认 `output`） |
| `-n, --name` | 覆盖元件名（仅单个下载时有效） |
| `--lib-name` | 共享库名，所有元器件写入同一库 |
| `--append` | 与 `--lib-name` 配合使用，追加到已有库 |
| `--schlib-only` | 只生成 SchLib |
| `--pcblib-only` | 只生成 PcbLib |
| `--with-3d` | 嵌入 STEP 3D 模型（需要 easyeda2kicad） |
| `--step-only` | 只下载 STEP 模型，不生成库文件 |
| `-q, --quiet` | 静默模式 |

## 🏗️ 项目结构

```
altiumdownload/
├── bin/
│   └── npnp.exe                    # npnp 引擎（Altium 库生成核心）
│
├── gui/
│   ├── __init__.py
│   ├── main_window.py              # 主窗口
│   ├── worker.py                   # 后台线程（搜索/下载/预览）
│   ├── svg_view.py                 # SVG 预览组件
│   ├── model_3d_view.py            # QPainter 3D 回退渲染
│   └── model_3d_view_gl.py         # OpenGL 3D 渲染
│
├── gui_main.py                     # GUI 入口
├── cli.py                          # CLI 入口
├── downloader.py                   # npnp 调用核心
├── lceda_client.py                 # 立创 API 客户端
├── easyeda_renderer.py             # 符号/封装 SVG 渲染
├── easyeda_3d_renderer.py          # 3D 预览数据解析
│
├── build.spec                      # GUI 打包配置（onedir）
├── build_cli.spec                  # CLI 打包配置（onedir）
│
├── output/                         # 默认输出目录
└── dist/                           # 打包产物
```

## 🔧 技术架构

### 核心依赖

| 组件 | 用途 |
| --- | --- |
| [npnp](https://github.com/ref42/npnp) | 立创元件 → Altium 库 转换引擎（Rust） |
| [PyQt6](https://pypi.org/project/PyQt6/) | GUI 框架 |
| [pyqtgraph](https://pypi.org/project/pyqtgraph/) | OpenGL 3D 渲染 |
| [easyeda2kicad](https://pypi.org/project/easyeda2kicad/) | 预览数据获取 + 3D 模型下载 |
| [requests](https://pypi.org/project/requests/) | HTTP 请求 |

### 工作流程

```
用户输入
   ↓
[lceda_client] 搜索 / 获取元器件信息
   ↓
[downloader] 组装 npnp 命令
   ↓
[npnp.exe] 立创 API → Altium 库文件
   ↓
输出 .SchLib / .PcbLib / .step
```

### 预览流程

```
点击元件行
   ↓
并行启动 2 个后台线程：
  ├─ [PreviewWorker] 符号 + 封装 SVG
  └─ [Model3DWorker] 3D 模型数据
   ↓
GUI 显示预览
```

## 📦 打包

**GUI 版**：

```bash
python -m PyInstaller build.spec --clean --noconfirm
```

**CLI 版**：

```bash
python -m PyInstaller build_cli.spec --clean --noconfirm
```

输出：

- `dist/LCEDA_Altium_Downloader/`（整个文件夹分发）
- `dist/lceda-downloader/`（整个文件夹分发）

## ❓ 常见问题

### Q1：Altium 打开库报 `Access violation in AdvSch.dll`

**原因**：你的 Altium 版本低于 23.x，不支持 npnp 生成的新版格式。

**解决**：升级 Altium 到 23 或更高版本。

### Q2：下载时提示"未找到 npnp"

**原因**：`npnp.exe` 未打包进去或路径不对。

**解决**：

- 源码运行：确认 `bin/npnp.exe` 存在
- 打包运行：确认 `dist/LCEDA_Altium_Downloader/_internal/bin/npnp.exe` 存在
- 或设置环境变量 `NPNP_PATH` 指向 npnp.exe

### Q3：GUI 里的 3D 模型是空的

**原因**：

- 该元器件立创未提供 3D 模型
- 或 OpenGL 环境不可用（会自动退化为 QPainter 渲染）

**解决**：查看日志区的提示信息。CAD 列不显示 `3` 表示无 3D 模型。

### Q4：搜索很慢或超时

**原因**：立创 API 临时故障或网络问题。

**解决**：本工具内置重试机制（每个请求最多 4 次，指数退避），如持续失败请检查网络连接或稍后再试。

### Q5：如何分发给他人？

**推荐方式**：把 `dist/LCEDA_Altium_Downloader/` 整个文件夹压缩成 zip，发送 zip 文件。

**不要**只发 exe 文件，因为它依赖同目录的 `_internal/` 文件夹。

### Q6：怎样加自定义图标？

1. 准备一个 `.ico` 文件（建议 256×256）
2. 放到项目根目录（如 `icon.ico`）
3. 编辑 `build.spec`，把 `icon=None` 改成 `icon='icon.ico'`
4. 重新打包

## 🛠️ 开发者指引

### 添加新功能

- **修改下载逻辑**：编辑 `downloader.py`
- **修改搜索逻辑**：编辑 `lceda_client.py`
- **修改预览渲染**：编辑 `easyeda_renderer.py` 或 `easyeda_3d_renderer.py`
- **修改界面**：编辑 `gui/main_window.py`
- **添加后台任务**：编辑 `gui/worker.py`

### 调试技巧

**GUI 模式下查看控制台输出**（Windows 下用 CMD 启动）：

```bash
dist\LCEDA_Altium_Downloader\LCEDA_Altium_Downloader.exe
```

**查看 npnp 日志**：

```bash
dist\lceda-downloader\lceda-downloader.exe C8315 -o test
```

**检查 npnp 是否可用**：

```bash
python -c "from downloader import find_npnp, npnp_version; print(find_npnp()); print(npnp_version())"
```

## 📄 许可

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

使用的第三方组件：

| 组件 | 许可 |
| --- | --- |
| npnp | MIT License |
| PyQt6 | GPL v3 / 商业许可 |
| pyqtgraph | MIT License |
| easyeda2kicad | MIT License |

## 🙏 致谢

### 项目作者

**scxyp** — 项目设计、开发与维护

- GitHub：[@scxyp](https://github.com/scxyp)

### 开发协助

本项目的架构设计与代码实现过程中，得到了 **DeepSeek** 的协助：

- 技术方案讨论与架构设计
- Python / PyQt6 / OpenGL 代码编写与调试
- npnp 集成方案与打包配置
- 文档撰写

### 开源项目

- [npnp](https://github.com/ref42/npnp) — 优秀的立创元件导出工具，本项目的核心转换引擎
- [easyeda2kicad](https://github.com/uPesy/easyeda2kicad.py) — 立创 API 封装
- [altium-monkey](https://pypi.org/project/altium-monkey/) — Altium 文件操作库
