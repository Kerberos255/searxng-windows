"""SQLite-backed state persistence for API Pool providers.

Tracks provider status, cooldowns, failure counts, and usage statistics.
Safe for concurrent access (write-ahead-log mode).
"""

import sqlite3
import threading
from datetime import datetime, timezone
from typing import Optional

from . import config

# Status constants
STATUS_AVAILABLE = "available"
STATUS_COOLDOWN = "cooldown"
STATUS_QUOTA_EXHAUSTED = "quota_exhausted"
STATUS_MISCONFIGURED = "misconfigured"
STATUS_UNAVAILABLE = "unavailable"  # no key configured

_local = threading.local()


def close_all():
    """Close all cached connections and clear thread-local state."""
    if hasattr(_local, "conn") and _local.conn is not None:
        try:
            _local.conn.close()
        except Exception:
            pass
        _local.conn = None


def _get_connection() -> sqlite3.Connection:
    """Get thread-local SQLite connection with WAL mode."""
    if not hasattr(_local, "conn") or _local.conn is None:
        config.DB_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(config.DB_PATH), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn = conn
    return _local.conn


def init_db():
    """Create tables if they do not exist."""
    conn = _get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS providers (
            provider       TEXT PRIMARY KEY,
            status         TEXT NOT NULL DEFAULT 'unavailable',
            configured     INTEGER NOT NULL DEFAULT 0,
            cooldown_until REAL,
            probe_after    REAL,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            last_http_status      INTEGER,
            last_error_category   TEXT,
            last_success_at       REAL,
            last_attempt_at       REAL,
            request_count         INTEGER NOT NULL DEFAULT 0,
            success_count         INTEGER NOT NULL DEFAULT 0
        );
    """)
    conn.commit()


def _ensure_provider(conn: sqlite3.Connection, provider: str):
    """Insert a provider row if it does not exist."""
    conn.execute(
        "INSERT OR IGNORE INTO providers (provider, status) VALUES (?, ?)",
        (provider, STATUS_UNAVAILABLE),
    )


def get_provider_state(provider: str) -> Optional[dict]:
    """Get full state dict for a provider, or None if not found."""
    conn = _get_connection()
    _ensure_provider(conn, provider)
    row = conn.execute(
        "SELECT * FROM providers WHERE provider = ?", (provider,)
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def get_all_provider_states() -> list[dict]:
    """Get state for all tracked providers."""
    conn = _get_connection()
    rows = conn.execute("SELECT * FROM providers ORDER BY provider").fetchall()
    return [dict(r) for r in rows]


def set_configured(provider: str, configured: bool):
    """Mark a provider as configured (has valid key) or not.

    This only updates the configured flag. Recovery from misconfigured /
    unavailable is handled by ``recover_configured_providers()`` which is
    called on startup only.
    """
    conn = _get_connection()
    _ensure_provider(conn, provider)
    conn.execute(
        "UPDATE providers SET configured = ? WHERE provider = ?",
        (1 if configured else 0, provider),
    )
    conn.commit()


def recover_configured_providers():
    """On startup: recover configured providers from misconfigured/unavailable.

    Called once at Broker startup (in ``main()``). Resets status to
    ``available`` so providers can be retried even if they were left in
    a failure state from a previous run. Does NOT touch quota_exhausted
    or cooldown (those must expire naturally or via probe).
    """
    conn = _get_connection()
    conn.execute(
        """UPDATE providers
            SET status = 'available', cooldown_until = NULL, consecutive_failures = 0
            WHERE configured = 1
              AND status IN ('unavailable', 'misconfigured')""",
    )
    conn.commit()


def record_success(provider: str):
    """Record a successful API call."""
    now = datetime.now(timezone.utc).timestamp()
    conn = _get_connection()
    _ensure_provider(conn, provider)
    conn.execute(
        """UPDATE providers SET
            status = 'available',
            cooldown_until = NULL,
            probe_after = NULL,
            consecutive_failures = 0,
            last_http_status = NULL,
            last_error_category = NULL,
            last_success_at = ?,
            last_attempt_at = ?,
            request_count = request_count + 1,
            success_count = success_count + 1
        WHERE provider = ?""",
        (now, now, provider),
    )
    conn.commit()


def record_failure(
    provider: str,
    http_status: Optional[int],
    error_category: str,
    is_quota: bool = False,
    is_misconfigured: bool = False,
    retry_after: Optional[int] = None,
):
    """Record a failed API call and set appropriate cooldown/probe state.

    Args:
        provider: Provider name.
        http_status: HTTP status code if available.
        error_category: Short string describing the error type.
        is_quota: True if quota exhausted.
        is_misconfigured: True if key is invalid/missing.
        retry_after: Retry-After header value in seconds, if available.
    """
    now = datetime.now(timezone.utc).timestamp()
    conn = _get_connection()
    _ensure_provider(conn, provider)

    if is_misconfigured:
        status = STATUS_MISCONFIGURED
        cooldown_until = None
        probe_after = None
        consecutive = 0
    elif is_quota:
        status = STATUS_QUOTA_EXHAUSTED
        cooldown_until = None
        # Probe after 24h by default, or use Retry-After if provided
        if retry_after:
            probe_delay = min(retry_after, 86400 * 7)  # cap at 7 days
        else:
            probe_delay = config.QUOTA_PROBE_INTERVAL_SECONDS
        probe_after = now + probe_delay
        consecutive = 0
    else:
        # Transient error: cooldown
        status = STATUS_COOLDOWN
        consecutive = (
            conn.execute(
                "SELECT consecutive_failures FROM providers WHERE provider = ?",
                (provider,),
            ).fetchone()[0]
            + 1
        )
        if retry_after and retry_after > 0:
            cooldown_delay = min(retry_after, 3600)  # cap at 1h
        else:
            cooldown_delay = min(
                config.COOLDOWN_BASE_SECONDS * (2 ** (consecutive - 1)),
                3600,  # cap at 1h
            )
        cooldown_until = now + cooldown_delay
        probe_after = None

    conn.execute(
        """UPDATE providers SET
            status = ?,
            cooldown_until = ?,
            probe_after = ?,
            consecutive_failures = ?,
            last_http_status = ?,
            last_error_category = ?,
            last_attempt_at = ?,
            request_count = request_count + 1
        WHERE provider = ?""",
        (status, cooldown_until, probe_after, consecutive, http_status, error_category, now, provider),
    )
    conn.commit()


def get_next_available(priority: list[str]) -> Optional[str]:
    """Find the highest-priority available provider.

    Also recovers providers whose probe_after has elapsed (single probe gate).
    Returns provider name or None if none available.
    """
    conn = _get_connection()
    now = datetime.now(timezone.utc).timestamp()

    for prov in priority:
        _ensure_provider(conn, prov)
        row = conn.execute(
            "SELECT status, cooldown_until, probe_after FROM providers WHERE provider = ?",
            (prov,),
        ).fetchone()
        if row is None:
            continue

        status = row["status"]
        cooldown_until = row["cooldown_until"]
        probe_after = row["probe_after"]

        if status == STATUS_AVAILABLE:
            return prov

        # If in cooldown but cooldown has expired, auto-recover to available
        if status == STATUS_COOLDOWN and cooldown_until and now >= cooldown_until:
            conn.execute(
                "UPDATE providers SET status = 'available', cooldown_until = NULL WHERE provider = ?",
                (prov,),
            )
            conn.commit()
            return prov

        # If quota exhausted but probe time has arrived, allow probe (status stays
        # quota_exhausted but we return it so the caller can attempt a single probe)
        if status == STATUS_QUOTA_EXHAUSTED and probe_after and now >= probe_after:
            # Return it for probing - the caller must call record_success/record_failure
            return prov

    return None


def is_probe_pending(provider: str) -> bool:
    """Check if a provider is in quota_exhausted state and ready for probe."""
    state = get_provider_state(provider)
    if not state:
        return False
    if state["status"] != STATUS_QUOTA_EXHAUSTED:
        return False
    if not state["probe_after"]:
        return False
    now = datetime.now(timezone.utc).timestamp()
    return now >= state["probe_after"]


# Module-level lock for atomic probe lease (Python-level, not SQL-level)
# Since the Broker runs as a single-process Flask app, a threading.Lock
# ensures that only one request at a time can check-and-acquire the lease.
_probe_lease_lock = threading.Lock()


def try_acquire_probe_lease(provider: str) -> bool:
    """Atomically acquire a probe lease for a quota-exhausted provider.

    Uses a Python-level threading.Lock to guarantee serialization.
    Only one concurrent caller will succeed. The winner's caller should
    proceed with the API probe; other callers will skip the provider.
    """
    with _probe_lease_lock:
        conn = _get_connection()
        now = datetime.now(timezone.utc).timestamp()
        new_probe = now + config.QUOTA_PROBE_INTERVAL_SECONDS

        # Re-read current state while holding the lock
        row = conn.execute(
            "SELECT probe_after FROM providers WHERE provider = ? AND status = ?",
            (provider, STATUS_QUOTA_EXHAUSTED),
        ).fetchone()

        if row is None or row["probe_after"] is None or row["probe_after"] > now:
            return False  # not yet ready, or not in quota_exhausted

        conn.execute(
            "UPDATE providers SET probe_after = ? WHERE provider = ?",
            (new_probe, provider),
        )
        conn.commit()
        return True
