"""API Pool Broker - Flask application for multi-provider search.

Endpoints:
  GET  /health  - Service health check
  GET  /status  - Provider status (no keys leaked)
  POST /search  - Execute search with priority/fallback logic
"""

import sys
import os

# Ensure the api_pool package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


@app.route("/search", methods=["POST"])
def search():
    """Execute a search with automatic provider fallback.

    Request JSON:
      - query (str, required): Search query
      - pageno (int, optional): Page number, default 1
      - time_range (str, optional): Time range filter
      - safesearch (int, optional): Safe search level (0/1/2)
      - max_results (int, optional): Results per page, default 10
      - fallback_on_empty (bool, optional): Fallback on empty results, default false

    Response JSON:
      - provider: Name of the provider that returned results
      - results: List of result dicts
      - attempts: List of attempt outcomes
    """
    state.init_db()
    data = request.get_json(silent=True) or {}
    query = data.get("query", "")
    if not isinstance(query, str) or not query.strip():
        return jsonify({"error": "query is required"}), 400
    query = query.strip()

    try:
        pageno = int(data.get("pageno", 1))
    except (ValueError, TypeError):
        return jsonify({"error": "invalid pageno"}), 400
    if pageno < 1 or pageno > 100:
        return jsonify({"error": "pageno must be between 1 and 100"}), 400

    time_range = data.get("time_range")
    if time_range is not None and time_range not in (None, "day", "week", "month", "year"):
        return jsonify({"error": "invalid time_range"}), 400

    try:
        safesearch = int(data.get("safesearch", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "invalid safesearch"}), 400
    if safesearch not in (0, 1, 2):
        return jsonify({"error": "safesearch must be 0, 1, or 2"}), 400

    try:
        max_results = int(data.get("max_results", 10))
    except (ValueError, TypeError):
        return jsonify({"error": "invalid max_results"}), 400
    if max_results < 1 or max_results > 50:
        return jsonify({"error": "max_results must be between 1 and 50"}), 400

    fallback_on_empty = bool(data.get("fallback_on_empty", False))

    priority = _get_priority()
    attempts = []
    last_error = None

    for provider_name in priority:
        configured = config.is_provider_configured(provider_name)
        if not configured:
            state.set_configured(provider_name, False)
            attempts.append({"provider": provider_name, "outcome": "unconfigured"})
            continue

        state.set_configured(provider_name, True)

        # Check provider state - skip if unavailable/misconfigured
        prov_state = state.get_provider_state(provider_name)
        if prov_state:
            st = prov_state.get("status")
            if st == state.STATUS_MISCONFIGURED:
                attempts.append({"provider": provider_name, "outcome": "misconfigured"})
                continue
            if st == state.STATUS_UNAVAILABLE:
                attempts.append({"provider": provider_name, "outcome": "unavailable"})
                continue

        # For quota_exhausted, atomically acquire probe lease
        if prov_state and prov_state.get("status") == state.STATUS_QUOTA_EXHAUSTED:
            if not state.try_acquire_probe_lease(provider_name):
                # Probe not ready or another caller already claimed the lease
                attempts.append({"provider": provider_name, "outcome": "quota_exhausted"})
                continue
            # This caller won the probe lease - proceed with one attempt

        # For cooldown, skip if still cooling down
        if prov_state and prov_state.get("status") == state.STATUS_COOLDOWN:
            cooldown_until = prov_state.get("cooldown_until")
            now = __import__("time").time()
            if cooldown_until and now < cooldown_until:
                attempts.append({"provider": provider_name, "outcome": "cooldown"})
                continue

        # Attempt search with this provider
        try:
            provider_mod = _PROVIDERS.get(provider_name)
            if not provider_mod:
                attempts.append({"provider": provider_name, "outcome": "unknown_provider"})
                continue

            result = provider_mod.search(
                query=query,
                pageno=pageno,
                time_range=time_range,
                safesearch=safesearch,
                max_results=max_results,
            )

            if result.success:
                state.record_success(provider_name)
                if result.results or not fallback_on_empty:
                    return jsonify(
                        {
                            "provider": provider_name,
                            "results": result.results,
                            "attempts": attempts
                            + [{"provider": provider_name, "outcome": "success"}],
                        }
                    )
                else:
                    # Empty results and fallback_on_empty=true - continue
                    attempts.append(
                        {"provider": provider_name, "outcome": "empty_results"}
                    )
                    continue
            else:
                # Record failure
                state.record_failure(
                    provider=provider_name,
                    http_status=result.http_status,
                    error_category=result.error_category or "unknown",
                    is_quota=result.is_quota,
                    is_misconfigured=result.is_misconfigured,
                    retry_after=result.retry_after,
                )
                outcome = result.error_category or "error"
                attempts.append({"provider": provider_name, "outcome": outcome})
                last_error = result

                # If misconfigured, skip permanently
                if result.is_misconfigured:
                    continue
                # If quota exhausted, check if we should try next
                if result.is_quota:
                    continue
                # Otherwise (transient error), try next
                continue

        except Exception as e:
            state.record_failure(
                provider=provider_name,
                http_status=None,
                error_category=f"exception:{type(e).__name__}",
            )
            attempts.append(
                {"provider": provider_name, "outcome": f"exception:{type(e).__name__}"}
            )
            continue

    # All providers exhausted
    return jsonify(
        {
            "provider": None,
            "results": [],
            "attempts": attempts,
        }
    )


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
