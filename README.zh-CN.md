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

## 仓库不包含什么

这个仓库只保存脚本和模板，不包含：

- Python 虚拟环境
- SearXNG 源码副本
- 日志、PID 文件、下载的源码 zip
- 真实 `settings.yml` 里的密钥
- 私有 OpenClaw 配置

## 快速开始

1. 安装或准备 Python 3.11/3.12 x64。
2. 把 `config/settings.example.yml` 复制到部署目录的 `config/settings.yml`。
3. 把 `CHANGE_ME_GENERATE_WITH_SECRETS_TOKEN_URLSAFE` 替换成随机 secret：

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

4. 选择部署目录。下面示例使用 `$env:USERPROFILE\Apps\searxng-windows`。

5. 安装：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -Root "$env:USERPROFILE\Apps\searxng-windows" -RuntimePython "<python.exe>"
```

6. 启动并检查：

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Apps\searxng-windows\scripts\start.ps1"
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Apps\searxng-windows\scripts\check.ps1"
```

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

## 搜索引擎说明

SearXNG 会并发请求多个搜索引擎。某一个引擎验证码、限流或超时，通常不会阻止其他引擎返回结果；失败的引擎会出现在 `unresponsive_engines`。

这个模板默认禁用了 DuckDuckGo 系列，因为在代理或共享出口下它比较容易触发验证码。SearXNG 里的 Brave 引擎抓取的是 `search.brave.com` 网页结果，不使用 Brave 官方 API key，但也可能被限流。

## 开机启动

注册 Windows 登录自启动：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-startup-task.ps1 -Root "$env:USERPROFILE\Apps\searxng-windows"
```

计划任务名称是 `OpenClaw SearXNG`。

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

本仓库不包含 SearXNG 本身。安装脚本会从上游 SearXNG 项目下载源码，SearXNG 的上游许可证是 AGPL-3.0-or-later。如果分发包含 SearXNG 源码或修改过的 SearXNG 文件的整包，需要遵守 SearXNG 的上游许可证。
