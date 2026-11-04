"""SQLite-backed state persistence for API Pool providers.

Tracks provider status, cooldowns, failure counts, and usage statistics.
Safe for concurrent access (write-ahead-log mode).
"""

import sqlite3
import threading
from datetime import datetime, timezone
from typing import Optional

from . import config

STATUS_AVAILABLE = "available"
STATUS_COOLDOWN = "cooldown"
STATUS_QUOTA_EXHAUSTED = "quota_exhausted"
STATUS_MISCONFIGURED = "misconfigured"
STATUS_UNAVAILABLE = "unavailable"

_local = threading.local()
_connection_lock = threading.Lock()
_write_lock = threading.RLock()
_probe_lease_lock = threading.Lock()


def close_all():
    """Close the current thread's cached SQLite connection."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass
        _local.conn = None


def _get_connection() -> sqlite3.Connection:
    """Get a thread-local SQLite connection."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        with _connection_lock:
            conn = getattr(_local, "conn", None)
            if conn is None:
                config.DB_DIR.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(str(config.DB_PATH), timeout=30)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA busy_timeout=30000")
                conn.execute("PRAGMA synchronous=NORMAL")
                _local.conn = conn
    return conn


def init_db():
    """Create tables once during Broker startup."""
    with _write_lock:
        conn = _get_connection()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(
            """
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
            """
        )
        conn.commit()


def _ensure_provider(conn: sqlite3.Connection, provider: str):
    conn.execute(
        "INSERT OR IGNORE INTO providers (provider, status) VALUES (?, ?)",
        (provider, STATUS_UNAVAILABLE),
    )


def get_provider_state(provider: str) -> Optional[dict]:
    conn = _get_connection()
    row = conn.execute(
        "SELECT * FROM providers WHERE provider = ?", (provider,)
    ).fetchone()
    if row is None:
        with _write_lock:
            _ensure_provider(conn, provider)
            conn.commit()
            row = conn.execute(
                "SELECT * FROM providers WHERE provider = ?", (provider,)
            ).fetchone()
    return dict(row) if row is not None else None


def get_all_provider_states() -> list[dict]:
    conn = _get_connection()
    rows = conn.execute("SELECT * FROM providers ORDER BY provider").fetchall()
    return [dict(row) for row in rows]


def set_configured(provider: str, configured: bool):
    """Update configured state only when the value actually changes."""
    desired = 1 if configured else 0
    with _write_lock:
        conn = _get_connection()
        row = conn.execute(
            "SELECT configured FROM providers WHERE provider = ?", (provider,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO providers (provider, status, configured) VALUES (?, ?, ?)",
                (provider, STATUS_UNAVAILABLE, desired),
            )
            conn.commit()
        elif row["configured"] != desired:
            conn.execute(
                "UPDATE providers SET configured = ? WHERE provider = ?",
                (desired, provider),
            )
            conn.commit()

def recover_configured_providers():
    """Recover configured providers left unavailable/misconfigured at shutdown."""
    with _write_lock:
        conn = _get_connection()
        conn.execute(
            """UPDATE providers
               SET status = 'available', cooldown_until = NULL, consecutive_failures = 0
               WHERE configured = 1
                 AND status IN ('unavailable', 'misconfigured')"""
        )
        conn.commit()


def record_success(provider: str):
    now = datetime.now(timezone.utc).timestamp()
    with _write_lock:
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
    """Record a provider failure and update cooldown/probe state."""
    now = datetime.now(timezone.utc).timestamp()
    with _write_lock:
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
            probe_delay = (
                min(retry_after, 86400 * 7)
                if retry_after
                else config.QUOTA_PROBE_INTERVAL_SECONDS
            )
            probe_after = now + probe_delay
            consecutive = 0
        else:
            status = STATUS_COOLDOWN
            row = conn.execute(
                "SELECT consecutive_failures FROM providers WHERE provider = ?",
                (provider,),
            ).fetchone()
            consecutive = (row[0] if row else 0) + 1
            if retry_after and retry_after > 0:
                cooldown_delay = min(retry_after, 3600)
            else:
                cooldown_delay = min(
                    config.COOLDOWN_BASE_SECONDS * (2 ** (consecutive - 1)),
                    3600,
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
            (
                status,
                cooldown_until,
                probe_after,
                consecutive,
                http_status,
                error_category,
                now,
                provider,
            ),
        )
        conn.commit()


def try_acquire_probe_lease(provider: str) -> bool:
    """Acquire the single-flight lease for a quota-exhausted provider probe."""
    with _probe_lease_lock, _write_lock:
        conn = _get_connection()
        now = datetime.now(timezone.utc).timestamp()
        new_probe = now + config.QUOTA_PROBE_INTERVAL_SECONDS
        row = conn.execute(
            "SELECT probe_after FROM providers WHERE provider = ? AND status = ?",
            (provider, STATUS_QUOTA_EXHAUSTED),
        ).fetchone()

        if row is None or row["probe_after"] is None or row["probe_after"] > now:
            return False

        conn.execute(
            "UPDATE providers SET probe_after = ? WHERE provider = ?",
            (new_probe, provider),
        )
        conn.commit()
        return True
