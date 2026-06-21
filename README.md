# SearXNG Windows for OpenClaw

English | [简体中文](README.zh-CN.md)

Native Windows deployment scripts for running a local SearXNG instance behind OpenClaw.

This repository packages the practical Windows setup:

- standard Python + venv, no Docker required
- local-only SearXNG at `http://127.0.0.1:8888`
- optional proxy-aware outbound search traffic
- start, stop, update, check, and logon startup scripts
- OpenClaw skill and config notes
- Windows compatibility patch for SearXNG's Unix-only `pwd` import path

## What This Repo Does Not Include

This repo intentionally does not include:

- a Python virtual environment
- a copied SearXNG source tree
- logs, PID files, or downloaded source zips
- real `settings.yml` secrets
- private OpenClaw config files

## Quick Start for Normal Users

1. Install Python 3.11 or 3.12 x64.
2. Download `install-searxng-windows.cmd` and `install-searxng-windows.ps1` from the latest release into the same folder.
3. Double-click `install-searxng-windows.cmd`.
4. Start and check SearXNG:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Apps\searxng-windows\scripts\start.ps1"
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Apps\searxng-windows\scripts\check.ps1"
```

Open:

```text
http://127.0.0.1:8888
```

The default deployment root is `$env:USERPROFILE\Apps\searxng-windows`.

## Advanced Install From a Git Clone

1. Copy `config/settings.example.yml` to your deployment config path as `config/settings.yml`.
2. Replace `CHANGE_ME_GENERATE_WITH_SECRETS_TOKEN_URLSAFE` with a generated secret:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

3. Install:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -Root "$env:USERPROFILE\Apps\searxng-windows"
```

If Python is not available as `python` in `PATH`, pass a full Python path with `-RuntimePython`.

## Bootstrap Installer

Normal users can double-click `install-searxng-windows.cmd`. Advanced users can review and run `install-searxng-windows.ps1` directly in PowerShell.

The bootstrap installer downloads this repository's release source archive, then runs `scripts\install.ps1`. That script downloads upstream SearXNG during installation. This repository does not bundle SearXNG, Python, a venv, or patched SearXNG source.

## OpenClaw Integration

Set OpenClaw web search provider to `searxng`, and configure:

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

Also set this in the OpenClaw launcher environment:

```cmd
set "SEARXNG_URL=http://127.0.0.1:8888"
```

Restart OpenClaw after config changes.

## Proxy Notes

If direct outbound access to search engines times out, configure SearXNG outbound proxy in `settings.yml`:

```yaml
outgoing:
  request_timeout: 10.0
  max_request_timeout: 20.0
  extra_proxy_timeout: 10
  proxies:
    all://:
      - http://127.0.0.1:10808
```

The `run.ps1` script can also set standard proxy environment variables. Proxy is disabled by default. Change `127.0.0.1:10808` to match your local proxy, then start with:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Apps\searxng-windows\scripts\start.ps1" -ProxyUrl "http://127.0.0.1:10808"
```

## Engine Notes

SearXNG queries engines concurrently. One failing engine should not block other engines from returning results; failures appear in `unresponsive_engines`.

DuckDuckGo can hit CAPTCHA frequently behind shared/proxied traffic, so this setup disables DuckDuckGo variants by default. Brave in SearXNG scrapes `search.brave.com` HTML and does not use the official Brave API key; it can still be rate-limited.

## Startup

Register Windows logon startup:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-startup-task.ps1 -Root "$env:USERPROFILE\Apps\searxng-windows"
```

The task name is `OpenClaw SearXNG`.

## CI

GitHub Actions validates PowerShell script syntax and Python helper syntax on push and pull requests.

## License Notes

This repository's deployment scripts and documentation are MIT licensed.

SearXNG itself is not included in this repository. The install scripts download SearXNG from the upstream project, which is licensed under AGPL-3.0-or-later. The Windows compatibility patch is applied locally to the downloaded SearXNG source tree during installation/update. This repository does not redistribute the patched SearXNG source.

Any distribution that bundles SearXNG source code or modified SearXNG files must comply with SearXNG's upstream license.
