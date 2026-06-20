# SearXNG Windows for OpenClaw

Native Windows deployment scripts for running a local SearXNG instance behind OpenClaw.

This repository packages the practical Windows setup:

- standard Python + venv, no Docker required
- local-only SearXNG at `http://127.0.0.1:8888`
- proxy-aware outbound search traffic
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

## Quick Start

1. Install or provide Python 3.11/3.12 x64.
2. Copy `config/settings.example.yml` to your deployment config path as `config/settings.yml`.
3. Replace `CHANGE_ME_GENERATE_WITH_SECRETS_TOKEN_URLSAFE` with a generated secret:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

4. Install:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -Root E:\openclaw\searxng_windows -RuntimePython E:\openclaw\runtime\python\python.exe
```

5. Start and check:

```powershell
powershell -ExecutionPolicy Bypass -File E:\openclaw\searxng_windows\scripts\start.ps1
powershell -ExecutionPolicy Bypass -File E:\openclaw\searxng_windows\scripts\check.ps1
```

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

The `run.ps1` script also sets standard proxy environment variables.

## Engine Notes

SearXNG queries engines concurrently. One failing engine should not block other engines from returning results; failures appear in `unresponsive_engines`.

DuckDuckGo can hit CAPTCHA frequently behind shared/proxied traffic, so this setup disables DuckDuckGo variants by default. Brave in SearXNG scrapes `search.brave.com` HTML and does not use the official Brave API key; it can still be rate-limited.

## Startup

Register Windows logon startup:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-startup-task.ps1 -Root E:\openclaw\searxng_windows
```

The task name is `OpenClaw SearXNG`.
