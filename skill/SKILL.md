---
name: searxng
description: Use when Codex needs to operate, diagnose, maintain, or query a local Windows SearXNG deployment, including web search via the local JSON API, start/stop/update scripts, proxy troubleshooting, client integration, engine enable/disable decisions, and startup task management.
---

# Local SearXNG on Windows

This skill covers the local Windows SearXNG deployment provided by this repository.

## Path Conventions

- Deployment root: `<deploy-root>`
- Source: `<deploy-root>\searxng`
- Virtualenv Python: `<deploy-root>\.venv\Scripts\python.exe`
- SearXNG config: `<deploy-root>\config\settings.yml`
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

Proxy is disabled by default. If direct search-engine access times out, pass
`-ProxyUrl "http://127.0.0.1:10808"` to `start.ps1` or `run.ps1`, and uncomment
the `outgoing.proxies` block in `config\settings.yml`.

Use `scripts/search.py` in this skill for quick JSON/table search checks. It uses
ordinary SearXNG on `8888` by default; set `SEARXNG_URL` to `8890` only when the
API Pool is enabled:

```powershell
$env:SEARXNG_URL='http://127.0.0.1:8888'
python <skill-root>\scripts\search.py search "openai" --format json -n 3
```

## Deployment Facts

- SearXNG can be installed from the official GitHub source archive when Git is unavailable.
- SearXNG is installed editable into the venv with `pip install --no-build-isolation -e .`.
- A Windows compatibility patch is applied to `searx\valkeydb.py` because upstream imports Unix-only `pwd`.
- `update.ps1` stops SearXNG if running, updates source/dependencies, reapplies the Windows patch, and restarts it when appropriate.
- The optional Windows Scheduled Task defaults to `SearXNG Local` and starts SearXNG at user logon via `scripts\start-hidden.vbs`.

## Client Integration

SearXNG-compatible clients should use `http://127.0.0.1:8888` by default.
Only when `config\settings.yml` enables the `api pool` engine should clients that
need the API-first chain switch to `http://127.0.0.1:8890`.

The standard JSON endpoint is:

```text
http://127.0.0.1:8888/search?q=example&format=json
```

## Search Behavior

With the API Pool disabled, the Broker is not started and clients should query
ordinary SearXNG directly on port `8888`.

With the API Pool enabled, clients may query the API-first gateway on port `8890`.
It tries `Parallel -> Tavily -> Brave -> Firecrawl` serially and returns the first
non-empty result set. Only when every API provider is unavailable or empty does it
query the free Bing/Sogou/Qwant/Mojeek engines through SearXNG on port `8888`.

The gateway accepts `time_range` (`day`, `week`, `month`, `year`) plus exact
`date_after` and `date_before` values in `YYYY-MM-DD` format. Direct SearXNG
supports only the coarse `time_range` values. Parallel supports only the lower
date bound, so requests containing `date_before` skip it and continue with Tavily.

DuckDuckGo variants are disabled in the public template because shared or proxied
traffic can frequently trigger CAPTCHA challenges.

Brave in SearXNG scrapes `https://search.brave.com/` HTML and therefore requires
no API key, but can be rate-limited. The API Pool Brave provider is separate and
uses the official `BRAVE_API_KEY`.

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

5. If a client cannot search but the local API works, verify that its configured
   base URL points to `8888` when the API Pool is disabled or `8890` when it is enabled.

## References

Read `references/deployment.md` when changing deployment, startup, update behavior,
proxy settings, engine counts, or troubleshooting details.
