# SearXNG Windows for OpenClaw

[English](README.md) | 简体中文

这是一个面向 Windows 的本地 SearXNG 部署脚本包，用于让 OpenClaw 使用本机 SearXNG 作为网页搜索后端。

这个仓库整理的是一套实用的 Windows 原生部署方案：

- 使用标准 Python + venv，不需要 Docker
- 本地 SearXNG 地址：`http://127.0.0.1:8888`
- 可选配置 SearXNG 出站搜索代理
- 提供 start、stop、update、check 和登录自启动脚本
- 包含 OpenClaw skill 和配置说明
- 包含 SearXNG 在 Windows 上遇到 Unix-only `pwd` 导入问题时的兼容补丁
- 可选的串行 API Pool，支持 Brave、Firecrawl、Tavily 和 Parallel

## 仓库不包含什么

这个仓库只保存脚本和模板，不包含：

- Python 虚拟环境
- SearXNG 源码副本
- 日志、PID 文件、下载的源码 zip
- 真实 `settings.yml` 里的密钥
- 私有 OpenClaw 配置
- API Pool 真实密钥、本地 SQLite 状态或 `config/api-pool.env`

## 普通用户快速开始

1. 安装 Python 3.11 或 3.12 x64。
2. 从最新 Release 下载 `install-searxng-windows.cmd` 和 `install-searxng-windows.ps1`，并放在同一个文件夹里。
3. 双击 `install-searxng-windows.cmd`。
4. 启动并检查 SearXNG：

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Apps\searxng-windows\scripts\start.ps1"
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Apps\searxng-windows\scripts\check.ps1"
```

打开：

```text
http://127.0.0.1:8888
```

默认部署目录是 `$env:USERPROFILE\Apps\searxng-windows`。

## 从 Git 仓库高级安装

1. 把 `config/settings.example.yml` 复制到部署目录的 `config/settings.yml`。
2. 把 `CHANGE_ME_GENERATE_WITH_SECRETS_TOKEN_URLSAFE` 替换成随机 secret：

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

3. 安装：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -Root "$env:USERPROFILE\Apps\searxng-windows"
```

如果系统 PATH 里没有可用的 `python` 命令，可以用 `-RuntimePython` 传入完整 Python 路径。

## Bootstrap 安装器

普通用户可以双击 `install-searxng-windows.cmd`。高级用户可以先查看 `install-searxng-windows.ps1` 的内容，再在 PowerShell 里直接运行。

这个 bootstrap 安装器会下载本仓库的 Release 源码包，然后运行 `scripts\install.ps1`。后者会在安装过程中自动下载上游官方 SearXNG。本仓库不捆绑 SearXNG、Python、venv 或已打补丁的 SearXNG 源码。

## OpenClaw 集成

把 OpenClaw 的网页搜索 provider 设置成 `searxng`：

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

同时建议在 OpenClaw 启动环境里设置：

```cmd
set "SEARXNG_URL=http://127.0.0.1:8888"
```

修改配置后重启 OpenClaw。

## 代理说明

默认不启用代理。如果 SearXNG 直接访问搜索引擎超时，可以在 `settings.yml` 里取消注释代理配置：

```yaml
outgoing:
  request_timeout: 10.0
  max_request_timeout: 20.0
  extra_proxy_timeout: 10
  proxies:
    all://:
      - http://127.0.0.1:10808
```

然后用 `-ProxyUrl` 启动，让 `run.ps1` 同时设置常见代理环境变量：

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Apps\searxng-windows\scripts\start.ps1" -ProxyUrl "http://127.0.0.1:10808"
```

请把 `127.0.0.1:10808` 改成你的本地代理地址。

## 可选 API Pool

安装器会同时部署一个仅监听本机的 API Pool Broker：

```text
http://127.0.0.1:8890
```

SearXNG 只看到一个 `api pool` 引擎，Broker 默认按以下顺序串行尝试：

```text
Brave → Firecrawl → Tavily → Parallel
```

每次只使用第一家成功的 API。额度耗尽、临时限流、超时或服务故障时，
自动切换到下一家已配置的 provider。没有配置任何 Key 时，API Pool 返回
空结果，普通 SearXNG 免费网页引擎仍会照常工作。

编辑安装目录中的：

```text
%USERPROFILE%\Apps\searxng-windows\config\api-pool.env
```

可用变量：

```dotenv
BRAVE_API_KEY=
FIRECRAWL_API_KEY=
TAVILY_API_KEY=
PARALLEL_API_KEY=
API_POOL_PRIORITY=brave,firecrawl,tavily,parallel
```

真实 env 文件和 SQLite 状态都被 Git 忽略。详细状态机、接口和测试说明见
[`api_pool/README.md`](api_pool/README.md)。

## 搜索引擎说明

SearXNG 会并发请求多个搜索引擎。某一个引擎验证码、限流或超时，通常不会阻止其他引擎返回结果；失败的引擎会出现在 `unresponsive_engines`。

这个模板默认禁用了 DuckDuckGo 系列，因为在代理或共享出口下它比较容易触发验证码。SearXNG 里的 Brave 引擎抓取的是 `search.brave.com` 网页结果，不使用 Brave 官方 API key，但也可能被限流。

## 开机启动

注册 Windows 登录自启动：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-startup-task.ps1 -Root "$env:USERPROFILE\Apps\searxng-windows"
```

计划任务名称是 `OpenClaw SearXNG`。

## CI

GitHub Actions 会在 push 和 pull request 时检查 PowerShell 语法、编译全部 Python 文件，并运行使用 Mock 上游的 API Pool 测试。

## 常用命令

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Apps\searxng-windows\scripts\start.ps1"
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Apps\searxng-windows\scripts\stop.ps1"
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Apps\searxng-windows\scripts\update.ps1"
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Apps\searxng-windows\scripts\check.ps1"
```

## Skill

`skill/` 目录里包含一个可放入 OpenClaw/Codex skill 目录的 SearXNG skill，用于记录本地部署、诊断流程和搜索脚本。

## 许可证说明

本仓库的部署脚本和文档使用 MIT 许可证。

本仓库不包含 SearXNG 本身。安装脚本会从上游 SearXNG 项目下载源码，SearXNG 的上游许可证是 AGPL-3.0-or-later。Windows 兼容补丁和小型 `patches/api_pool.py` SearXNG 引擎适配器会在安装/更新时应用到用户本机下载的源码目录中。适配器标注为 AGPL-3.0-or-later；独立 Broker 与部署脚本仍使用 MIT 许可证。本仓库不重新分发完整的已修改 SearXNG 源码树。

如果分发包含 SearXNG 源码或修改过的 SearXNG 文件的整包，需要遵守 SearXNG 的上游许可证。
