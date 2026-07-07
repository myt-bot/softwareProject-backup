"""本机 Agent 的训练运行时下载与版本管理。

首次使用该系统时，本机 Agent 需要从云端下载训练运行时（PyTorch 训练
代码）。本模块负责版本比较、下载、SHA-256 校验、解压安装和本地版本
记录，使用户「第一次使用即自动准备好训练环境」。
"""

import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Optional

_MANIFEST_NAME = "runtime_manifest.json"


def get_installed_runtime_version(runtime_root: Path) -> Optional[str]:
    """读取本机已安装的 trainer-runtime 版本。

    参数：
        runtime_root：保存各版本训练运行时的本地目录。

    返回：
        已安装的版本号字符串；如果尚未安装，则返回 None。
    """
    manifest_path = Path(runtime_root) / _MANIFEST_NAME
    if not manifest_path.exists():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return data.get("version")
    except (json.JSONDecodeError, OSError):
        return None


def fetch_runtime_manifest(server_url: str, auth_token: str) -> dict[str, Any]:
    """从云端服务器获取最新兼容的训练运行时元信息。

    参数：
        server_url：云端服务器基础地址，例如 http://127.0.0.1:8000。
        auth_token：用于请求运行时元信息的身份令牌。

    返回：
        dict，包含 version、download_url、sha256、size_bytes、
        min_agent_version、release_notes 等字段。
    """
    url = server_url.rstrip("/") + "/runtime/manifest"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {auth_token}"})
    with urllib.request.urlopen(req, timeout=30) as response:  # noqa: S310 (受信任的自建服务)
        return json.loads(response.read().decode("utf-8"))


def download_runtime_package(download_url: str, target_file: Path, expected_sha256: str) -> Path:
    """下载 trainer-runtime 压缩包到本机并做 SHA-256 校验。

    参数：
        download_url：trainer-runtime zip 包的完整下载地址。
        target_file：zip 包保存到本机的目标路径。
        expected_sha256：云端 manifest 提供的期望 SHA-256 值。

    返回：
        Path，表示已经下载并通过校验的 zip 包路径。
    """
    target_file = Path(target_file)
    target_file.parent.mkdir(parents=True, exist_ok=True)

    hasher = hashlib.sha256()
    with urllib.request.urlopen(download_url, timeout=120) as response, open(target_file, "wb") as out:  # noqa: S310
        while True:
            chunk = response.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
            out.write(chunk)

    actual = hasher.hexdigest()
    if expected_sha256 and actual != expected_sha256:
        target_file.unlink(missing_ok=True)
        raise ValueError(f"训练运行时校验失败：期望 {expected_sha256}，实际 {actual}")

    return target_file


def install_runtime_package(package_file: Path, runtime_root: Path, version: str) -> Path:
    """安装已下载的 trainer-runtime 压缩包。

    参数：
        package_file：已经下载并校验通过的 trainer-runtime zip 文件。
        runtime_root：保存运行时的本地根目录。
        version：本次安装的运行时版本号，例如 "1.0.0"。

    返回：
        Path，表示安装后的运行时目录（runtime_root/runtime）。
    """
    runtime_root = Path(runtime_root)
    runtime_root.mkdir(parents=True, exist_ok=True)

    # 清理旧的 runtime 目录后重新解压，保证是干净安装
    extracted_dir = runtime_root / "runtime"
    if extracted_dir.exists():
        shutil.rmtree(extracted_dir)

    with zipfile.ZipFile(package_file, "r") as archive:
        archive.extractall(runtime_root)

    manifest_path = runtime_root / _MANIFEST_NAME
    manifest_path.write_text(
        json.dumps({"version": version, "runtime_dir": str(extracted_dir)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return extracted_dir


def ensure_runtime_ready(server_url: str, auth_token: str, runtime_root: Path) -> dict[str, Any]:
    """确保本机已经安装可用的训练运行时。

    比较本机已安装版本与云端最新版本，必要时下载并安装。

    参数：
        server_url：云端服务器基础地址。
        auth_token：用于请求运行时元信息和下载包的身份令牌。
        runtime_root：保存本机运行时版本的目录。

    返回：
        dict，包含 ready、version、runtime_path、updated、message。
    """
    runtime_root = Path(runtime_root)
    installed = get_installed_runtime_version(runtime_root)

    try:
        manifest = fetch_runtime_manifest(server_url, auth_token)
    except Exception as exc:  # 云端不可达时，若本机已有运行时仍可离线使用
        if installed:
            return {
                "ready": True,
                "version": installed,
                "runtime_path": str(runtime_root / "runtime"),
                "updated": False,
                "message": f"无法连接云端获取运行时信息（{exc}），使用已安装版本 {installed}。",
            }
        return {"ready": False, "version": None, "runtime_path": None, "updated": False,
                "message": f"无法连接云端获取训练运行时：{exc}"}

    latest = manifest.get("version")
    if installed == latest:
        return {
            "ready": True,
            "version": installed,
            "runtime_path": str(runtime_root / "runtime"),
            "updated": False,
            "message": f"训练运行时已是最新版本 {installed}。",
        }

    # 需要下载/更新
    download_url = manifest.get("download_url", "")
    if download_url.startswith("/"):
        download_url = server_url.rstrip("/") + download_url

    package_file = runtime_root / f"trainer-runtime-{latest}.zip"
    try:
        download_runtime_package(download_url, package_file, manifest.get("sha256", ""))
        runtime_path = install_runtime_package(package_file, runtime_root, latest)
    except Exception as exc:
        return {"ready": bool(installed), "version": installed, "runtime_path": None,
                "updated": False, "message": f"训练运行时下载或安装失败：{exc}"}
    finally:
        package_file.unlink(missing_ok=True)

    return {
        "ready": True,
        "version": latest,
        "runtime_path": str(runtime_path),
        "updated": True,
        "message": f"训练运行时已更新到 {latest}。" if installed else f"训练运行时已首次安装（{latest}）。",
    }
