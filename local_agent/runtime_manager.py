"""本机 Agent 的训练运行时下载与版本管理。"""

from pathlib import Path
from typing import Any


def get_installed_runtime_version(runtime_root: Path) -> str | None:
    """读取本机已安装的 trainer-runtime 版本。

    TODO：实现对 runtime_root 下 runtime_manifest.json 的读取。

    参数：
        runtime_root：保存各版本训练运行时的本地目录。

    返回：
        已安装的版本号字符串；如果尚未安装，则返回 None。
    """
    raise NotImplementedError("TODO：读取本机训练运行时版本")


def fetch_runtime_manifest(server_url: str, auth_token: str) -> dict[str, Any]:
    """从云端服务器获取最新兼容的训练运行时元信息。

    TODO：实现对云端 runtime manifest 接口的 HTTPS 请求。

    参数：
        server_url：云端服务器基础地址。
        auth_token：用于请求运行时元信息的身份令牌。

    返回：
        dict，包含 version、download_url、sha256、size_bytes、
        min_agent_version、release_notes 和可选的签名信息。
    """
    raise NotImplementedError("TODO：获取训练运行时元信息")


def download_runtime_package(download_url: str, target_file: Path, expected_sha256: str) -> Path:
    """下载 trainer-runtime 压缩包到本机。

    TODO：实现流式下载、必要时的断点续传，以及下载后的 SHA-256 校验。

    参数：
        download_url：trainer-runtime zip 包的 HTTPS 下载地址。
        target_file：zip 包保存到本机的目标路径。
        expected_sha256：云端 manifest 提供的期望 SHA-256 值。

    返回：
        Path，表示已经下载并通过校验的 zip 包路径。
    """
    raise NotImplementedError("TODO：下载训练运行时压缩包")


def install_runtime_package(package_file: Path, runtime_root: Path, version: str) -> Path:
    """安装已下载的 trainer-runtime 压缩包。

    TODO：实现 zip 解压、版本目录创建、文件校验和本地元信息写入。

    参数：
        package_file：已经下载并校验通过的 trainer-runtime zip 文件。
        runtime_root：保存运行时版本的本地根目录。
        version：本次安装的运行时版本号，例如 "1.0.0"。

    返回：
        Path，表示安装后的运行时版本目录。
    """
    raise NotImplementedError("TODO：安装训练运行时压缩包")


def ensure_runtime_ready(server_url: str, auth_token: str, runtime_root: Path) -> dict[str, Any]:
    """确保本机已经安装可用的训练运行时。

    TODO：实现版本比较、manifest 获取、运行时下载、安装和失败回滚。

    参数：
        server_url：云端服务器基础地址。
        auth_token：用于请求运行时元信息和下载包的身份令牌。
        runtime_root：保存本机运行时版本的目录。

    返回：
        dict，包含 ready、version、runtime_path、updated 和 message。
    """
    raise NotImplementedError("TODO：确保本机训练运行时可用")
