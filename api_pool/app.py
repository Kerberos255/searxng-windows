"""API Pool Broker - Flask application for multi-provider search.

Endpoints:
  GET  /health  - Service health check
  GET  /status  - Provider status (no keys leaked)
  GET  /search  - SearXNG-compatible API-first search gateway
  POST /search  - Execute API provider search with priority/fallback logic
"""

import os
import sys
from datetime import date

# Ensure the api_pool package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from flask import Flask, request, jsonify

from api_pool import config
from api_pool import state
from api_pool.providers import brave, firecrawl, tavily, parallel

app = Flask(__name__)

# Provider dispatch table
_PROVIDERS = {
    "brave": brave,
    "firecrawl": firecrawl,
    "tavily": tavily,
    "parallel": parallel,
}


def _get_priority() -> list[str]:
    """Get provider priority order from config or default."""
    return config.get_priority()


def _parse_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("1", "true", "yes", "on"):
            return True
        if normalized in ("0", "false", "no", "off", ""):
            return False
    return default


def _parse_iso_date(value, field_name: str):
    if value in (None, ""):
        return None, None
    if not isinstance(value, str):
        return None, f"invalid {field_name}"
    normalized = value.strip()
    try:
        date.fromisoformat(normalized)
    except ValueError:
        return None, f"invalid {field_name}; expected YYYY-MM-DD"
    return normalized, None


def _parse_search_input(data: dict):
    query = data.get("query", "")
    if not isinstance(query, str) or not query.strip():
        return None, "query is required"
    query = query.strip()
    if len(query) > 5000:
        return None, "query must be 5000 characters or fewer"

    try:
        pageno = int(data.get("pageno", 1))
    except (ValueError, TypeError):
        return None, "invalid pageno"
    if pageno < 1 or pageno > 100:
        return None, "pageno must be between 1 and 100"

    time_range = data.get("time_range") or None
    if time_range not in (None, "day", "week", "month", "year"):
        return None, "invalid time_range"

    date_after, error = _parse_iso_date(data.get("date_after"), "date_after")
    if error:
        return None, error
    date_before, error = _parse_iso_date(data.get("date_before"), "date_before")
    if error:
        return None, error
    if date_after and date_before and date_after > date_before:
        return None, "date_after must not be later than date_before"

    try:
        safesearch = int(data.get("safesearch", 0))
    except (ValueError, TypeError):
        return None, "invalid safesearch"
    if safesearch not in (0, 1, 2):
        return None, "safesearch must be 0, 1, or 2"

    try:
        max_results = int(data.get("max_results", 10))
    except (ValueError, TypeError):
        return None, "invalid max_results"
    if max_results < 1 or max_results > 50:
        return None, "max_results must be between 1 and 50"

    language = data.get("language") or ""
    if not isinstance(language, str):
        return None, "invalid language"

    return {
        "query": query,
        "pageno": pageno,
        "time_range": time_range,
        "date_after": date_after,
        "date_before": date_before,
        "safesearch": safesearch,
        "max_results": max_results,
        "language": language.strip(),
        "fallback_on_empty": _parse_bool(data.get("fallback_on_empty"), False),
    }, None


def _run_api_search(search_input: dict) -> dict:
    priority = _get_priority()
    attempts = []

    for provider_name in priority:
        if search_input["date_before"] and provider_name == "parallel":
            attempts.append(
                {"provider": provider_name, "outcome": "unsupported_date_before"}
            )
            continue

        configured = config.is_provider_configured(provider_name)
        if not configured:
            state.set_configured(provider_name, False)
            attempts.append({"provider": provider_name, "outcome": "unconfigured"})
            continue

        state.set_configured(provider_name, True)
        prov_state = state.get_provider_state(provider_name)
        if prov_state:
            provider_status = prov_state.get("status")
            if provider_status == state.STATUS_MISCONFIGURED:
                attempts.append({"provider": provider_name, "outcome": "misconfigured"})
                continue
            if provider_status == state.STATUS_UNAVAILABLE:
                attempts.append({"provider": provider_name, "outcome": "unavailable"})
                continue

        if prov_state and prov_state.get("status") == state.STATUS_QUOTA_EXHAUSTED:
            if not state.try_acquire_probe_lease(provider_name):
                attempts.append({"provider": provider_name, "outcome": "quota_exhausted"})
                continue

        if prov_state and prov_state.get("status") == state.STATUS_COOLDOWN:
            cooldown_until = prov_state.get("cooldown_until")
            now = __import__("time").time()
            if cooldown_until and now < cooldown_until:
                attempts.append({"provider": provider_name, "outcome": "cooldown"})
                continue

        try:
            provider_mod = _PROVIDERS.get(provider_name)
            if not provider_mod:
                attempts.append({"provider": provider_name, "outcome": "unknown_provider"})
                continue

            result = provider_mod.search(
                query=search_input["query"],
                pageno=search_input["pageno"],
                time_range=search_input["time_range"],
                date_after=search_input["date_after"],
                date_before=search_input["date_before"],
                safesearch=search_input["safesearch"],
                max_results=search_input["max_results"],
            )

            if result.success:
                state.record_success(provider_name)
                if result.results or not search_input["fallback_on_empty"]:
                    return {
                        "provider": provider_name,
                        "results": result.results,
                        "attempts": attempts
                        + [{"provider": provider_name, "outcome": "success"}],
                    }
                attempts.append({"provider": provider_name, "outcome": "empty_results"})
                continue

            state.record_failure(
                provider=provider_name,
                http_status=result.http_status,
                error_category=result.error_category or "unknown",
                is_quota=result.is_quota,
                is_misconfigured=result.is_misconfigured,
                retry_after=result.retry_after,
            )
            attempts.append(
                {"provider": provider_name, "outcome": result.error_category or "error"}
            )
        except Exception as exc:
            state.record_failure(
                provider=provider_name,
                http_status=None,
                error_category=f"exception:{type(exc).__name__}",
            )
            attempts.append(
                {"provider": provider_name, "outcome": f"exception:{type(exc).__name__}"}
            )

    return {"provider": None, "results": [], "attempts": attempts}


def _free_search_query(search_input: dict) -> str:
    query = search_input["query"]
    if search_input["date_after"]:
        query += f" after:{search_input['date_after']}"
    if search_input["date_before"]:
        query += f" before:{search_input['date_before']}"
    return query


def _run_free_search(search_input: dict, api_attempts: list[dict]) -> dict:
    gateway_url = request.host_url.rstrip("/")
    if config.SEARXNG_BACKEND_URL == gateway_url:
        return {
            "query": search_input["query"],
            "provider": None,
            "results": [],
            "attempts": api_attempts
            + [{"provider": "searxng_free", "outcome": "recursive_backend_blocked"}],
            "fallback_used": True,
        }

    params = {
        "q": _free_search_query(search_input),
        "format": "json",
        "pageno": search_input["pageno"],
        "safesearch": search_input["safesearch"],
        "engines": ",".join(config.SEARXNG_FREE_ENGINES),
    }
    if search_input["time_range"]:
        params["time_range"] = search_input["time_range"]
    if search_input["language"]:
        params["language"] = search_input["language"]

    try:
        with httpx.Client(
            timeout=config.SEARXNG_FALLBACK_TIMEOUT,
            follow_redirects=True,
            trust_env=False,
        ) as client:
            response = client.get(f"{config.SEARXNG_BACKEND_URL}/search", params=params)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("SearXNG returned a non-object response")
        results = data.get("results")
        if not isinstance(results, list):
            results = []
        data["results"] = results[: search_input["max_results"]]
        data["provider"] = "searxng_free"
        data["api_attempts"] = api_attempts
        data["fallback_used"] = True
        return data
    except Exception as exc:
        return {
            "query": search_input["query"],
            "provider": None,
            "results": [],
            "attempts": api_attempts
            + [{"provider": "searxng_free", "outcome": f"exception:{type(exc).__name__}"}],
            "fallback_used": True,
        }


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    try:
        state.init_db()
        count = len(state.get_all_provider_states())
        return jsonify({"status": "ok", "providers_tracked": count}), 200
    except Exception as exc:
        return jsonify({"status": "error", "error": type(exc).__name__}), 500


@app.route("/status", methods=["GET"])
def status():
    """Provider status overview - no keys exposed."""
    state.init_db()
    default_priority = _get_priority()
    all_states = state.get_all_provider_states()
    configured = config.get_configured_providers()

    providers_info = []
    state_map = {s["provider"]: s for s in all_states}

    for prov in default_priority:
        s = state_map.get(prov, {})
        providers_info.append(
            {
                "provider": prov,
                "configured": configured.get(prov, False),
                "status": s.get("status", "unknown"),
                "cooldown_until": s.get("cooldown_until"),
                "probe_after": s.get("probe_after"),
                "consecutive_failures": s.get("consecutive_failures", 0),
                "last_error_category": s.get("last_error_category"),
                "last_success_at": s.get("last_success_at"),
                "last_attempt_at": s.get("last_attempt_at"),
                "request_count": s.get("request_count", 0),
                "success_count": s.get("success_count", 0),
            }
        )

    return jsonify(
        {
            "priority_order": default_priority,
            "providers": providers_info,
        }
    )


@app.route("/search", methods=["GET", "POST"])
def search():
    """Execute API-first search with optional free SearXNG fallback.

    POST accepts JSON:
      - query (str, required): Search query
      - pageno (int, optional): Page number, default 1
      - time_range (str, optional): Time range filter
      - date_after/date_before (str, optional): Exact ISO date boundaries
      - safesearch (int, optional): Safe search level (0/1/2)
      - max_results (int, optional): Results per page, default 10
      - fallback_on_empty (bool, optional): Fallback on empty results, default false

    GET accepts SearXNG-compatible q/format/count parameters, always tries every
    configured API provider on empty results, then uses the configured free
    SearXNG engines only if the API tier produced no results.
    """
    state.init_db()
    if request.method == "GET":
        data = {
            "query": request.args.get("q", ""),
            "pageno": request.args.get("pageno", 1),
            "time_range": request.args.get("time_range"),
            "date_after": request.args.get("date_after"),
            "date_before": request.args.get("date_before"),
            "safesearch": request.args.get("safesearch", 0),
            "max_results": request.args.get(
                "count", request.args.get("max_results", 10)
            ),
            "language": request.args.get("language", ""),
            "fallback_on_empty": True,
        }
    else:
        data = request.get_json(silent=True) or {}

    search_input, error = _parse_search_input(data)
    if error:
        return jsonify({"error": error}), 400

    api_result = _run_api_search(search_input)
    if api_result["results"] or request.method == "POST":
        if request.method == "GET":
            api_result["query"] = search_input["query"]
            api_result["number_of_results"] = len(api_result["results"])
            api_result["fallback_used"] = False
        return jsonify(api_result)

    if not config.SEARXNG_FREE_FALLBACK:
        api_result["query"] = search_input["query"]
        api_result["number_of_results"] = 0
        api_result["fallback_used"] = False
        return jsonify(api_result)

    return jsonify(_run_free_search(search_input, api_result["attempts"]))


def main():
    """Entry point for running the Broker directly."""
    state.init_db()
    # Initialize configured state for all providers
    configured = config.get_configured_providers()
    for prov, is_cfg in configured.items():
        state.set_configured(prov, is_cfg)

    # Recover misconfigured/unavailable providers to available on startup
    state.recover_configured_providers()

    print(f"API Pool Broker starting on {config.BROKER_HOST}:{config.BROKER_PORT}")
    app.run(
        host=config.BROKER_HOST,
        port=config.BROKER_PORT,
        debug=False,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()
