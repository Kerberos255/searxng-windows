# API Pool Broker

The API Pool is a local-only search broker used by SearXNG as one logical engine.
It tries API providers serially and stops after the first successful response, so
multiple free quotas are not consumed by every search.

Default order:

```text
Parallel -> Tavily -> Brave -> Firecrawl
```

The public Windows template keeps this engine disabled by default. Set the
`api pool` entry in `config/settings.yml` to `disabled: false` before starting
the Broker through the normal `start.ps1` workflow.

## Configuration

Copy `config/api-pool.env.example` to `config/api-pool.env` and fill only the
providers you want to enable:

```dotenv
BRAVE_API_KEY=
FIRECRAWL_API_KEY=
TAVILY_API_KEY=
PARALLEL_API_KEY=
API_POOL_PRIORITY=parallel,tavily,brave,firecrawl
```

The real `config/api-pool.env` is ignored by Git. Process environment variables
take precedence over the env file. `OPENCLAW_BRAVE_API_KEY` is also accepted as
a compatibility alias for `BRAVE_API_KEY`.

## Behavior

- One provider succeeds: return its results and stop.
- Quota exhausted: persist the state and try the next provider.
- HTTP 429, timeout, connection error, or server error: enter cooldown and try the next provider.
- Invalid or missing key: mark unavailable/misconfigured and skip it.
- All providers unavailable: return HTTP 200 with an empty result list; normal SearXNG engines continue working.
- Quota-exhausted providers are probed at low frequency with a single-flight lease.

Provider state is stored locally in `api_pool/data/api_pool.sqlite`. The database
contains status and counters only; API keys are never stored in SQLite or returned
by `/status`.

## Endpoints

- `GET http://127.0.0.1:8890/health`
- `GET http://127.0.0.1:8890/status`
- `POST http://127.0.0.1:8890/search`

Example request:

```json
{
  "query": "httpx proxy parameter",
  "pageno": 1,
  "time_range": "month",
  "safesearch": 0,
  "max_results": 10,
  "fallback_on_empty": false
}
```

Firecrawl is called in search-only mode (`sources: ["web"]`) without
`scrapeOptions`, avoiding additional page-scraping credit consumption.

## Tests

```powershell
python -m pip install -r api_pool\requirements.txt
python -m unittest discover -s api_pool\tests -v
```

The test suite uses mocked upstream APIs and does not need real credentials.
