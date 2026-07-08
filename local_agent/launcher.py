"""VisualDL 本机训练应用启动器（图形界面）。

功能：
- 图形界面（tkinter），带项目风格图标；
- 检测本机训练环境是否就绪，**未就绪时由用户点击按钮才下载/安装依赖**（不自动装）；
- 界面内可直接粘贴/更新令牌，保存到启动器自管配置（不依赖外部 config.json）；
- 虚拟环境创建在**启动器所在目录**下的 visualdl_runtime/venv；
- 启动并连接云端，实时显示连接状态与日志。

打包为单文件应用时（PyInstaller + 内置独立 Python），本文件是入口。
无图形环境时自动回退到命令行模式（--no-gui 亦可强制）。
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import traceback
from pathlib import Path

# 依赖清单（Windows/Linux 一律装 CUDA 版 PyTorch；macOS 装默认版）
BASE_REQUIREMENTS = ["websockets", "numpy", "fastapi", "pydantic"]
TORCH_REQUIREMENTS = ["torch", "torchvision"]
CUDA_INDEX_URL = "https://download.pytorch.org/whl/cu121"
DEFAULT_SERVER = "http://127.0.0.1:8000"


def _is_windows() -> bool:
    return platform.system() == "Windows"


def _is_macos() -> bool:
    return platform.system() == "Darwin"


def _deps_size_text() -> str:
    """首次需下载的依赖大小估计（含 PyTorch）。CUDA 版较大，macOS 默认版较小。"""
    return "约 200 MB" if _is_macos() else "约 2–3 GB"


def _launcher_dir() -> Path:
    """启动器/可执行文件所在目录（虚拟环境与配置都放在它下面）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent   # 打包 exe 所在目录
    return Path(__file__).resolve().parent              # 源码运行：launcher.py 所在目录


def _find_base_python() -> str | None:
    """找一个**真正的 Python 解释器**来创建虚拟环境。

    ⚠️ 打包成 exe 后 `sys.executable` 是 exe 自己，绝不能用它去执行 `-m venv`，
    否则会反复重启 exe 自身，造成进程炸弹 / 内存爆满。因此这里明确区分：
      - 源码运行：当前解释器就是真 Python；
      - 打包 exe：优先用随包内置的独立 Python（pybundle），否则用系统 PATH 里的 Python；
        都找不到就返回 None（由调用方明确报错，绝不递归启动自己）。
    """
    if not getattr(sys, "frozen", False):
        return sys.executable

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        names = ["python.exe"] if _is_windows() else ["python3", "python"]
        for sub in ("pybundle", "python", "."):
            for name in names:
                candidate = Path(meipass) / sub / name
                if candidate.exists():
                    return str(candidate)

    for name in ("python", "py", "python3"):
        found = shutil.which(name)
        if found:
            return found
    return None


# 启动器目录下新建的运行时文件夹：存放虚拟环境与启动器自管配置
APP_DIR = _launcher_dir() / "visualdl_runtime"
VENV_DIR = APP_DIR / "venv"
READY_MARKER = VENV_DIR / ".deps_ready"
SAVED_CONFIG = APP_DIR / "config.json"   # 启动器自管配置（令牌更新后存这里，最高优先）


def venv_python() -> Path:
    """虚拟环境内 Python 解释器路径（区分平台）。"""
    if _is_windows():
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def is_venv_ready() -> bool:
    """训练环境是否已创建且依赖已装好。"""
    return venv_python().exists() and READY_MARKER.exists()


def _agent_code_dir() -> Path:
    """包含 local_agent 包的目录（用于子进程 PYTHONPATH）。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", _launcher_dir()))
    here = Path(__file__).resolve().parent
    for d in (here, here.parent):
        if (d / "local_agent").is_dir():
            return d
    return here.parent


def _asset(name: str):
    """定位打包/源码中的资源文件（如图标）。"""
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "local_agent" / "assets" / name)
    candidates.append(Path(__file__).resolve().parent / "assets" / name)
    for p in candidates:
        if p.exists():
            return p
    return None


# —————————————————————————————————————————————
# 配置：随下载附带（seed）+ 启动器自管（authoritative）
# —————————————————————————————————————————————

def _read_json(path) -> dict:
    try:
        if path and Path(path).exists():
            return json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _shipped_config() -> dict:
    """随应用附带的 config.json（下载时注入的令牌），用于首次 seed。

    优先读可执行文件旁的外部 config.json；其次源码布局；最后打包内置。
    """
    meipass = getattr(sys, "_MEIPASS", None)
    for path in [
        _launcher_dir() / "config.json",
        Path(__file__).resolve().parent / "config.json",
        (Path(meipass) / "config.json") if meipass else None,
    ]:
        cfg = _read_json(path)
        if cfg:
            return cfg
    return {}


def load_config() -> dict:
    """有效配置：启动器自管配置优先，缺失项用随包附带的 seed 补齐。"""
    shipped = _shipped_config()
    saved = _read_json(SAVED_CONFIG)
    return {
        "server_url": saved.get("server_url") or shipped.get("server_url") or DEFAULT_SERVER,
        "token": saved.get("token") or shipped.get("token") or "",
    }


def save_config(server_url: str, token: str) -> None:
    """把令牌/地址保存到启动器自管配置（此后以此为准，不再依赖外部 config.json）。"""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    SAVED_CONFIG.write_text(
        json.dumps({"server_url": server_url, "token": token}, ensure_ascii=False),
        encoding="utf-8",
    )


# —————————————————————————————————————————————
# 环境准备（点击后才执行）与 Agent 子进程
# —————————————————————————————————————————————

def create_environment(log=print) -> None:
    """创建虚拟环境并安装依赖（含 CUDA 版 PyTorch）。仅在用户触发时调用。"""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if not venv_python().exists():
        base_python = _find_base_python()
        if not base_python:
            # 绝不用 exe 自己去建 venv（会递归自启动）；找不到 Python 就明确报错
            raise RuntimeError(
                "未找到可用的 Python 解释器，无法创建训练环境。\n"
                "请安装 Python 3.10 及以上版本（安装时勾选 Add Python to PATH），\n"
                "或改用『源码方式』运行：在含 launcher.py 的目录执行  python launcher.py"
            )
        log(f"[启动器] 正在创建训练环境（首次使用，只需一次）... 使用 {base_python}")
        subprocess.run([base_python, "-m", "venv", str(VENV_DIR)], check=True)
    py = str(venv_python())
    log("[启动器] 正在升级 pip ...")
    subprocess.run([py, "-m", "pip", "install", "--upgrade", "pip"], check=True)
    log("[启动器] 正在安装基础依赖 ...")
    subprocess.run([py, "-m", "pip", "install", *BASE_REQUIREMENTS], check=True)
    log(f"[启动器] 即将下载并安装 PyTorch（{_deps_size_text()}），首次较慢，请保持网络畅通 ...")
    torch_cmd = [py, "-m", "pip", "install", *TORCH_REQUIREMENTS]
    if not _is_macos():
        torch_cmd += ["--index-url", CUDA_INDEX_URL]
    subprocess.run(torch_cmd, check=True)
    READY_MARKER.write_text("ok", encoding="utf-8")
    log("[启动器] 训练环境准备完成。")


def start_agent_process(server_url: str, token: str) -> subprocess.Popen:
    """启动 Agent 子进程，stdout 行式输出（供界面/命令行读取）。"""
    env = dict(os.environ)
    code_dir = str(_agent_code_dir())
    env["PYTHONPATH"] = code_dir + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.Popen(
        [str(venv_python()), "-m", "local_agent.main", "--server", server_url, "--token", token],
        cwd=code_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )


# —————————————————————————————————————————————
# 图形界面
# —————————————————————————————————————————————

def run_gui(config: dict) -> None:
    import tkinter as tk
    from tkinter import scrolledtext, messagebox

    C_BG = "#f4f8fd"
    C_BLUE = "#0ea5e9"
    C_TEXT = "#1f2a44"
    C_MUTED = "#5b6b88"

    root = tk.Tk()
    root.title("VisualDL 本机训练应用")
    root.geometry("660x560")
    root.configure(bg=C_BG)
    _imgs = []  # 防止 PhotoImage 被回收
    icon = _asset("icon.png")
    if icon is not None:
        try:
            img = tk.PhotoImage(file=str(icon))
            root.iconphoto(True, img)
            _imgs.append(img)
        except Exception:
            pass

    ui = {"busy": False, "connected": False, "proc": None}

    # 头部：图标 + 标题
    header = tk.Frame(root, bg=C_BG)
    header.pack(fill="x", padx=20, pady=(18, 8))
    if _imgs:
        small = _imgs[0].subsample(max(1, _imgs[0].width() // 48))
        _imgs.append(small)
        tk.Label(header, image=small, bg=C_BG).pack(side="left")
    title_box = tk.Frame(header, bg=C_BG)
    title_box.pack(side="left", padx=12)
    tk.Label(title_box, text="VisualDL 本机训练应用", font=("Microsoft YaHei", 15, "bold"),
             fg=C_TEXT, bg=C_BG).pack(anchor="w")
    tk.Label(title_box, text="训练在你自己的电脑上进行", font=("Microsoft YaHei", 9),
             fg=C_MUTED, bg=C_BG).pack(anchor="w")

    # 令牌 / 服务器地址（界面内更新令牌）
    form = tk.Frame(root, bg=C_BG)
    form.pack(fill="x", padx=20, pady=6)
    tk.Label(form, text="登录令牌（从网页「本机训练应用」弹窗复制，失效时在此更新）",
             font=("Microsoft YaHei", 9), fg=C_MUTED, bg=C_BG).pack(anchor="w")
    token_var = tk.StringVar(value=config.get("token", ""))
    token_entry = tk.Entry(form, textvariable=token_var, font=("Consolas", 9), show="•")
    token_entry.pack(fill="x", pady=(2, 6), ipady=4)
    row = tk.Frame(form, bg=C_BG)
    row.pack(fill="x")
    tk.Label(row, text="服务器：", font=("Microsoft YaHei", 9), fg=C_MUTED, bg=C_BG).pack(side="left")
    server_var = tk.StringVar(value=config.get("server_url", DEFAULT_SERVER))
    tk.Entry(row, textvariable=server_var, font=("Consolas", 9)).pack(side="left", fill="x", expand=True, ipady=3)

    status_var = tk.StringVar(value="")
    tk.Label(root, textvariable=status_var, font=("Microsoft YaHei", 10, "bold"),
             fg=C_TEXT, bg=C_BG, anchor="w").pack(fill="x", padx=20, pady=(8, 4))

    # 主按钮 + 保存令牌
    btns = tk.Frame(root, bg=C_BG)
    btns.pack(fill="x", padx=20)
    action_btn = tk.Button(btns, text="", font=("Microsoft YaHei", 11, "bold"),
                           bg=C_BLUE, fg="white", activebackground="#0284c7",
                           activeforeground="white", relief="flat", cursor="hand2", pady=8)
    action_btn.pack(side="left", fill="x", expand=True)
    save_btn = tk.Button(btns, text="保存令牌", font=("Microsoft YaHei", 10),
                         relief="flat", cursor="hand2", pady=8, padx=12)
    save_btn.pack(side="left", padx=(10, 0))

    # 日志
    log_widget = scrolledtext.ScrolledText(root, height=14, font=("Consolas", 9),
                                           bg="#0f172a", fg="#cbd5e1", relief="flat", state="disabled")
    log_widget.pack(fill="both", expand=True, padx=20, pady=(10, 18))

    def log(msg: str) -> None:
        def _do():
            log_widget.configure(state="normal")
            log_widget.insert("end", msg + "\n")
            log_widget.see("end")
            log_widget.configure(state="disabled")
        root.after(0, _do)

    def set_status(text: str) -> None:
        root.after(0, lambda: status_var.set(text))

    def set_action(text: str, enabled: bool) -> None:
        root.after(0, lambda: action_btn.config(text=text, state=("normal" if enabled else "disabled")))

    def refresh_idle() -> None:
        if ui["busy"] or ui["connected"]:
            return
        if not token_var.get().strip():
            set_status("请先粘贴登录令牌")
            set_action("请先填写令牌", False)
        elif is_venv_ready():
            set_status("环境就绪，点击即可连接")
            set_action("启动并连接云端", True)
        else:
            set_status(f"首次使用需准备训练环境：约需下载 {_deps_size_text()} 依赖（含 PyTorch，只需一次）")
            set_action(f"准备训练环境并连接（首次下载{_deps_size_text()}）", True)

    def on_save() -> None:
        t = token_var.get().strip()
        s = server_var.get().strip() or DEFAULT_SERVER
        if not t:
            messagebox.showwarning("提示", "请先粘贴令牌。")
            return
        save_config(s, t)
        log("[启动器] 令牌已保存。")
        refresh_idle()

    def worker() -> None:
        s = server_var.get().strip() or DEFAULT_SERVER
        t = token_var.get().strip()
        if not t:
            ui["busy"] = False
            set_status("缺少令牌")
            refresh_idle()
            return
        save_config(s, t)
        try:
            if not is_venv_ready():
                set_status("正在准备训练环境（首次较慢）...")
                create_environment(log=log)
        except Exception as exc:  # noqa: BLE001
            log(f"[启动器] 环境准备失败：{exc}")
            set_status("环境准备失败，请重试")
            ui["busy"] = False
            set_action("重试准备环境并连接", True)
            return

        set_status("正在连接云端 ...")
        set_action("连接中 ...", False)
        try:
            proc = start_agent_process(s, t)
        except Exception as exc:  # noqa: BLE001
            log(f"[启动器] 启动失败：{exc}")
            ui["busy"] = False
            set_status("启动失败")
            set_action("重试", True)
            return
        ui["proc"] = proc
        for line in proc.stdout:
            line = line.rstrip()
            log(line)
            if "CONNECTED" in line or "已成功连接" in line:
                ui["connected"] = True
                set_status("✅ 已连接云端，回到网页即可训练")
            elif "403" in line:
                ui["connected"] = False
                set_status("❌ 令牌无效/已失效：请在上方更新令牌后点“保存令牌”再重试")
        ui["busy"] = False
        ui["connected"] = False
        set_status("连接已结束")
        refresh_idle()

    def on_action() -> None:
        if ui["busy"]:
            return
        if not token_var.get().strip():
            messagebox.showwarning("提示", "请先粘贴令牌。")
            return
        ui["busy"] = True
        threading.Thread(target=worker, daemon=True).start()

    action_btn.config(command=on_action)
    save_btn.config(command=on_save)
    token_var.trace_add("write", lambda *a: refresh_idle())
    refresh_idle()

    def on_close() -> None:
        proc = ui.get("proc")
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:  # noqa: BLE001
                pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


# —————————————————————————————————————————————
# 命令行回退
# —————————————————————————————————————————————

def run_cli(config: dict) -> None:
    server = config.get("server_url", DEFAULT_SERVER)
    token = config.get("token", "")
    if not token:
        _show_message("VisualDL 本机训练应用", "缺少登录令牌：请从网页重新下载应用。")
        sys.exit(1)
    save_config(server, token)
    if is_venv_ready():
        print("[启动器] 检测到已就绪的训练环境，直接启动。")
    else:
        create_environment()  # 失败时抛异常，由 main() 统一记录并弹窗提示（不静默、不递归）
    proc = start_agent_process(server, token)
    for line in proc.stdout:
        print(line.rstrip())
    sys.exit(proc.wait())


def _show_message(title: str, message: str) -> None:
    """在没有控制台的打包应用里也能弹出可见提示（Windows 用系统消息框）。"""
    print(f"{title}: {message}")
    try:
        if _is_windows():
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)  # MB_ICONERROR
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    # --windowed 打包后没有控制台，把所有输出与异常写进日志文件，便于排查
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        log_fp = open(APP_DIR / "launcher.log", "a", encoding="utf-8")
        sys.stdout = log_fp
        sys.stderr = log_fp
    except Exception:  # noqa: BLE001
        pass

    try:
        config = load_config()
        for i, arg in enumerate(sys.argv):
            if arg == "--server" and i + 1 < len(sys.argv):
                config["server_url"] = sys.argv[i + 1]
            if arg == "--token" and i + 1 < len(sys.argv):
                config["token"] = sys.argv[i + 1]

        if "--no-gui" not in sys.argv:
            try:
                import tkinter  # noqa: F401
                run_gui(config)
                return
            except Exception as exc:  # noqa: BLE001
                print(f"[启动器] 图形界面不可用，转命令行模式：{exc}")
                traceback.print_exc()
        run_cli(config)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        _show_message(
            "VisualDL 本机训练应用",
            f"启动失败：{exc}\n\n详细日志见：\n{APP_DIR / 'launcher.log'}",
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
