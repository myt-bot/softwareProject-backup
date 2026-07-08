#!/usr/bin/env python3
"""把「本机训练应用」的组成文件打包成规范的分发 zip。

产物结构（用户解压后得到干净的单一文件夹）：
    VisualDL-Agent.zip
      └─ VisualDL-Agent/
           ├─ python/            独立 CPython（需自行放好，见 build_app.md）
           ├─ local_agent/       编译后的 .pyc
           ├─ launcher.py
           ├─ 启动.bat / 启动.command
           └─ README.txt
自动剔除：build_app.md（仅分发者看）、config.json（避免泄露令牌）、
          __pycache__ 与 visualdl_runtime（运行期缓存/产物）。

用法（只用标准库，Windows / macOS / Linux 通用）：
    # 1) 规范化一个已有的 zip（比如之前打得比较随意的包）
    python tools/assemble_bundle.py --from-zip 旧包.zip -o VisualDL-Agent.zip

    # 2) 从一个已备好的文件夹组装（该文件夹里已有 python/、local_agent/、launcher.py …）
    python tools/assemble_bundle.py --src 某文件夹 -o VisualDL-Agent.zip
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

TOP = "VisualDL-Agent"
EXCLUDE_NAMES = {"build_app.md", "config.json"}          # 不进分发包


def _excluded(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    if parts[-1] in EXCLUDE_NAMES:
        return True
    if "visualdl_runtime" in parts:                       # 运行期产物（venv 等）
        return True
    # __pycache__：保留内置 python 自带的（加速首次启动），只剔除源码树里散落的缓存
    if "__pycache__" in parts and parts[0] != "python":
        return True
    return False


def _guess_mode(rel: str) -> int:
    low = rel.lower()
    if low.endswith((".exe", ".command", ".sh")) or "/bin/" in "/" + low:
        return 0o755
    return 0o644


def iter_from_dir(src: Path):
    for p in sorted(src.rglob("*")):
        if p.is_file():
            rel = p.relative_to(src).as_posix()
            if not _excluded(rel):
                mode = p.stat().st_mode & 0o777
                yield rel, p.read_bytes(), (mode or _guess_mode(rel))


def iter_from_zip(zpath: Path):
    with zipfile.ZipFile(zpath) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        # 若原 zip 已有统一外层文件夹，剥掉它，避免 VisualDL-Agent/VisualDL-Agent/
        tops = {n.split("/")[0] for n in names}
        strip = f"{next(iter(tops))}/" if len(tops) == 1 else ""
        for info in z.infolist():
            if info.is_dir():
                continue
            n = info.filename
            rel = n[len(strip):] if strip and n.startswith(strip) else n
            if not rel or _excluded(rel):
                continue
            orig = (info.external_attr >> 16) & 0o777
            yield rel, z.read(info), (orig or _guess_mode(rel))


def build(entries, out: Path) -> tuple[int, set[str]]:
    seen: set[str] = set()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, data, mode in entries:
            arc = f"{TOP}/{rel}"
            if arc in seen:
                continue
            seen.add(arc)
            info = zipfile.ZipInfo(arc)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (mode & 0o777) << 16
            zf.writestr(info, data)
    return len(seen), seen


def verify(members: set[str]) -> list[str]:
    """检查组装结果是否满足最低要求，返回警告列表（空则一切正常）。"""
    warn = []
    need_exact = [
        f"{TOP}/launcher.py",
        f"{TOP}/启动.bat",
        f"{TOP}/python/python.exe",
        f"{TOP}/python/pythonw.exe",
    ]
    for m in need_exact:
        if m not in members:
            warn.append(f"缺少 {m}")
    if not any(m.startswith(f"{TOP}/local_agent/") and m.endswith(".pyc") for m in members):
        warn.append("缺少 local_agent/*.pyc（Agent 代码）")
    if not any(m.startswith(f"{TOP}/python/") for m in members):
        warn.append("缺少 python/（独立 Python，用户将无法零安装运行）")
    if any(m == f"{TOP}/config.json" for m in members):
        warn.append("含 config.json（应剔除，避免泄露令牌）")
    return warn


def main() -> int:
    ap = argparse.ArgumentParser(description="打包规范的「本机训练应用」分发 zip")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--from-zip", type=Path, help="规范化一个已有的 zip")
    g.add_argument("--src", type=Path, help="从一个已备好的文件夹组装")
    ap.add_argument("-o", "--out", type=Path, default=Path("VisualDL-Agent.zip"), help="输出 zip 路径")
    args = ap.parse_args()

    if args.from_zip:
        if not args.from_zip.is_file():
            print(f"找不到输入 zip：{args.from_zip}", file=sys.stderr)
            return 2
        entries = iter_from_zip(args.from_zip)
    else:
        if not args.src.is_dir():
            print(f"找不到输入文件夹：{args.src}", file=sys.stderr)
            return 2
        entries = iter_from_dir(args.src)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    count, members = build(entries, args.out)
    size_mb = args.out.stat().st_size / 1024 / 1024
    print(f"✓ 已生成 {args.out}（{count} 个文件，{size_mb:.1f} MB），外层文件夹：{TOP}/")

    warns = verify(members)
    if warns:
        print("⚠ 注意：")
        for w in warns:
            print(f"   - {w}")
        return 1
    print("✓ 结构检查通过：含独立 Python、pythonw.exe、local_agent/.pyc，且不含 config.json。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
