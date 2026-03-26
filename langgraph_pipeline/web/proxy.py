# langgraph_pipeline/web/proxy.py
# TracingProxy: SQLite persistence and async LangSmith forwarder for trace runs.
# Design: docs/plans/2026-03-25-14-langsmith-tracing-proxy-design.md

"""Intercepts LangSmith trace calls, persists them to a local SQLite database,
and optionally forwards them to the real LangSmith API in a background thread.

Usage:
    init_proxy(config)        # call once from server.py on startup
    get_proxy()               # returns the singleton or None when disabled
"""

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

DB_DEFAULT_PATH = "~/.claude/orchestrator-traces.db"
PAGE_SIZE_DEFAULT = 50

COMPLETIONS_LIMIT = 20

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS traces (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL,
    parent_run_id TEXT,
    name          TEXT NOT NULL,
    start_time    TEXT,
    end_time      TEXT,
    inputs_json   TEXT,
    outputs_json  TEXT,
    metadata_json TEXT,
    error         TEXT,
    created_at    TEXT NOT NULL
);
"""

_CREATE_COMPLETIONS_SQL = """
CREATE TABLE IF NOT EXISTS completions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT NOT NULL,
    item_type   TEXT NOT NULL,
    outcome     TEXT NOT NULL,
    cost_usd    REAL NOT NULL DEFAULT 0.0,
    duration_s  REAL NOT NULL DEFAULT 0.0,
    finished_at TEXT NOT NULL
);
"""

_CREATE_COST_TASKS_SQL = """
CREATE TABLE IF NOT EXISTS cost_tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_slug       TEXT NOT NULL,
    item_type       TEXT NOT NULL,
    task_id         TEXT NOT NULL,
    agent_type      TEXT NOT NULL,
    model           TEXT NOT NULL,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    cost_usd        REAL NOT NULL DEFAULT 0.0,
    duration_s      REAL NOT NULL DEFAULT 0.0,
    tool_calls_json TEXT,
    recorded_at     TEXT NOT NULL
);
"""

_CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_traces_run_id        ON traces (run_id);",
    "CREATE INDEX IF NOT EXISTS idx_traces_parent_run_id ON traces (parent_run_id);",
    "CREATE INDEX IF NOT EXISTS idx_traces_created_at    ON traces (created_at);",
    "CREATE INDEX IF NOT EXISTS idx_completions_finished ON completions (finished_at);",
    "CREATE INDEX IF NOT EXISTS idx_cost_tasks_item_slug ON cost_tasks (item_slug);",
]

_LANGSMITH_RUNS_URL = "https://api.smith.langchain.com/runs"

# ─── Module State ─────────────────────────────────────────────────────────────

_proxy_instance: Optional["TracingProxy"] = None


# ─── TracingProxy ──────────────────────────────────────────────────────────────


class TracingProxy:
    """Intercepts LangSmith trace calls for local persistence and optional forwarding."""

    def __init__(self, config: dict) -> None:
        """Initialise the proxy from the ``web.proxy`` config sub-dict.

        Args:
            config: The ``web.proxy`` section of orchestrator-config.yaml.
        """
        raw_path: str = config.get("db_path", DB_DEFAULT_PATH)
        self._db_path = Path(raw_path).expanduser()
        self._forward_enabled: bool = bool(config.get("forward_to_langsmith", False))
        self._langsmith_api_key: str = config.get("langsmith_api_key", "")
        self._init_db()

    # ─── DB Setup ─────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Create the traces table and indexes if they do not exist yet."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.execute(_CREATE_COMPLETIONS_SQL)
            conn.execute(_CREATE_COST_TASKS_SQL)
            for index_sql in _CREATE_INDEXES_SQL:
                conn.execute(index_sql)

    def _connect(self) -> sqlite3.Connection:
        """Open and return a new SQLite connection with row_factory set."""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # ─── Write ────────────────────────────────────────────────────────────────

    def record_run(
        self,
        run_id: str,
        parent_run_id: Optional[str],
        name: str,
        inputs: Optional[dict],
        outputs: Optional[dict],
        metadata: Optional[dict],
        error: Optional[str],
        start_time: Optional[str],
        end_time: Optional[str],
    ) -> None:
        """Persist a trace run to SQLite and schedule an async forward if enabled.

        Never raises; all errors are logged at DEBUG level so callers are not disrupted.

        Args:
            run_id: Unique identifier for this run.
            parent_run_id: Parent run identifier, or None for root runs.
            name: Human-readable run name (tool name, chain name, etc.).
            inputs: Input payload dict, will be serialised to JSON.
            outputs: Output payload dict, will be serialised to JSON.
            metadata: Arbitrary metadata dict, will be serialised to JSON.
            error: Error message string if the run failed, else None.
            start_time: ISO-8601 start timestamp string.
            end_time: ISO-8601 end timestamp string.
        """
        created_at = datetime.now(timezone.utc).isoformat()
        row = {
            "run_id": run_id,
            "parent_run_id": parent_run_id,
            "name": name,
            "start_time": start_time,
            "end_time": end_time,
            "inputs_json": json.dumps(inputs) if inputs is not None else None,
            "outputs_json": json.dumps(outputs) if outputs is not None else None,
            "metadata_json": json.dumps(metadata) if metadata is not None else None,
            "error": error,
            "created_at": created_at,
        }
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO traces
                        (run_id, parent_run_id, name, start_time, end_time,
                         inputs_json, outputs_json, metadata_json, error, created_at)
                    VALUES
                        (:run_id, :parent_run_id, :name, :start_time, :end_time,
                         :inputs_json, :outputs_json, :metadata_json, :error, :created_at)
                    """,
                    row,
                )
        except Exception:
            logger.debug("TracingProxy: failed to write run_id=%s to SQLite", run_id, exc_info=True)
            return

        if self._forward_enabled:
            payload = {
                "id": run_id,
                "parent_run_id": parent_run_id,
                "name": name,
                "inputs": inputs,
                "outputs": outputs,
                "extra": {"metadata": metadata},
                "error": error,
                "start_time": start_time,
                "end_time": end_time,
            }
            try:
                self._forward_async(payload)
            except Exception:
                logger.debug("TracingProxy: failed to schedule forward for run_id=%s", run_id, exc_info=True)

    # ─── Async Forwarder ──────────────────────────────────────────────────────

    def _forward_async(self, payload: dict) -> None:
        """Fire-and-forget: POST payload to the real LangSmith API in a daemon thread.

        Catches all exceptions and logs them at DEBUG level so the caller is never
        disrupted by forwarding failures.
        """
        api_key = self._langsmith_api_key

        def _send() -> None:
            try:
                import urllib.request

                data = json.dumps(payload).encode()
                req = urllib.request.Request(
                    _LANGSMITH_RUNS_URL,
                    data=data,
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": api_key,
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    logger.debug(
                        "TracingProxy: forwarded run_id=%s status=%d",
                        payload.get("id"),
                        resp.status,
                    )
            except Exception:
                logger.debug(
                    "TracingProxy: forward failed for run_id=%s",
                    payload.get("id"),
                    exc_info=True,
                )

        thread = threading.Thread(target=_send, daemon=True, name="proxy-forward")
        thread.start()

    # ─── Completions ──────────────────────────────────────────────────────────

    def record_completion(
        self,
        slug: str,
        item_type: str,
        outcome: str,
        cost_usd: float,
        duration_s: float,
    ) -> None:
        """Persist a worker completion record to the completions table.

        Args:
            slug: Work item slug.
            item_type: One of "defect", "feature", or "analysis".
            outcome: One of "success", "warn", or "fail".
            cost_usd: API cost incurred by this worker.
            duration_s: Wall-clock seconds the worker ran.
        """
        finished_at = datetime.now(timezone.utc).isoformat()
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO completions (slug, item_type, outcome, cost_usd, duration_s, finished_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [slug, item_type, outcome, cost_usd, duration_s, finished_at],
                )
        except Exception:
            logger.debug("TracingProxy: failed to record completion for %s", slug, exc_info=True)

    def list_completions(self, limit: int = COMPLETIONS_LIMIT) -> list[dict]:
        """Return the most recent completions ordered by finished_at descending.

        Args:
            limit: Maximum number of rows to return.

        Returns:
            List of dicts with keys: slug, item_type, outcome, cost_usd, duration_s, finished_at.
        """
        sql = "SELECT slug, item_type, outcome, cost_usd, duration_s, finished_at FROM completions ORDER BY finished_at DESC LIMIT ?"
        with self._connect() as conn:
            rows = conn.execute(sql, [limit]).fetchall()
        return [dict(row) for row in rows]

    # ─── Read Helpers ─────────────────────────────────────────────────────────

    def list_runs(
        self,
        page: int = 1,
        page_size: int = PAGE_SIZE_DEFAULT,
        slug: str = "",
        model: str = "",
        date_from: str = "",
        date_to: str = "",
    ) -> list[dict]:
        """Return a paginated list of root runs (parent_run_id IS NULL).

        Args:
            page: 1-based page number.
            page_size: Number of rows per page.
            slug: Filter on name containing this substring (case-insensitive).
            model: Filter on metadata_json containing this model string.
            date_from: ISO date string lower bound for created_at (inclusive).
            date_to: ISO date string upper bound for created_at (inclusive).

        Returns:
            List of row dicts ordered by created_at descending.
        """
        conditions = ["parent_run_id IS NULL"]
        params: list = []

        if slug:
            conditions.append("name LIKE ?")
            params.append(f"%{slug}%")
        if model:
            conditions.append("metadata_json LIKE ?")
            params.append(f"%{model}%")
        if date_from:
            conditions.append("created_at >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("created_at <= ?")
            params.append(date_to)

        where = " AND ".join(conditions)
        offset = (page - 1) * page_size
        params.extend([page_size, offset])

        sql = f"""
            SELECT * FROM traces
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_run(self, run_id: str) -> Optional[dict]:
        """Return a single trace row by run_id, or None if not found.

        Args:
            run_id: The run identifier to look up.
        """
        sql = "SELECT * FROM traces WHERE run_id = ? LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(sql, [run_id]).fetchone()
        return dict(row) if row else None

    def count_runs(
        self,
        slug: str = "",
        model: str = "",
        date_from: str = "",
        date_to: str = "",
    ) -> int:
        """Return total count of root runs matching the given filters.

        Uses the same filter logic as list_runs but returns only the count.
        """
        conditions = ["parent_run_id IS NULL"]
        params: list = []

        if slug:
            conditions.append("name LIKE ?")
            params.append(f"%{slug}%")
        if model:
            conditions.append("metadata_json LIKE ?")
            params.append(f"%{model}%")
        if date_from:
            conditions.append("created_at >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("created_at <= ?")
            params.append(date_to)

        where = " AND ".join(conditions)
        sql = f"SELECT COUNT(*) FROM traces WHERE {where}"
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return row[0] if row else 0

    def count_children_batch(self, run_ids: list[str]) -> dict[str, int]:
        """Return child run counts for a batch of parent run_ids.

        Args:
            run_ids: List of parent run identifiers.

        Returns:
            Dict mapping run_id to child count.
        """
        if not run_ids:
            return {}
        placeholders = ",".join("?" for _ in run_ids)
        sql = f"""
            SELECT parent_run_id, COUNT(*) as cnt
            FROM traces
            WHERE parent_run_id IN ({placeholders})
            GROUP BY parent_run_id
        """
        with self._connect() as conn:
            rows = conn.execute(sql, run_ids).fetchall()
        return {row[0]: row[1] for row in rows}

    def get_children(self, run_id: str) -> list[dict]:
        """Return all direct child runs for the given parent run_id.

        Args:
            run_id: The parent run identifier whose children to retrieve.

        Returns:
            List of row dicts ordered by start_time ascending.
        """
        sql = """
            SELECT * FROM traces
            WHERE parent_run_id = ?
            ORDER BY start_time ASC
        """
        with self._connect() as conn:
            rows = conn.execute(sql, [run_id]).fetchall()
        return [dict(row) for row in rows]


# ─── Module-Level Singleton ────────────────────────────────────────────────────


def get_proxy() -> Optional[TracingProxy]:
    """Return the shared TracingProxy instance, or None when the proxy is disabled."""
    return _proxy_instance


def init_proxy(config: dict) -> None:
    """Initialise the module-level TracingProxy singleton from the given config.

    Call this once from server.py when the web server starts and
    ``web.proxy.enabled`` is true.

    Args:
        config: The ``web.proxy`` section of orchestrator-config.yaml.
    """
    global _proxy_instance
    _proxy_instance = TracingProxy(config)
    logger.info("TracingProxy initialised at db_path=%s", _proxy_instance._db_path)
