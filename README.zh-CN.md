# SearXNG Windows for OpenClaw

[English](README.md) | 简体中文

这是一套面向 OpenClaw 的 Windows 原生 SearXNG 安装与维护工具。服务只在本机
运行，不需要 Docker。

## 主要功能

- 本地地址：`http://127.0.0.1:8888`
- 使用标准 Python 和虚拟环境
- 支持可选的出站代理
- 提供安装、启动、停止、更新、健康检查和登录自启动脚本
- 自动应用 SearXNG 所需的 Windows 兼容补丁
- 可选 API Pool，支持 Brave、Firecrawl、Tavily 和 Parallel
- API Key、本地状态、日志和生成配置都不会提交到 Git

## 系统要求

- Windows 10 或 Windows 11
- Python 3.11 或 3.12 x64
- 安装时可以访问互联网
- Git 可选；没有 Git 时安装器会改用源码 ZIP

## 快速安装

1. 从最新 GitHub Release 下载下面两个文件，并放在同一目录：
   - `install-searxng-windows.cmd`
   - `install-searxng-windows.ps1`
2. 双击 `install-searxng-windows.cmd`。
3. 启动 SearXNG 并运行健康检查：

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Apps\searxng-windows\scripts\start.ps1"
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Apps\searxng-windows\scripts\check.ps1"
```

4. 打开 `http://127.0.0.1:8888`。

默认安装目录：

```text
%USERPROFILE%\Apps\searxng-windows
```

bootstrap 安装器默认解析并下载最新 Release，再下载上游 SearXNG、创建虚拟
环境、安装依赖、生成本地 `secret_key`，并应用 Windows 补丁。已有的
`config/settings.yml` 和 `config/api-pool.env` 会被保留。

## OpenClaw 集成

默认把 OpenClaw 的网页搜索后端设置为 `8888` 端口上的普通 SearXNG：

```json
{
  "tools": {
    "web": {
      "search": {
        "provider": "searxng",
        "enabled": true,
        "maxResults": 10,
        "timeoutSeconds": 30
      }
    }
  },
  "plugins": {
    "entries": {
      "searxng": {
        "enabled": true,
        "config": {
          "webSearch": {
            "baseUrl": "http://127.0.0.1:8888",
            "language": "",
            "categories": "general"
          }
        }
      }
    }
  }
}
```

同时在 OpenClaw 启动环境中设置：

```cmd
set "SEARXNG_URL=http://127.0.0.1:8888"
set "SEARXNG_BASE_URL=http://127.0.0.1:8888"
```

修改后重启 OpenClaw。API Pool 未启用时保持使用 `8888`；启用下面的 API
Pool 后，再把上述三个 URL 改成 `8890`。

## 可选 API Pool

API Pool 会随安装包部署，但**默认关闭**。关闭时不会启动本地 Broker，普通
SearXNG 搜索引擎照常工作。

启用步骤：

1. 编辑 `%USERPROFILE%\Apps\searxng-windows\config\settings.yml`。
2. 把 `api pool` 条目的 `disabled: true` 改为 `disabled: false`。
3. 在 `config\api-pool.env` 中至少填写一个 Key：

```dotenv
BRAVE_API_KEY=
FIRECRAWL_API_KEY=
TAVILY_API_KEY=
PARALLEL_API_KEY=
API_POOL_PRIORITY=parallel,tavily,brave,firecrawl
```

4. 把 OpenClaw 的 `baseUrl`、`SEARXNG_URL` 和 `SEARXNG_BASE_URL` 从
   `8888` 改成 `8890`。
5. 重启 SearXNG 和 OpenClaw。

Broker 只在 API Pool 启用时启动，监听 `http://127.0.0.1:8890`，为 OpenClaw
提供兼容 SearXNG 的搜索入口，并按以下顺序执行：

```text
Parallel → Tavily → Brave → Firecrawl → Bing/Sogou/Qwant/Mojeek 免费兜底
```

第一家 API 返回有效结果后立即停止，不会让一次搜索同时消耗所有 API 的额度；
空结果会继续尝试下一家。只有全部 API 都不可用或都没有结果时，网关才会调用
`8888` 上的 Bing、Sogou、Qwant、Mojeek 免费层。API Pool 未启用时，OpenClaw 应继续连接
`8888`，直接使用普通 SearXNG。精确日期筛选使用 `date_after`、`date_before`
和 `YYYY-MM-DD` 格式。接口、状态机和故障切换说明见
[`api_pool/README.md`](api_pool/README.md)。

## 代理配置

默认不使用代理。如果出站搜索超时，可以编辑 `config/settings.yml`，启用示例
代理配置：

```yaml
outgoing:
  request_timeout: 10.0
  max_request_timeout: 20.0
  extra_proxy_timeout: 10
  proxies:
    all://:
      - http://127.0.0.1:10808
```

请替换成自己的代理地址。启动时也传入同一个代理，让 API Pool 和相关工具获得
标准代理环境变量：

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Apps\searxng-windows\scripts\start.ps1" -ProxyUrl "http://127.0.0.1:10808"
```

## 常用操作

```powershell
$Root = "$env:USERPROFILE\Apps\searxng-windows"

# 启动 SearXNG；API Pool 启用时也会启动 Broker
powershell -ExecutionPolicy Bypass -File "$Root\scripts\start.ps1"

# 停止本地服务
powershell -ExecutionPolicy Bypass -File "$Root\scripts\stop.ps1"

# 检查服务状态并执行一次测试搜索
powershell -ExecutionPolicy Bypass -File "$Root\scripts\check.ps1"

# 更新上游 SearXNG 源码和依赖
powershell -ExecutionPolicy Bypass -File "$Root\scripts\update.ps1"

# 注册 Windows 登录自启动
powershell -ExecutionPolicy Bypass -File "$Root\scripts\register-startup-task.ps1" -Root $Root
```

`update.ps1` 只更新上游 SearXNG。要更新本仓库的 Windows 脚本、API Pool 和配置
模板，请重新运行最新 Release 中的安装器；已有本地配置会被保留。

## 从 Git 仓库安装

```powershell
git clone https://github.com/Kerberos255/searxng-windows.git
cd searxng-windows
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -Root "$env:USERPROFILE\Apps\searxng-windows"
```

当 `config/settings.yml` 不存在时，安装脚本会自动创建它并生成本地 secret；不需
手工生成。系统 PATH 中没有 `python` 时，可用 `-RuntimePython` 指定完整路径。
需要固定某个版本时，bootstrap 安装器支持传入 `-Ref v0.2.0`。

## 故障排查

先运行 `scripts\check.ps1`。安装目录中的常用日志：

```text
searxng-run.log
searxng-run.err.log
broker-run.log
broker-run.err.log
```

- `8888` 是 SearXNG 端口；`8890` 是可选 API Pool Broker 端口。
- 某个搜索引擎失败时，通常不会阻止其他引擎返回结果。
- 模板默认禁用 DuckDuckGo 系列，因为共享出口或代理环境较容易触发验证码。
- SearXNG 自带的 Brave 引擎抓取公开网页结果，不使用官方 API Key；API Pool 中
  的 Brave provider 才使用官方 Key。

## 仓库边界

本仓库不会包含：

- Python 虚拟环境或 SearXNG 源码副本
- 生成后的 `config/settings.yml` 或真实 API Key
- `config/api-pool.env`、SQLite 状态、日志、PID 或下载文件
- 私有 OpenClaw 配置

## CI 与 Release

每次 push 和 pull request 都会运行 Windows CI：检查 PowerShell 语法、编译
Python、运行 API Pool 测试，并执行公开包防泄漏检查。

推送 `v0.2.0` 这类语义化版本标签后，会触发 Release 工作流。它会重新验证代码、
确认标签对应的提交属于 `main`、构建 ZIP 和 bootstrap 安装器、生成 SHA-256
校验文件，然后自动创建 GitHub Release。

## 许可证

部署脚本、独立 API Pool Broker 和文档使用 MIT 许可证。

SearXNG 从上游项目下载，使用 AGPL-3.0-or-later 许可证；小型
`patches/api_pool.py` 引擎适配器同样标注为 AGPL-3.0-or-later。分发包含
SearXNG 源码或修改文件的整包时，需要遵守其上游许可证。
