# 本机训练应用产物发布目录

`GET /agent/download` 会优先从这里发放**已构建好的本机训练应用**（按用户平台）。
本目录下的产物**不入库**（体积大、分平台），由部署时放入。目录位置可用环境变量
`AGENT_DIST_DIR` 覆盖，默认即本目录（`backend/agent_dist`）。

## 目录约定

按平台分子目录放置各自构建好的产物：

```
agent_dist/
  windows/VisualDL-Agent.exe        # Windows 构建产物
  macos/VisualDL-Agent-mac.zip      # macOS 的 .app 是目录包，先自行 zip
  linux/VisualDL-Agent              # Linux 可执行文件
  manifest.json                     # 可选，见下
```

也可用 `manifest.json` 显式指定版本与各平台产物路径（优先于子目录扫描）：

```json
{
  "version": "1.0.0",
  "artifacts": {
    "windows": "windows/VisualDL-Agent.exe",
    "macos": "macos/VisualDL-Agent-mac.zip",
    "linux": "linux/VisualDL-Agent"
  }
}
```

若某平台没有放产物，`/agent/download` 会**自动回退**为发放「启动器源码 + .pyc +
构建指引」压缩包（供开发或自行打包），因此缺产物不会导致下载失败。

## 如何生成产物

在**与目标平台相同的系统**上，按下载包里的 `build_app.md`（PyInstaller 冻结
`launcher.py` + 内置独立 Python）构建，得到单文件应用后放入对应子目录即可。

## 令牌如何注入（无需为每个用户重新构建）

产物是**通用的、不含令牌**，只需构建一次。下载时服务器会把该用户令牌写进一个
`config.json`，与产物一起打包下发；启动器运行时从应用所在目录读取 `config.json`
完成账号绑定。所以更新令牌逻辑无需重新构建应用。
