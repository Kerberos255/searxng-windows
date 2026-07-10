# Deployment Reference

## Directory Layout

```text
<deploy-root>\
  .venv\
  api_pool\
  patches\api_pool.py
  config\api-pool.env
  config\settings.yml
  scripts\
    apply-windows-patch.ps1
    check.ps1
    install.ps1
    run.ps1
    start.ps1
    start-hidden.vbs
    stop.ps1
    update.ps1
  searxng\
  searxng-master.zip
  searxng-run.log
  searxng-run.err.log
  searxng.pid
  broker-run.log
  broker-run.err.log
  broker.pid
```

## Optional API-First Gateway

- `8888`: normal SearXNG UI and search API; this is the default OpenClaw target.
- `8890`: optional API Pool gateway; it starts only when the `api pool` engine is
  enabled in `config\settings.yml`.
- Enabled provider order: `Parallel -> Tavily -> Brave -> Firecrawl`.
- Free fallback engines: Bing, Sogou, Qwant, and Mojeek, called only after the
  enabled API tier returns no results.
- Exact filters: `date_after` and `date_before` in `YYYY-MM-DD` format.
- API keys stay in `config\api-pool.env`; provider counters and cooldown state
  stay in `api_pool\data\api_pool.sqlite`.
- When the API Pool is disabled, OpenClaw remains on `8888` and uses ordinary
  SearXNG directly.

## Important Config

`config\settings.yml` should include:

```yaml
use_default_settings: true

server:
  bind_address: "127.0.0.1"
  port: 8888
  limiter: false
  public_instance: false
  image_proxy: false
  method: "GET"

search:
  safe_search: 0
  autocomplete: ""
  formats:
    - html
    - json

# Uncomment this block if direct outbound access to search engines times out.
# outgoing:
#   request_timeout: 10.0
#   max_request_timeout: 20.0
#   extra_proxy_timeout: 10
#   proxies:
#     all://:
#       - http://127.0.0.1:10808

ui:
  default_locale: "zh-Hans-CN"

engines:
  # Disabled by default. Enable this only when OpenClaw will use port 8890.
  - name: api pool
    engine: api_pool
    disabled: true
    enable_http: true
    categories:
      - general
      - web

  - name: duckduckgo
    disabled: true
  - name: duckduckgo images
    disabled: true
  - name: duckduckgo videos
    disabled: true
  - name: duckduckgo news
    disabled: true
```

`scripts\run.ps1` should always set SearXNG settings path. Proxy environment variables should only be set when `-ProxyUrl` is provided:

```powershell
$env:SEARXNG_SETTINGS_PATH = $Settings
$env:PYTHONUTF8 = "1"
if ($ProxyUrl) {
  $env:HTTP_PROXY = $ProxyUrl
  $env:HTTPS_PROXY = $ProxyUrl
  $env:ALL_PROXY = $ProxyUrl
  $env:NO_PROXY = "127.0.0.1,localhost"
}
```

## Engine Counts

As of this deployment:

- Engine Python modules: 236
- Configured engine instances: 321
- Enabled after local overrides: 82
- Disabled after local overrides: 190
- Inactive: 49
- Enabled general-category instances: about 55

Recompute counts with:

```powershell
@'
import yaml
from pathlib import Path
base = Path(r'<deploy-root>\searxng\searx\settings.yml')
local = Path(r'<deploy-root>\config\settings.yml')
base_cfg = yaml.safe_load(base.read_text(encoding='utf-8'))
local_cfg = yaml.safe_load(local.read_text(encoding='utf-8'))
engines = [e for e in base_cfg.get('engines', []) if isinstance(e, dict) and e.get('name')]
overrides = {e['name']: e for e in local_cfg.get('engines', []) if isinstance(e, dict) and 'name' in e}
active = disabled = inactive = 0
for e in engines:
    merged = dict(e)
    merged.update(overrides.get(e['name'], {}))
    if merged.get('inactive'):
        inactive += 1
    elif merged.get('disabled', False):
        disabled += 1
    else:
        active += 1
print(len(engines), active, disabled, inactive)
'@ | <deploy-root>\.venv\Scripts\python.exe -
```

## Startup Task

Scheduled Task:

- Name: `OpenClaw SearXNG`
- Trigger: user logon
- Action: `wscript.exe "<deploy-root>\scripts\start-hidden.vbs"`

Check it:

```powershell
Get-ScheduledTask -TaskName 'OpenClaw SearXNG'
Get-ScheduledTaskInfo -TaskName 'OpenClaw SearXNG'
```

Manually trigger it:

```powershell
Start-ScheduledTask -TaskName 'OpenClaw SearXNG'
```

## Common Problems

### HTTP 200 but empty results

Likely outbound search engines are timing out. Check proxy:

```powershell
Invoke-WebRequest -Uri 'https://www.google.com/search?q=openai' -Proxy 'http://127.0.0.1:10808' -UseBasicParsing -TimeoutSec 20
```

Then confirm `outgoing.proxies` and `run.ps1` proxy env are present.

### DuckDuckGo CAPTCHA

One failed engine should not block successful engines. Keep DuckDuckGo disabled if it repeatedly reports CAPTCHA.

### Brave rate limit

SearXNG's Brave engine scrapes HTML, not the official API. It can return `Too many request`. Disable `brave`, `brave.images`, and `brave.videos` if it becomes noisy.

### `pwd` import failure on Windows

Run:

```powershell
powershell -ExecutionPolicy Bypass -File <deploy-root>\scripts\apply-windows-patch.ps1
```

### OpenClaw still uses old search provider

Check `<openclaw-home>\.openclaw\openclaw.json`, `<openclaw-home>\openclaw.cmd`, then restart:

```powershell
<openclaw-home>\restart-openclaw.cmd
```
