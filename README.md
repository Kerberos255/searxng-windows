# SearXNG Windows for OpenClaw

English | [简体中文](README.zh-CN.md)

A native Windows installer and maintenance toolkit for running a private local
SearXNG instance for OpenClaw. Docker is not required.

## Highlights

- Runs locally at `http://127.0.0.1:8888`
- Uses standard Python and a virtual environment
- Supports optional outbound proxy settings
- Includes install, start, stop, update, health-check, and logon-startup scripts
- Applies the required Windows compatibility patch automatically
- Includes an optional API Pool for Brave, Firecrawl, Tavily, and Parallel
- Keeps API keys, local state, logs, and generated configuration out of Git

## Requirements

- Windows 10 or Windows 11
- Python 3.11 or 3.12 x64
- Internet access during installation
- Git is optional; the installer falls back to source ZIP downloads

## Quick Start

1. Download these two files from the latest GitHub Release into the same folder:
   - `install-searxng-windows.cmd`
   - `install-searxng-windows.ps1`
2. Double-click `install-searxng-windows.cmd`.
3. Start SearXNG and run the health check:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Apps\searxng-windows\scripts\start.ps1"
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Apps\searxng-windows\scripts\check.ps1"
```

4. Open `http://127.0.0.1:8888`.

The default installation directory is:

```text
%USERPROFILE%\Apps\searxng-windows
```

The bootstrap installer resolves the latest Release by default, downloads that
package and upstream SearXNG, creates a virtual environment, installs
dependencies, generates a local
`secret_key`, and applies the Windows patches. Existing `config/settings.yml`
and `config/api-pool.env` files are preserved.

## OpenClaw Integration

Configure OpenClaw to use the normal local SearXNG endpoint on port `8888`:

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

Also set the launcher environment variables:

```cmd
set "SEARXNG_URL=http://127.0.0.1:8888"
set "SEARXNG_BASE_URL=http://127.0.0.1:8888"
```

Restart OpenClaw after changing its configuration. Keep port `8888` while the
API Pool is disabled. If you enable the API Pool below, switch all three URL
settings to port `8890`.

## Optional API Pool

The API Pool is installed but **disabled by default**. While disabled, its local
Broker is not started and normal SearXNG engines work as usual.

To enable it:

1. Edit `%USERPROFILE%\Apps\searxng-windows\config\settings.yml`.
2. Change the `api pool` entry from `disabled: true` to `disabled: false`.
3. Add at least one key to `config\api-pool.env`:

```dotenv
BRAVE_API_KEY=
FIRECRAWL_API_KEY=
TAVILY_API_KEY=
PARALLEL_API_KEY=
API_POOL_PRIORITY=parallel,tavily,brave,firecrawl
```

4. Change OpenClaw's `baseUrl`, `SEARXNG_URL`, and `SEARXNG_BASE_URL` from
   port `8888` to `8890`.
5. Restart SearXNG and OpenClaw.

The Broker starts only while the API Pool is enabled. It listens on
`http://127.0.0.1:8890`, exposes a SearXNG-compatible search endpoint for
OpenClaw, and uses this sequence:

```text
Parallel -> Tavily -> Brave -> Firecrawl -> Bing/Sogou/Qwant/Mojeek free fallback
```

It stops after the first API provider with results, so one search does not
consume all configured quotas. Empty results continue to the next API provider.
Only when the complete API tier is unavailable or empty does the gateway query
the free Bing, Sogou, Qwant, and Mojeek engines through SearXNG on port `8888`.
When the API Pool is disabled, OpenClaw should remain on port `8888` and use ordinary
SearXNG directly. Exact filters use `date_after` and `date_before` in
`YYYY-MM-DD` format. See [`api_pool/README.md`](api_pool/README.md) for endpoint,
state, and fallback details.

## Proxy Configuration

Proxy use is disabled by default. If outbound searches time out, edit
`config/settings.yml` and enable the example proxy block:

```yaml
outgoing:
  request_timeout: 10.0
  max_request_timeout: 20.0
  extra_proxy_timeout: 10
  proxies:
    all://:
      - http://127.0.0.1:10808
```

Replace the address with your proxy. Pass the same proxy to the launcher so the
API Pool and supporting tools receive standard proxy environment variables:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Apps\searxng-windows\scripts\start.ps1" -ProxyUrl "http://127.0.0.1:10808"
```

## Common Operations

```powershell
$Root = "$env:USERPROFILE\Apps\searxng-windows"

# Start SearXNG and the optional API Pool when enabled
powershell -ExecutionPolicy Bypass -File "$Root\scripts\start.ps1"

# Stop local services
powershell -ExecutionPolicy Bypass -File "$Root\scripts\stop.ps1"

# Check service status and perform a test search
powershell -ExecutionPolicy Bypass -File "$Root\scripts\check.ps1"

# Update the downloaded upstream SearXNG source and dependencies
powershell -ExecutionPolicy Bypass -File "$Root\scripts\update.ps1"

# Register startup at Windows logon
powershell -ExecutionPolicy Bypass -File "$Root\scripts\register-startup-task.ps1" -Root $Root
```

`update.ps1` updates upstream SearXNG. To update this repository's Windows
scripts, API Pool code, and templates, rerun the installer files from the latest
Release; existing local configuration is retained.

## Advanced Installation from a Git Clone

```powershell
git clone https://github.com/Kerberos255/searxng-windows.git
cd searxng-windows
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -Root "$env:USERPROFILE\Apps\searxng-windows"
```

The install script creates `config/settings.yml` and generates its local secret
automatically when the file does not already exist. Use `-RuntimePython` with a
full executable path when `python` is not available in `PATH`. The bootstrap
installer accepts `-Ref v0.2.0` when a specific release must be pinned.

## Troubleshooting

Run `scripts\check.ps1` first. Useful logs in the installation directory are:

```text
searxng-run.log
searxng-run.err.log
broker-run.log
broker-run.err.log
```

- Port `8888` is SearXNG; port `8890` is the optional API Pool Broker.
- A failed search engine does not normally block results from other engines.
- DuckDuckGo variants are disabled in the template because shared or proxied
  traffic frequently triggers CAPTCHA challenges.
- The SearXNG Brave engine scrapes Brave's public results and does not use the
  official Brave API key. The API Pool's Brave provider does use that key.

## Repository Boundaries

This repository intentionally does not contain:

- a virtual environment or a copied SearXNG source tree
- generated `config/settings.yml` or real API keys
- `config/api-pool.env`, SQLite state, logs, PID files, or downloaded archives
- private OpenClaw configuration

## CI and Releases

Pushes and pull requests run the Windows CI checks: PowerShell parsing, Python
compilation, API Pool tests, and public-package safety checks.

Pushing a semantic version tag such as `v0.2.0` triggers the Release workflow.
It repeats validation, verifies that the tagged commit belongs to `main`, builds
the release ZIP and bootstrap installers, generates SHA-256 checksums, and then
creates the GitHub Release automatically.

## License

The deployment scripts, standalone API Pool Broker, and documentation are MIT
licensed.

SearXNG is downloaded from its upstream project and is licensed under
AGPL-3.0-or-later. The small `patches/api_pool.py` SearXNG engine adapter is also
marked AGPL-3.0-or-later. Distributions that bundle SearXNG source or modified
SearXNG files must comply with its upstream license.
