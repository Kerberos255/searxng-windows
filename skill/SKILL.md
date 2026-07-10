---
name: searxng
description: Use when Codex needs to operate, diagnose, maintain, or query a local Windows SearXNG deployment for OpenClaw, including web search via the local JSON API, start/stop/update scripts, proxy troubleshooting, OpenClaw integration, engine enable/disable decisions, and startup task management.
---

# Local SearXNG for OpenClaw

This skill covers the local Windows SearXNG instance deployed for OpenClaw.

## Path Conventions

- Deployment root: `<deploy-root>`
- Source: `<deploy-root>\searxng`
- Virtualenv Python: `<deploy-root>\.venv\Scripts\python.exe`
- SearXNG config: `<deploy-root>\config\settings.yml`
- OpenClaw config: `<openclaw-home>\.openclaw\openclaw.json`
- OpenClaw launcher: `<openclaw-home>\openclaw.cmd`
- Normal SearXNG backend/UI: `http://127.0.0.1:8888`
- Optional API Pool gateway: `http://127.0.0.1:8890`
- Optional example local proxy for outbound search-engine traffic: `http://127.0.0.1:10808`

## Core Commands

Use these scripts instead of launching `searx\webapp.py` manually:

```powershell
powershell -ExecutionPolicy Bypass -File <deploy-root>\scripts\start.ps1
powershell -ExecutionPolicy Bypass -File <deploy-root>\scripts\stop.ps1
powershell -ExecutionPolicy Bypass -File <deploy-root>\scripts\update.ps1
powershell -ExecutionPolicy Bypass -File <deploy-root>\scripts\check.ps1
```

Proxy is disabled by default. If direct search-engine access times out, pass `-ProxyUrl "http://127.0.0.1:10808"` to `start.ps1` or `run.ps1`, and uncomment the `outgoing.proxies` block in `config\settings.yml`.

Use `scripts/search.py` in this skill for quick JSON/table search checks. It uses ordinary SearXNG on `8888` by default; set `SEARXNG_URL` to `8890` only when the API Pool is enabled:

```powershell
$env:SEARXNG_URL='http://127.0.0.1:8888'
python <skill-root>\scripts\search.py search "openai" --format json -n 3
```

## Current Deployment Facts

- Installed from the official GitHub source zip because `git clone/fetch` timed out.
- SearXNG is installed editable into the venv with `pip install --no-build-isolation -e .`.
- A Windows compatibility patch is applied to `searx\valkeydb.py` because upstream imports Unix-only `pwd`.
- The `update.ps1` script stops SearXNG if running, updates source/dependencies, reapplies the Windows patch, and restarts if it was running.
- A Windows Scheduled Task named `OpenClaw SearXNG` starts SearXNG at user logon via `scripts\start-hidden.vbs`.

## OpenClaw Integration

OpenClaw should use local SearXNG through:

```json
"tools": {
  "web": {
    "search": {
      "provider": "searxng",
      "enabled": true,
      "maxResults": 10,
      "timeoutSeconds": 30
    }
  }
}
```

Use port `8888` in the plugin config by default:

```json
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
```

The OpenClaw launcher should also use port `8888` by default:

```cmd
set "SEARXNG_URL=http://127.0.0.1:8888"
set "SEARXNG_BASE_URL=http://127.0.0.1:8888"
```

Only when `config\settings.yml` enables the `api pool` engine should all three URLs be changed to `http://127.0.0.1:8890`. Restart OpenClaw Gateway after configuration changes:

```powershell
<openclaw-home>\restart-openclaw.cmd
```

## Search Behavior

With the API Pool disabled, the Broker is not started and OpenClaw should query ordinary SearXNG directly on port `8888`.

With the API Pool enabled, OpenClaw may query the API-first gateway on port `8890`. It tries `Parallel -> Tavily -> Brave -> Firecrawl` serially and returns the first non-empty result set. Only when every API provider is unavailable or empty does it query the free Bing/Sogou/Qwant/Mojeek engines through SearXNG on port `8888`.

The gateway accepts `time_range` (`day`, `week`, `month`, `year`) plus exact `date_after` and `date_before` values in `YYYY-MM-DD` format. Direct SearXNG supports only the coarse `time_range` values. Parallel supports only the lower date bound, so requests containing `date_before` skip it and continue with Tavily.

DuckDuckGo is disabled locally because it frequently returned CAPTCHA. Current disabled overrides include:

```yaml
engines:
  - name: duckduckgo
    disabled: true
  - name: duckduckgo images
    disabled: true
  - name: duckduckgo videos
    disabled: true
  - name: duckduckgo news
    disabled: true
```

Brave in SearXNG does not use the official Brave API. It scrapes `https://search.brave.com/` HTML and therefore requires no API key, but can be rate-limited. OpenClaw's native `brave` provider is different and requires `OPENCLAW_BRAVE_API_KEY`.

## Diagnostics Workflow

1. Check local API health:

```powershell
powershell -ExecutionPolicy Bypass -File <deploy-root>\scripts\check.ps1
```

2. Confirm actual results, not only HTTP 200. Use `8888` normally and `8890` only while the API Pool is enabled:

```powershell
$SearchUrl = 'http://127.0.0.1:8888'
$r = Invoke-WebRequest -Uri "$SearchUrl/search?q=openai&format=json&count=5" -UseBasicParsing -TimeoutSec 80
$j = $r.Content | ConvertFrom-Json
$j.results.Count
$j.provider
$j.fallback_used
```

3. Inspect logs:

```powershell
Get-Content <deploy-root>\searxng-run.log -Tail 80
Get-Content <deploy-root>\searxng-run.err.log -Tail 120
```

4. Confirm listener and process:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8888,8890
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*searxng_windows*' -or $_.CommandLine -like '*searx\webapp.py*' }
```

5. If OpenClaw cannot search but the local API works, verify that `openclaw.json`, `SEARXNG_URL`, and `SEARXNG_BASE_URL` point to `8888` when the API Pool is disabled or `8890` when it is enabled, then restart the gateway.

## References

Read `references/deployment.md` when changing deployment, startup, update behavior, proxy settings, engine counts, or troubleshooting details.
