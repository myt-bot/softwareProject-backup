"""VisualDL 本机训练应用启动器（自举）。

打开应用后自动完成环境准备并启动 Agent，用户无需手敲任何命令：

    1. 检查本应用专属的虚拟环境是否已存在（~/.visualdl_agent/venv）；
    2. 已存在 → 直接用它启动 Agent；
    3. 不存在 → 自动创建虚拟环境并安装依赖（Windows/Linux 一律装 CUDA 版
       PyTorch，macOS 装默认版），装好后启动 Agent。

第二次以后打开都走「直接启动」，不再重复安装。

打包为单文件应用时（PyInstaller + 内置独立 Python），本文件是入口。
launcher 只用 Python 标准库，创建虚拟环境所需的「基础 Python」由打包时
内置的独立解释器提供，因此用户电脑上无需预装 Python。
"""

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

# 应用专属数据目录（名字足够独特，几乎不会与其他程序冲突）
APP_DIR = Path.home() / ".visualdl_agent"
VENV_DIR = APP_DIR / "venv"
READY_MARKER = VENV_DIR / ".deps_ready"

# 轻量依赖（从 PyPI 安装，很快）
BASE_REQUIREMENTS = ["websockets", "numpy", "fastapi", "pydantic"]
# 训练框架（Windows/Linux 用 CUDA 源，一律装 GPU 版；macOS 无 CUDA 装默认版）
TORCH_REQUIREMENTS = ["torch", "torchvision"]
CUDA_INDEX_URL = "https://download.pytorch.org/whl/cu121"


def _is_windows() -> bool:
    return platform.system() == "Windows"


def _is_macos() -> bool:
    return platform.system() == "Darwin"


def venv_python() -> Path:
    """返回虚拟环境内 Python 解释器的路径（区分平台）。"""
    if _is_windows():
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def is_venv_ready() -> bool:
    """判断本应用的虚拟环境是否已创建且依赖已装好。"""
    return venv_python().exists() and READY_MARKER.exists()


def _base_python() -> str:
    """创建虚拟环境使用的基础 Python。

    打包成单文件应用后，sys.executable 指向内置的独立 Python，可直接用它
    创建 venv；开发环境下则是当前 Python。
    """
    return sys.executable


def create_environment(log=print) -> None:
    """创建虚拟环境并安装全部依赖（含 CUDA 版 PyTorch）。"""
    APP_DIR.mkdir(parents=True, exist_ok=True)

    if not venv_python().exists():
        log("[启动器] 正在创建训练环境（首次使用，只需一次）...")
        subprocess.run([_base_python(), "-m", "venv", str(VENV_DIR)], check=True)

    py = str(venv_python())
    log("[启动器] 正在升级 pip ...")
    subprocess.run([py, "-m", "pip", "install", "--upgrade", "pip"], check=True)

    # 先装轻量依赖（快）
    log("[启动器] 正在安装基础依赖 ...")
    subprocess.run([py, "-m", "pip", "install", *BASE_REQUIREMENTS], check=True)

    # 再装 PyTorch：Windows/Linux 用 CUDA 源一律装 GPU 版；macOS 装默认版
    log("[启动器] 正在安装 PyTorch（首次较慢，请耐心等待）...")
    torch_cmd = [py, "-m", "pip", "install", *TORCH_REQUIREMENTS]
    if not _is_macos():
        torch_cmd += ["--index-url", CUDA_INDEX_URL]
    subprocess.run(torch_cmd, check=True)

    READY_MARKER.write_text("ok", encoding="utf-8")
    log("[启动器] 训练环境准备完成。")


def _load_config() -> dict:
    """读取随应用包附带的 config.json（含云端地址与令牌）。"""
    # 优先读应用包目录（打包后为可执行文件所在目录）里的 config.json
    candidates = [
        Path(getattr(sys, "_MEIPASS", "")) / "config.json" if hasattr(sys, "_MEIPASS") else None,
        Path(sys.argv[0]).resolve().parent / "config.json",
        Path(__file__).resolve().parent.parent / "config.json",
        APP_DIR / "config.json",
    ]
    for path in candidates:
        if path and path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
    return {}


def _agent_code_dir() -> Path:
    """返回包含 local_agent 包的目录，用于设置子进程的 PYTHONPATH。"""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # PyInstaller 解包目录
    return Path(__file__).resolve().parent.parent


def run_agent(server_url: str, token: str, log=print) -> int:
    """用虚拟环境里的 Python 启动本机 Agent（阻塞运行直到退出）。"""
    env = dict(os.environ)
    code_dir = str(_agent_code_dir())
    env["PYTHONPATH"] = code_dir + os.pathsep + env.get("PYTHONPATH", "")

    log("[启动器] 正在启动本机训练 Agent 并连接云端 ...")
    proc = subprocess.run(
        [str(venv_python()), "-m", "local_agent.main", "--server", server_url, "--token", token],
        cwd=code_dir,
        env=env,
    )
    return proc.returncode


def main() -> None:
    config = _load_config()
    # 命令行参数可覆盖 config.json（便于开发调试）
    server_url = config.get("server_url", "http://127.0.0.1:8000")
    token = config.get("token", "")
    for i, arg in enumerate(sys.argv):
        if arg == "--server" and i + 1 < len(sys.argv):
            server_url = sys.argv[i + 1]
        if arg == "--token" and i + 1 < len(sys.argv):
            token = sys.argv[i + 1]

    if not token:
        print("[启动器] 缺少令牌：请从网页「本机训练 Agent」弹窗下载带令牌的应用，"
              "或用 --token 提供令牌。")
        sys.exit(1)

    try:
        if is_venv_ready():
            print("[启动器] 检测到已就绪的训练环境，直接启动。")
        else:
            create_environment()
    except subprocess.CalledProcessError as exc:
        print(f"[启动器] 环境准备失败：{exc}")
        sys.exit(1)

    code = run_agent(server_url, token)
    sys.exit(code)


if __name__ == "__main__":
    main()
