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
# 线上服务器（共用包删掉 config.json 后的默认值，务必是生产域名，否则连不上）
DEFAULT_SERVER = "https://fk.kanzakiyui.com"


def _is_windows() -> bool:
    return platform.system() == "Windows"


def _is_macos() -> bool:
    return platform.system() == "Darwin"


def _deps_size_text() -> str:
    """首次需下载的依赖大小估计（含 PyTorch）。CUDA 版较大，macOS 默认版较小。"""
    return "约 200 MB" if _is_macos() else "约 2–3 GB"


def _subprocess_flags() -> dict:
    """子进程不弹出黑色控制台窗口（Windows 上 CREATE_NO_WINDOW）。"""
    if _is_windows():
        return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
    return {}


def _launcher_dir() -> Path:
    """启动器/可执行文件所在目录（虚拟环境与配置都放在它下面）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent   # 打包 exe 所在目录
    return Path(__file__).resolve().parent              # 源码运行：launcher.py 所在目录


def _python_in(directory: Path):
    """在一个独立 Python 目录里找到 python 可执行文件（兼容不同布局）。"""
    names = ["python.exe"] if _is_windows() else ["python3", "python"]
    for name in names:
        for cand in (directory / name, directory / "bin" / name):
            if cand.exists():
                return cand
    return None


def _ensure_base_python(log=print) -> str | None:
    """返回一个**可长期使用的真 Python 解释器**路径，用于创建虚拟环境。

    ⚠️ 打包成单文件 exe 后：
      - `sys.executable` 是 exe 自己，绝不能用它执行 `-m venv`（会反复重启自身 →
        进程炸弹 / 内存爆满）；
      - 内置的独立 Python 被解包到临时目录 `_MEIPASS`，exe 退出即删；直接用它建的
        venv 会指向这个临时路径、下次启动就失效。
    因此这里**首次运行把内置 Python 复制到 visualdl_runtime/pybase（永久目录）**，
    之后一直用它。找不到任何可用 Python 时返回 None（调用方明确报错，绝不递归自启动）。
    """
    if not getattr(sys, "frozen", False):
        # 源码 / 内置 Python 文件夹方式：当前解释器就是真 Python。
        # 若是 pythonw.exe（无控制台），换成同目录的 python.exe 建 venv。
        exe = sys.executable
        if exe.lower().endswith("pythonw.exe"):
            alt = Path(exe).with_name("python.exe")
            if alt.exists():
                return str(alt)
        return exe

    # —— 打包 exe —— #
    pybase = APP_DIR / "pybase"
    found = _python_in(pybase)
    if found:                                  # 已复制过的永久内置 Python
        return str(found)

    # exe 旁边直接放了 python/ 目录（文件夹方式，本身就永久，无需复制）
    for sub in ("python", "pybundle"):
        found = _python_in(_launcher_dir() / sub)
        if found:
            return str(found)

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        for sub in ("python", "pybundle"):
            src = Path(meipass) / sub
            if src.is_dir():
                log("[启动器] 正在准备内置 Python（首次，只需一次）...")
                APP_DIR.mkdir(parents=True, exist_ok=True)
                shutil.copytree(src, pybase, dirs_exist_ok=True)   # 复制到永久目录
                found = _python_in(pybase)
                if found:
                    return str(found)

    # 兜底：系统 PATH 里的 Python
    for name in ("python", "py", "python3"):
        which = shutil.which(name)
        if which:
            return which
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
        # 打包 exe：_MEIPASS 退出即删，Agent 子进程会因此崩溃；
        # 首次把 local_agent 复制到永久目录 visualdl_runtime，从那里运行。
        meipass = getattr(sys, "_MEIPASS", None)
        target = APP_DIR / "local_agent"
        if meipass and not (target / "__init__.pyc").exists() and not (target / "__init__.py").exists():
            src = Path(meipass) / "local_agent"
            if src.is_dir():
                APP_DIR.mkdir(parents=True, exist_ok=True)
                shutil.copytree(src, target, dirs_exist_ok=True)
        return APP_DIR if target.is_dir() else Path(meipass or _launcher_dir())
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
        base_python = _ensure_base_python(log)
        if not base_python:
            # 绝不用 exe 自己去建 venv（会递归自启动）；找不到 Python 就明确报错
            raise RuntimeError(
                "未找到可用的 Python 解释器，无法创建训练环境。\n"
                "该应用应内置独立 Python；若你是用源码运行，请安装 Python 3.10+，"
                "或在含 launcher.py 的目录执行  python launcher.py"
            )
        log("[启动器] 正在创建训练环境（首次使用，只需一次）...")
        subprocess.run([base_python, "-m", "venv", str(VENV_DIR)], check=True, **_subprocess_flags())
    py = str(venv_python())
    log("[启动器] 正在升级 pip ...")
    subprocess.run([py, "-m", "pip", "install", "--upgrade", "pip"], check=True, **_subprocess_flags())
    log("[启动器] 正在安装基础依赖 ...")
    subprocess.run([py, "-m", "pip", "install", *BASE_REQUIREMENTS], check=True, **_subprocess_flags())
    log(f"[启动器] 即将下载并安装 PyTorch（{_deps_size_text()}），首次较慢，请保持网络畅通 ...")
    torch_cmd = [py, "-m", "pip", "install", *TORCH_REQUIREMENTS]
    if not _is_macos():
        torch_cmd += ["--index-url", CUDA_INDEX_URL]
    subprocess.run(torch_cmd, check=True, **_subprocess_flags())
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
        **_subprocess_flags(),
    )


# —————————————————————————————————————————————
# 图形界面
# —————————————————————————————————————————————

def run_gui(config: dict) -> None:
    import tkinter as tk
    from tkinter import scrolledtext, messagebox, ttk

    # 调色板（清爽现代，浅色）
    C_BG    = "#f5f8fc"   # 窗口底
    C_BRAND = "#2563eb"   # 品牌蓝头部
    C_SKY   = "#0ea5e9"   # 主按钮
    C_SKY_H = "#0284c7"
    C_GREY  = "#e2e8f0"   # 次要按钮
    C_TEXT  = "#0f172a"
    C_MUTED = "#64748b"
    F = "Microsoft YaHei"

    root = tk.Tk()
    root.title("VisualDL 本机训练应用")
    root.geometry("700x620")
    root.minsize(660, 560)
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

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("VDL.Horizontal.TProgressbar", troughcolor=C_GREY,
                    background=C_SKY, bordercolor=C_GREY, thickness=6)

    # —— 头部色带：图标 + 标题 ——
    header = tk.Frame(root, bg=C_BRAND)
    header.pack(fill="x")
    hpad = tk.Frame(header, bg=C_BRAND)
    hpad.pack(fill="x", padx=24, pady=16)
    if _imgs:
        small = _imgs[0].subsample(max(1, _imgs[0].width() // 44))
        _imgs.append(small)
        tk.Label(hpad, image=small, bg=C_BRAND).pack(side="left")
    tbox = tk.Frame(hpad, bg=C_BRAND)
    tbox.pack(side="left", padx=12)
    tk.Label(tbox, text="VisualDL 本机训练应用", font=(F, 16, "bold"),
             fg="white", bg=C_BRAND).pack(anchor="w")
    tk.Label(tbox, text="训练在你自己的电脑上进行 · 无需安装 Python", font=(F, 9),
             fg="#c7d7fe", bg=C_BRAND).pack(anchor="w")

    body = tk.Frame(root, bg=C_BG)
    body.pack(fill="both", expand=True, padx=24, pady=(16, 18))

    # —— 状态横幅（大字、随状态变色）+ 进度条 ——
    banner = tk.Frame(body, bg="#eef2ff")
    banner.pack(fill="x")
    status_var = tk.StringVar(value="")
    status_lbl = tk.Label(banner, textvariable=status_var, font=(F, 11, "bold"),
                          fg=C_TEXT, bg="#eef2ff", anchor="w", justify="left", wraplength=620)
    status_lbl.pack(fill="x", padx=14, pady=11)
    progress = ttk.Progressbar(body, style="VDL.Horizontal.TProgressbar", mode="indeterminate")

    # —— 步骤①：登录令牌 ——
    tk.Label(body, text="① 粘贴登录令牌", font=(F, 11, "bold"), fg=C_TEXT, bg=C_BG).pack(anchor="w", pady=(16, 2))
    tk.Label(body, text="在网页「本机训练应用」弹窗里复制令牌，粘到下面（失效时也在这里更新，无需改任何文件）",
             font=(F, 9), fg=C_MUTED, bg=C_BG, wraplength=640, justify="left").pack(anchor="w")
    token_var = tk.StringVar(value=config.get("token", ""))
    token_entry = tk.Entry(body, textvariable=token_var, font=("Consolas", 10), show="•",
                           relief="solid", bd=1)
    token_entry.pack(fill="x", pady=(6, 2), ipady=6)
    tokrow = tk.Frame(body, bg=C_BG)
    tokrow.pack(fill="x")
    show_var = tk.BooleanVar(value=False)
    tk.Checkbutton(tokrow, text="显示令牌", variable=show_var,
                   command=lambda: token_entry.config(show="" if show_var.get() else "•"),
                   font=(F, 9), fg=C_MUTED, bg=C_BG, activebackground=C_BG,
                   selectcolor="white", bd=0, cursor="hand2").pack(side="left")
    save_btn = tk.Button(tokrow, text="保存令牌", font=(F, 9), relief="flat",
                         bg=C_GREY, fg=C_TEXT, activebackground="#cbd5e1",
                         cursor="hand2", padx=14, pady=5)
    save_btn.pack(side="right")

    # —— 步骤②③：两个大按钮 ——
    tk.Label(body, text="② 准备训练环境　③ 启动并连接", font=(F, 11, "bold"),
             fg=C_TEXT, bg=C_BG).pack(anchor="w", pady=(16, 5))
    btns = tk.Frame(body, bg=C_BG)
    btns.pack(fill="x")
    prepare_btn = tk.Button(btns, text="", font=(F, 11, "bold"),
                            bg=C_GREY, fg=C_TEXT, activebackground="#cbd5e1",
                            relief="flat", cursor="hand2", pady=13, disabledforeground="#94a3b8")
    prepare_btn.pack(side="left", fill="x", expand=True)
    connect_btn = tk.Button(btns, text="③ 启动并连接云端", font=(F, 12, "bold"),
                            bg=C_SKY, fg="white", activebackground=C_SKY_H,
                            activeforeground="white", relief="flat", cursor="hand2", pady=13,
                            disabledforeground="#e0f2fe")
    connect_btn.pack(side="left", fill="x", expand=True, padx=(12, 0))

    # —— 高级设置（可折叠）：服务器地址 ——
    adv = {"open": False}
    adv_toggle = tk.Label(body, text="⚙ 高级设置 ▼", font=(F, 9), fg=C_MUTED, bg=C_BG, cursor="hand2")
    adv_toggle.pack(anchor="w", pady=(16, 0))
    adv_box = tk.Frame(body, bg=C_BG)
    tk.Label(adv_box, text="服务器地址（一般无需修改）", font=(F, 9), fg=C_MUTED, bg=C_BG).pack(anchor="w", pady=(6, 2))
    server_var = tk.StringVar(value=config.get("server_url", DEFAULT_SERVER))
    tk.Entry(adv_box, textvariable=server_var, font=("Consolas", 9), relief="solid", bd=1).pack(fill="x", ipady=4)

    def _toggle_adv(*_):
        adv["open"] = not adv["open"]
        if adv["open"]:
            adv_box.pack(fill="x", after=adv_toggle)
            adv_toggle.config(text="⚙ 高级设置 ▲")
        else:
            adv_box.pack_forget()
            adv_toggle.config(text="⚙ 高级设置 ▼")
    adv_toggle.bind("<Button-1>", _toggle_adv)

    # —— 详细日志（可折叠，默认收起，避免吓到新手）——
    logstate = {"open": False}
    log_toggle = tk.Label(body, text="📄 查看详细日志 ▼", font=(F, 9), fg=C_MUTED, bg=C_BG, cursor="hand2")
    log_toggle.pack(anchor="w", pady=(8, 0))
    log_widget = scrolledtext.ScrolledText(body, height=8, font=("Consolas", 9),
                                           bg="#0f172a", fg="#cbd5e1", relief="flat", state="disabled")

    def _toggle_log(*_):
        logstate["open"] = not logstate["open"]
        if logstate["open"]:
            log_widget.pack(fill="both", expand=True, pady=(6, 0))
            log_toggle.config(text="📄 收起详细日志 ▲")
            root.geometry("700x800")
        else:
            log_widget.pack_forget()
            log_toggle.config(text="📄 查看详细日志 ▼")
            root.geometry("700x620")
    log_toggle.bind("<Button-1>", _toggle_log)

    # —— 状态 / 进度 / 按钮 helpers ——
    _BANNER = {
        "idle": ("#eef2ff", "#3730a3"),
        "busy": ("#e0f2fe", "#075985"),
        "ok":   ("#dcfce7", "#166534"),
        "err":  ("#fee2e2", "#991b1b"),
    }

    def _apply_banner(text, kind):
        bg, fg = _BANNER.get(kind, _BANNER["idle"])
        status_var.set(text)
        banner.config(bg=bg)
        status_lbl.config(bg=bg, fg=fg)
        if kind == "busy":
            if not progress.winfo_ismapped():
                progress.pack(fill="x", pady=(10, 0), after=banner)
            progress.start(12)
        else:
            progress.stop()
            if progress.winfo_ismapped():
                progress.pack_forget()

    def set_banner(text, kind="idle"):
        root.after(0, lambda: _apply_banner(text, kind))

    def _auto_kind(text):
        if text.startswith("✅"):
            return "ok"
        if text.startswith("❌") or "失败" in text:
            return "err"
        if "正在" in text or text.rstrip().endswith("..."):
            return "busy"
        return "idle"

    def set_status(text: str) -> None:
        set_banner(text, _auto_kind(text))

    def log(msg: str) -> None:
        def _do():
            log_widget.configure(state="normal")
            log_widget.insert("end", msg + "\n")
            log_widget.see("end")
            log_widget.configure(state="disabled")
        root.after(0, _do)
        # 把启动器的关键进度也映射到横幅，让收起日志的新手也能看到进展
        if msg.startswith("[启动器]"):
            set_banner(msg.replace("[启动器]", "").strip(), "busy")

    def _style_btn(btn, text: str, enabled: bool, primary: bool = False) -> None:
        """primary=当前该点的主操作→蓝色醒目；enabled=False→灰显不可点。"""
        if enabled and primary:
            cfg = dict(bg=C_SKY, fg="white", activebackground=C_SKY_H, state="normal", cursor="hand2")
        elif enabled:
            cfg = dict(bg=C_GREY, fg=C_TEXT, activebackground="#cbd5e1", state="normal", cursor="hand2")
        else:
            cfg = dict(bg="#eaeef3", fg="#9aa7b8", state="disabled", cursor="arrow")
        cfg["text"] = text
        root.after(0, lambda: btn.config(**cfg))

    def refresh_idle() -> None:
        """按状态高亮「当前该点」的按钮为蓝色主按钮，另一个灰显。"""
        if ui["busy"] or ui["connected"]:
            return
        ready = is_venv_ready()
        has_token = bool(token_var.get().strip())
        if ready and has_token:
            _style_btn(prepare_btn, "② 训练环境已就绪 ✓", False)
            _style_btn(connect_btn, "③ 启动并连接云端", True, primary=True)
            set_banner("环境已就绪！点下方「③ 启动并连接云端」即可开始。", "ok")
        elif ready:
            _style_btn(prepare_btn, "② 训练环境已就绪 ✓", False)
            _style_btn(connect_btn, "③ 请先粘贴令牌", False)
            set_banner("环境已就绪，请先在 ① 粘贴登录令牌。", "idle")
        else:
            _style_btn(prepare_btn, f"② 准备训练环境（首次下载 {_deps_size_text()}）", True, primary=True)
            _style_btn(connect_btn, "③ 启动并连接云端", False)
            set_banner(f"第一步：点「② 准备训练环境」下载依赖（约 {_deps_size_text()}，含 PyTorch，只需一次）。", "idle")

    def on_save() -> None:
        t = token_var.get().strip()
        s = server_var.get().strip() or DEFAULT_SERVER
        if not t:
            messagebox.showwarning("提示", "请先粘贴令牌。")
            return
        save_config(s, t)
        log("[启动器] 令牌已保存到本应用（无需外部配置文件）。")
        set_banner("令牌已保存。", "ok")
        root.after(1200, refresh_idle)

    def prepare_worker() -> None:
        try:
            set_status("正在准备训练环境（首次较慢，请保持网络畅通）...")
            create_environment(log=log)
            set_banner("✅ 训练环境准备完成，现在可以「③ 启动并连接云端」了。", "ok")
        except Exception as exc:  # noqa: BLE001
            log(f"[启动器] 环境准备失败：{exc}")
            set_banner("环境准备失败，请检查网络后重试。", "err")
        ui["busy"] = False
        root.after(1500, refresh_idle)

    def on_prepare() -> None:
        if ui["busy"] or is_venv_ready():
            return
        save_config(server_var.get().strip() or DEFAULT_SERVER, token_var.get().strip())
        ui["busy"] = True
        _style_btn(prepare_btn, "正在下载安装 ...", False)
        _style_btn(connect_btn, "请稍候 ...", False)
        threading.Thread(target=prepare_worker, daemon=True).start()

    def connect_worker() -> None:
        s = server_var.get().strip() or DEFAULT_SERVER
        t = token_var.get().strip()
        save_config(s, t)
        set_status("正在连接云端 ...")
        try:
            proc = start_agent_process(s, t)
        except Exception as exc:  # noqa: BLE001
            log(f"[启动器] 启动失败：{exc}")
            ui["busy"] = False
            set_banner("启动失败，请重试。", "err")
            root.after(1200, refresh_idle)
            return
        ui["proc"] = proc
        for line in proc.stdout:
            line = line.rstrip()
            log(line)
            if "CONNECTED" in line or "已成功连接" in line:
                ui["connected"] = True
                set_banner("✅ 已连接云端！回到网页即可开始训练。", "ok")
                _style_btn(prepare_btn, "② 训练环境已就绪 ✓", False)
                root.after(0, lambda: connect_btn.config(
                    text="● 已连接云端", state="disabled", bg="#16a34a",
                    fg="white", disabledforeground="white", cursor="arrow"))
            elif "403" in line:
                ui["connected"] = False
                set_banner("❌ 令牌无效/已失效：请在 ① 更新令牌后点「保存令牌」再启动。", "err")
        ui["busy"] = False
        ui["connected"] = False
        set_banner("连接已结束。", "idle")
        root.after(400, refresh_idle)

    def on_connect() -> None:
        if ui["busy"]:
            return
        if not token_var.get().strip():
            messagebox.showwarning("提示", "请先粘贴令牌。")
            return
        if not is_venv_ready():
            messagebox.showinfo("提示", "请先点「② 准备训练环境」下载依赖。")
            return
        ui["busy"] = True
        _style_btn(connect_btn, "连接中 ...", False)
        threading.Thread(target=connect_worker, daemon=True).start()

    prepare_btn.config(command=on_prepare)
    connect_btn.config(command=on_connect)
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
