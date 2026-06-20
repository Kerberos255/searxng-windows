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
- Local URL: `http://127.0.0.1:8888`
- Example local proxy for outbound search-engine traffic: `http://127.0.0.1:10808`

## Core Commands

Use these scripts instead of launching `searx\webapp.py` manually:

```powershell
powershell -ExecutionPolicy Bypass -File <deploy-root>\scripts\start.ps1
powershell -ExecutionPolicy Bypass -File <deploy-root>\scripts\stop.ps1
powershell -ExecutionPolicy Bypass -File <deploy-root>\scripts\update.ps1
powershell -ExecutionPolicy Bypass -File <deploy-root>\scripts\check.ps1
```

Use `scripts/search.py` in this skill for quick JSON/table search checks:

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

And plugin config:

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

The OpenClaw launcher should also set:

```cmd
set "SEARXNG_URL=http://127.0.0.1:8888"
```

Restart OpenClaw Gateway after config changes:

```powershell
<openclaw-home>\restart-openclaw.cmd
```

## Search Behavior

SearXNG queries engines concurrently. If one engine hits CAPTCHA, rate limits, or timeouts, other engines can still return results. Failed engines appear in `unresponsive_engines`.

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

2. Confirm actual results, not only HTTP 200:

```powershell
$r = Invoke-WebRequest -Uri 'http://127.0.0.1:8888/search?q=openai&format=json&categories=general' -UseBasicParsing -TimeoutSec 80
$j = $r.Content | ConvertFrom-Json
$j.results.Count
$j.unresponsive_engines
```

3. Inspect logs:

```powershell
Get-Content <deploy-root>\searxng-run.log -Tail 80
Get-Content <deploy-root>\searxng-run.err.log -Tail 120
```

4. Confirm listener and process:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8888
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*searxng_windows*' -or $_.CommandLine -like '*searx\webapp.py*' }
```

5. If OpenClaw cannot search but the local API works, verify `openclaw.json`, `SEARXNG_URL`, and restart the gateway.

## References

Read `references/deployment.md` when changing deployment, startup, update behavior, proxy settings, engine counts, or troubleshooting details.
