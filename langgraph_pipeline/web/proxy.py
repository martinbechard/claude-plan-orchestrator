# langgraph_pipeline/web/proxy.py
# TracingProxy: SQLite persistence, async LangSmith forwarder, and cost query methods.
# Design: docs/plans/2026-03-25-14-langsmith-tracing-proxy-design.md
# Design: docs/plans/2026-03-26-10-trace-cost-analysis-page-design.md
# Design: docs/plans/2026-03-26-11-tool-call-cost-attribution-design.md

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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

DB_DEFAULT_PATH = "~/.claude/orchestrator-traces.db"
PAGE_SIZE_DEFAULT = 50

COMPLETIONS_LIMIT = 20
TOP_TOOL_CALLS_LIMIT = 250
BASH_COMMAND_PREVIEW_LENGTH = 50

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS traces (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL,
    parent_run_id TEXT,
    name          TEXT NOT NULL,
    model         TEXT NOT NULL DEFAULT '',
    start_time    TEXT,
    end_time      TEXT,
    inputs_json   TEXT,
    outputs_json  TEXT,
    metadata_json TEXT,
    error         TEXT,
    created_at    TEXT NOT NULL
);
"""

_ALTER_ADD_MODEL_SQL = "ALTER TABLE traces ADD COLUMN model TEXT NOT NULL DEFAULT ''"

_CREATE_COMPLETIONS_SQL = """
CREATE TABLE IF NOT EXISTS completions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT NOT NULL,
    item_type   TEXT NOT NULL,
    outcome     TEXT NOT NULL,
    cost_usd    REAL NOT NULL DEFAULT 0.0,
    duration_s  REAL NOT NULL DEFAULT 0.0,
    finished_at TEXT NOT NULL,
    run_id      TEXT
);
"""

_ALTER_ADD_COMPLETIONS_RUN_ID_SQL = "ALTER TABLE completions ADD COLUMN run_id TEXT"

_ALTER_ADD_COMPLETIONS_TOKENS_PER_MINUTE_SQL = (
    "ALTER TABLE completions ADD COLUMN tokens_per_minute REAL NOT NULL DEFAULT 0.0"
)

_ALTER_ADD_COMPLETIONS_VERIFICATION_NOTES_SQL = (
    "ALTER TABLE completions ADD COLUMN verification_notes TEXT"
)

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

_DEDUPLICATE_RUN_IDS_SQL = """
DELETE FROM traces
WHERE id NOT IN (
    SELECT MAX(id) FROM traces GROUP BY run_id
)
AND run_id IN (
    SELECT run_id FROM traces GROUP BY run_id HAVING COUNT(*) > 1
);
"""

_CREATE_UNIQUE_INDEX_RUN_ID_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_traces_run_id_unique ON traces (run_id);"
)

_CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_traces_parent_run_id ON traces (parent_run_id);",
    "CREATE INDEX IF NOT EXISTS idx_traces_created_at    ON traces (created_at);",
    "CREATE INDEX IF NOT EXISTS idx_traces_model         ON traces (model);",
    "CREATE INDEX IF NOT EXISTS idx_completions_finished ON completions (finished_at);",
    "CREATE INDEX IF NOT EXISTS idx_cost_tasks_item_slug ON cost_tasks (item_slug);",
]

_LANGSMITH_RUNS_URL = "https://api.smith.langchain.com/runs"

COST_SORT_INCLUSIVE_DESC = "inclusive_desc"
COST_SORT_EXCLUSIVE_DESC = "exclusive_desc"
COST_SORT_DATE_DESC = "date_desc"

_WORKER_TOKEN_COUNTS_SQL = """
WITH RECURSIVE subtree(run_id) AS (
    SELECT run_id FROM traces WHERE run_id = ?
    UNION ALL
    SELECT t.run_id FROM traces t JOIN subtree s ON t.parent_run_id = s.run_id
)
SELECT
    COALESCE(SUM(json_extract(t.metadata_json, '$.input_tokens')), 0),
    COALESCE(SUM(json_extract(t.metadata_json, '$.output_tokens')), 0)
FROM traces t JOIN subtree s ON t.run_id = s.run_id
"""

# Recursive CTE fragment: computes inclusive cost (run + all descendants) for a given run_id.
# Bind parameter :anchor_id must be set to the run_id of the row being computed.
_INCLUSIVE_COST_CTE = """
    WITH RECURSIVE subtree(run_id, total_cost_usd) AS (
        SELECT run_id,
               COALESCE(json_extract(metadata_json, '$.total_cost_usd'), 0.0)
        FROM traces
        WHERE run_id = :anchor_id
        UNION ALL
        SELECT t.run_id,
               COALESCE(json_extract(t.metadata_json, '$.total_cost_usd'), 0.0)
        FROM traces t
        JOIN subtree s ON t.parent_run_id = s.run_id
    )
    SELECT COALESCE(SUM(total_cost_usd), 0.0) FROM subtree
"""


# ─── Cost Data Types ──────────────────────────────────────────────────────────


@dataclass
class CostSummary:
    """Aggregate cost figures for the analysis page summary cards."""

    total_cost_usd: float
    today_cost_usd: float
    week_cost_usd: float
    most_expensive_slug: str
    most_expensive_slug_cost_usd: float


@dataclass
class DailyCost:
    """Cost total for a single calendar day."""

    date_str: str
    cost_usd: float


@dataclass
class CostRun:
    """One row in the paginated top-runs table."""

    run_id: str
    name: str
    model: str
    item_slug: str
    item_type: str
    exclusive_cost_usd: float
    inclusive_cost_usd: float
    input_tokens: int
    output_tokens: int
    duration_ms: int
    created_at: str


@dataclass
class SlugCost:
    """Aggregated cost for a single work-item slug."""

    item_slug: str
    item_type: str
    total_cost_usd: float
    task_count: int
    avg_cost_usd: float


@dataclass
class NodeCost:
    """Aggregated cost for a single node type (e.g. execute_task, validate_task)."""

    node_name: str
    task_count: int
    total_cost_usd: float
    avg_cost_usd: float


@dataclass
class ToolCallCost:
    """Proportional cost attribution for a single tool call within a task."""

    tool_name: str
    detail: str           # file_path for Read/Edit/Write, command prefix for Bash, pattern for Grep/Glob
    result_bytes: int
    estimated_cost_usd: float
    item_slug: str
    task_id: str


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
            try:
                conn.execute(_ALTER_ADD_MODEL_SQL)
            except sqlite3.OperationalError:
                pass  # Column already exists in an existing database
            try:
                conn.execute(_ALTER_ADD_COMPLETIONS_RUN_ID_SQL)
            except sqlite3.OperationalError:
                pass  # Column already exists in an existing database
            try:
                conn.execute(_ALTER_ADD_COMPLETIONS_TOKENS_PER_MINUTE_SQL)
            except sqlite3.OperationalError:
                pass  # Column already exists in an existing database
            try:
                conn.execute(_ALTER_ADD_COMPLETIONS_VERIFICATION_NOTES_SQL)
            except sqlite3.OperationalError:
                pass  # Column already exists in an existing database
            conn.execute(_DEDUPLICATE_RUN_IDS_SQL)
            conn.execute(_CREATE_UNIQUE_INDEX_RUN_ID_SQL)
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
                    ON CONFLICT(run_id) DO UPDATE SET
                        end_time     = COALESCE(excluded.end_time,     traces.end_time),
                        outputs_json = COALESCE(excluded.outputs_json, traces.outputs_json),
                        error        = COALESCE(excluded.error,        traces.error)
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

    def propagate_model_to_root(self, parent_run_id: str, model: str) -> None:
        """Walk up the parent chain and set model on the root run if currently empty.

        Only the root run (parent_run_id IS NULL) is updated. First-write wins:
        if the root already has a model value, the update is skipped.

        Args:
            parent_run_id: The parent_run_id of the child run that carries model info.
            model: The model name extracted from the child run's extra.invocation_params.
        """
        if not model:
            return
        try:
            with self._connect() as conn:
                current_id = parent_run_id
                while current_id:
                    row = conn.execute(
                        "SELECT run_id, parent_run_id FROM traces WHERE run_id = ? LIMIT 1",
                        [current_id],
                    ).fetchone()
                    if row is None:
                        break
                    if row["parent_run_id"] is None:
                        # This is the root run
                        conn.execute(
                            "UPDATE traces SET model = ? WHERE run_id = ? AND model = ''",
                            [model, current_id],
                        )
                        break
                    current_id = row["parent_run_id"]
        except Exception:
            logger.debug(
                "TracingProxy: failed to propagate model to root for parent_run_id=%s",
                parent_run_id,
                exc_info=True,
            )

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
        run_id: Optional[str] = None,
        tokens_per_minute: float = 0.0,
        verification_notes: Optional[str] = None,
    ) -> None:
        """Persist a worker completion record to the completions table.

        Args:
            slug: Work item slug.
            item_type: One of "defect", "feature", or "analysis".
            outcome: One of "success", "warn", or "fail".
            cost_usd: API cost incurred by this worker.
            duration_s: Wall-clock seconds the worker ran.
            run_id: LangSmith trace UUID, if available.
            tokens_per_minute: Final token throughput velocity at reap time.
            verification_notes: JSON string with verdict, findings[], and evidence from the validator.
        """
        finished_at = datetime.now(timezone.utc).isoformat()
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO completions
                        (slug, item_type, outcome, cost_usd, duration_s, finished_at, run_id,
                         tokens_per_minute, verification_notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [slug, item_type, outcome, cost_usd, duration_s, finished_at, run_id,
                     tokens_per_minute, verification_notes],
                )
        except Exception:
            logger.debug("TracingProxy: failed to record completion for %s", slug, exc_info=True)

    def list_completions(
        self,
        page: int = 1,
        page_size: int = COMPLETIONS_LIMIT,
        slug: str = "",
        outcome: str = "",
        date_from: str = "",
        date_to: str = "",
    ) -> list[dict]:
        """Return completions ordered by finished_at descending, with optional filters.

        The dashboard SSE feed calls this with no arguments and receives the most
        recent COMPLETIONS_LIMIT rows (page=1, page_size=COMPLETIONS_LIMIT).
        The /completions route passes explicit pagination and filter params.

        Args:
            page: 1-based page number.
            page_size: Number of rows per page.
            slug: Filter on slug containing this substring (case-insensitive).
            outcome: Filter on exact outcome value (e.g. "success", "warn", "fail").
            date_from: ISO date string lower bound for finished_at (inclusive).
            date_to: ISO date string upper bound for finished_at (inclusive).

        Returns:
            List of dicts with keys: slug, item_type, outcome, cost_usd, duration_s, finished_at, run_id, tokens_per_minute, verification_notes.
        """
        conditions, params = self._completions_filter(slug, outcome, date_from, date_to)
        where = " AND ".join(conditions) if conditions else "1"
        offset = (page - 1) * page_size
        params.extend([page_size, offset])
        sql = f"""
            SELECT slug, item_type, outcome, cost_usd, duration_s, finished_at, run_id,
                   tokens_per_minute, verification_notes
            FROM completions
            WHERE {where}
            ORDER BY finished_at DESC
            LIMIT ? OFFSET ?
        """
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def count_completions(
        self,
        slug: str = "",
        outcome: str = "",
        date_from: str = "",
        date_to: str = "",
    ) -> int:
        """Return total count of completions matching the given filters.

        Uses the same filter logic as list_completions but returns only the count.

        Args:
            slug: Filter on slug containing this substring (case-insensitive).
            outcome: Filter on exact outcome value (e.g. "success", "warn", "fail").
            date_from: ISO date string lower bound for finished_at (inclusive).
            date_to: ISO date string upper bound for finished_at (inclusive).
        """
        conditions, params = self._completions_filter(slug, outcome, date_from, date_to)
        where = " AND ".join(conditions) if conditions else "1"
        sql = f"SELECT COUNT(*) FROM completions WHERE {where}"
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return row[0] if row else 0

    def sum_completions_cost(
        self,
        slug: str = "",
        outcome: str = "",
        date_from: str = "",
        date_to: str = "",
    ) -> float:
        """Return sum of cost_usd for completions matching the given filters.

        Args:
            slug: Filter on slug containing this substring (case-insensitive).
            outcome: Filter on exact outcome value (e.g. "success", "warn", "fail").
            date_from: ISO date string lower bound for finished_at (inclusive).
            date_to: ISO date string upper bound for finished_at (inclusive).
        """
        conditions, params = self._completions_filter(slug, outcome, date_from, date_to)
        where = " AND ".join(conditions) if conditions else "1"
        sql = f"SELECT COALESCE(SUM(cost_usd), 0.0) FROM completions WHERE {where}"
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return float(row[0]) if row else 0.0

    def _completions_filter(
        self,
        slug: str,
        outcome: str,
        date_from: str,
        date_to: str,
    ) -> tuple[list[str], list]:
        """Build WHERE clause conditions and params for completions queries.

        Args:
            slug: Substring match on slug (case-insensitive).
            outcome: Exact match on outcome.
            date_from: ISO date lower bound for finished_at.
            date_to: ISO date upper bound for finished_at.

        Returns:
            Tuple of (conditions list, params list).
        """
        conditions: list[str] = []
        params: list = []
        if slug:
            conditions.append("slug LIKE ?")
            params.append(f"%{slug}%")
        if outcome:
            conditions.append("outcome = ?")
            params.append(outcome)
        if date_from:
            conditions.append("finished_at >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("finished_at <= ?")
            params.append(date_to)
        return conditions, params

    def list_completions_by_slug(self, slug: str) -> list[dict]:
        """Return all completions for the given slug, ordered by finished_at descending.

        Args:
            slug: Work item slug to filter by.

        Returns:
            List of dicts with keys: slug, item_type, outcome, cost_usd, duration_s, finished_at, run_id, tokens_per_minute, verification_notes.
        """
        sql = """
            SELECT slug, item_type, outcome, cost_usd, duration_s, finished_at, run_id,
                   tokens_per_minute, verification_notes
            FROM completions
            WHERE slug = ?
            ORDER BY finished_at DESC
        """
        with self._connect() as conn:
            rows = conn.execute(sql, [slug]).fetchall()
        return [dict(row) for row in rows]

    def list_root_traces_by_slug(self, slug: str) -> list[dict]:
        """Return root traces whose name contains the given slug.

        Args:
            slug: Work item slug to match against trace names.

        Returns:
            List of dicts with keys: run_id, name, created_at.
        """
        sql = """
            SELECT run_id, name, MIN(created_at) AS created_at
            FROM traces
            WHERE parent_run_id IS NULL AND name LIKE ?
            GROUP BY run_id
            ORDER BY created_at DESC
        """
        with self._connect() as conn:
            rows = conn.execute(sql, [f"%{slug}%"]).fetchall()
        return [dict(row) for row in rows]

    def get_worker_token_counts(self, run_id: str) -> tuple[int, int]:
        """Return cumulative (input_tokens, output_tokens) across all traces in the run subtree.

        Uses a recursive CTE to sum token counts from metadata_json across the root run
        and all descendant traces.

        Args:
            run_id: The root run_id of the worker session.

        Returns:
            Tuple of (input_tokens, output_tokens) as integers.
        """
        try:
            with self._connect() as conn:
                row = conn.execute(_WORKER_TOKEN_COUNTS_SQL, [run_id]).fetchone()
            if row:
                return (int(row[0]), int(row[1]))
        except Exception:
            logger.debug(
                "TracingProxy: failed to get token counts for run_id=%s", run_id, exc_info=True
            )
        return (0, 0)

    # ─── Cost Tasks ───────────────────────────────────────────────────────────

    def record_cost_task(
        self,
        item_slug: str,
        item_type: str,
        task_id: str,
        agent_type: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        duration_s: float,
        tool_calls_json: Optional[str],
        recorded_at: str,
    ) -> None:
        """Persist a per-task cost record to the cost_tasks table.

        Never raises; errors are logged at DEBUG level so callers are not disrupted.

        Args:
            item_slug: Work item slug (e.g. "01-some-feature").
            item_type: One of "defect" or "feature".
            task_id: Plan task identifier (e.g. "1.1").
            agent_type: Agent role (e.g. "coder", "validator").
            model: Model ID used for the task.
            input_tokens: Number of input tokens consumed.
            output_tokens: Number of output tokens produced.
            cost_usd: Estimated API cost in USD.
            duration_s: Wall-clock seconds the task ran.
            tool_calls_json: JSON-serialised list of tool call dicts, or None.
            recorded_at: ISO-8601 timestamp when the record was created.
        """
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO cost_tasks
                        (item_slug, item_type, task_id, agent_type, model,
                         input_tokens, output_tokens, cost_usd, duration_s,
                         tool_calls_json, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        item_slug,
                        item_type,
                        task_id,
                        agent_type,
                        model,
                        input_tokens,
                        output_tokens,
                        cost_usd,
                        duration_s,
                        tool_calls_json,
                        recorded_at,
                    ],
                )
        except Exception:
            logger.debug("TracingProxy: failed to record cost_task for %s/%s", item_slug, task_id, exc_info=True)

    def merge_metadata(self, run_id: str, metadata: dict) -> None:
        """Merge custom metadata into an existing trace row's metadata_json.

        Reads the current metadata_json for the given run_id, merges the new
        keys, and writes back. Operates on the row with the latest created_at
        for that run_id (the END event row if duplicates exist).

        Args:
            run_id: The run identifier to update.
            metadata: Dict of key-value pairs to merge into metadata_json.
        """
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT id, metadata_json FROM traces WHERE run_id = ? "
                    "ORDER BY created_at DESC LIMIT 1",
                    [run_id],
                ).fetchone()
                if row is None:
                    return
                existing = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
                existing.update(metadata)
                conn.execute(
                    "UPDATE traces SET metadata_json = ? WHERE id = ?",
                    [json.dumps(existing), row["id"]],
                )
        except Exception:
            logger.debug("TracingProxy: merge_metadata failed for run_id=%s", run_id, exc_info=True)

    # ─── Read Helpers ─────────────────────────────────────────────────────────

    def list_runs(
        self,
        page: int = 1,
        page_size: int = PAGE_SIZE_DEFAULT,
        slug: str = "",
        model: str = "",
        date_from: str = "",
        date_to: str = "",
        trace_id: str = "",
    ) -> list[dict]:
        """Return a paginated list of runs.

        Without trace_id, returns only root runs (parent_run_id IS NULL).
        With trace_id, returns the root run and all direct children so the
        trace page is non-empty while a worker is still active.

        Args:
            page: 1-based page number.
            page_size: Number of rows per page.
            slug: Filter on name containing this substring (case-insensitive).
            model: Filter on model column containing this model string (case-insensitive).
            date_from: ISO date string lower bound for created_at (inclusive).
            date_to: ISO date string upper bound for created_at (inclusive).
            trace_id: Exact trace UUID. When provided, returns the root run and
                its direct children (run_id = ? OR parent_run_id = ?).

        Returns:
            List of row dicts ordered by created_at descending.
        """
        conditions: list[str] = []
        params: list = []

        if trace_id:
            conditions.append("(run_id = ? OR parent_run_id = ?)")
            params.extend([trace_id, trace_id])
        else:
            conditions.append("parent_run_id IS NULL")

        if slug:
            conditions.append("name LIKE ?")
            params.append(f"%{slug}%")
        if model:
            conditions.append("LOWER(model) LIKE LOWER(?)")
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
        trace_id: str = "",
    ) -> int:
        """Return total count of runs matching the given filters.

        Uses the same filter logic as list_runs but returns only the count.
        Without trace_id, counts only root runs (parent_run_id IS NULL).
        With trace_id, counts the root run and all direct children.
        """
        conditions: list[str] = []
        params: list = []

        if trace_id:
            conditions.append("(run_id = ? OR parent_run_id = ?)")
            params.extend([trace_id, trace_id])
        else:
            conditions.append("parent_run_id IS NULL")

        if slug:
            conditions.append("name LIKE ?")
            params.append(f"%{slug}%")
        if model:
            conditions.append("LOWER(model) LIKE LOWER(?)")
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

    def get_children_batch(self, run_ids: list[str]) -> dict[str, list[dict]]:
        """Return direct child runs grouped by parent_run_id.

        Uses a single SQL query with an IN clause to avoid N+1 queries.

        Args:
            run_ids: List of parent run identifiers.

        Returns:
            Dict mapping each parent run_id to its list of child run dicts,
            ordered by start_time ascending within each group.
        """
        if not run_ids:
            return {}
        placeholders = ",".join("?" for _ in run_ids)
        sql = f"""
            SELECT * FROM traces
            WHERE parent_run_id IN ({placeholders})
            ORDER BY parent_run_id, start_time ASC
        """
        with self._connect() as conn:
            rows = conn.execute(sql, run_ids).fetchall()
        result: dict[str, list[dict]] = {}
        for row in rows:
            row_dict = dict(row)
            parent_id = row_dict["parent_run_id"]
            result.setdefault(parent_id, []).append(row_dict)
        return result

    # ─── Cost Analysis Queries ────────────────────────────────────────────────

    def get_cost_summary(self) -> CostSummary:
        """Return aggregate cost figures for the analysis page summary cards.

        Queries cost data from traces.metadata_json for execute_task and
        validate_task runs that carry a total_cost_usd field.

        Returns:
            CostSummary with all-time, today, and this-week totals plus the
            most expensive slug and its cost.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        week_start = datetime.now(timezone.utc).strftime("%Y-%W")  # ISO year-week

        sql = """
            SELECT
                COALESCE(SUM(json_extract(metadata_json, '$.total_cost_usd')), 0.0) AS total,
                COALESCE(SUM(CASE
                    WHEN substr(created_at, 1, 10) = :today
                    THEN json_extract(metadata_json, '$.total_cost_usd')
                    ELSE 0.0 END), 0.0) AS today_total,
                COALESCE(SUM(CASE
                    WHEN strftime('%Y-%W', created_at) = :week_start
                    THEN json_extract(metadata_json, '$.total_cost_usd')
                    ELSE 0.0 END), 0.0) AS week_total
            FROM traces
            WHERE json_extract(metadata_json, '$.total_cost_usd') IS NOT NULL
        """
        slug_sql = """
            SELECT
                json_extract(metadata_json, '$.item_slug') AS slug,
                COALESCE(SUM(json_extract(metadata_json, '$.total_cost_usd')), 0.0) AS slug_total
            FROM traces
            WHERE json_extract(metadata_json, '$.item_slug') IS NOT NULL
              AND json_extract(metadata_json, '$.total_cost_usd') IS NOT NULL
            GROUP BY slug
            ORDER BY slug_total DESC
            LIMIT 1
        """
        with self._connect() as conn:
            row = conn.execute(sql, {"today": today, "week_start": week_start}).fetchone()
            slug_row = conn.execute(slug_sql).fetchone()

        total = float(row["total"]) if row else 0.0
        today_total = float(row["today_total"]) if row else 0.0
        week_total = float(row["week_total"]) if row else 0.0
        most_expensive_slug = slug_row["slug"] if slug_row else ""
        most_expensive_slug_cost = float(slug_row["slug_total"]) if slug_row else 0.0

        return CostSummary(
            total_cost_usd=total,
            today_cost_usd=today_total,
            week_cost_usd=week_total,
            most_expensive_slug=most_expensive_slug,
            most_expensive_slug_cost_usd=most_expensive_slug_cost,
        )

    def get_cost_by_day(self, days: int = 30) -> list[DailyCost]:
        """Return daily cost totals for the past N days, for a bar chart.

        Args:
            days: Number of calendar days to look back (default 30).

        Returns:
            List of DailyCost ordered by date ascending.
        """
        sql = """
            SELECT
                substr(created_at, 1, 10) AS date_str,
                COALESCE(SUM(json_extract(metadata_json, '$.total_cost_usd')), 0.0) AS cost_usd
            FROM traces
            WHERE json_extract(metadata_json, '$.total_cost_usd') IS NOT NULL
              AND created_at >= datetime('now', :offset)
            GROUP BY date_str
            ORDER BY date_str ASC
        """
        offset = f"-{days} days"
        with self._connect() as conn:
            rows = conn.execute(sql, {"offset": offset}).fetchall()
        return [DailyCost(date_str=row["date_str"], cost_usd=float(row["cost_usd"])) for row in rows]

    def list_cost_runs(
        self,
        page: int = 1,
        page_size: int = PAGE_SIZE_DEFAULT,
        slug: Optional[str] = None,
        item_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        sort: str = COST_SORT_INCLUSIVE_DESC,
    ) -> tuple[list[CostRun], int]:
        """Return a paginated list of cost-bearing trace runs with inclusive cost.

        Inclusive cost is computed via a correlated sub-query containing a recursive
        CTE that sums total_cost_usd across the run and all its descendants.

        Args:
            page: 1-based page number.
            page_size: Rows per page.
            slug: Optional substring filter on item_slug (case-insensitive).
            item_type: Optional exact filter on item_type.
            date_from: Optional ISO date lower bound on created_at (inclusive).
            date_to: Optional ISO date upper bound on created_at (inclusive).
            sort: Sort order — one of the COST_SORT_* constants.

        Returns:
            Tuple of (rows, total_count).
        """
        conditions, params = self._cost_run_filters(slug, item_type, date_from, date_to)
        where = " AND ".join(conditions) if conditions else "1"
        order_by = self._cost_run_order_by(sort)
        offset = (page - 1) * page_size

        sql = f"""
            SELECT
                run_id,
                name,
                COALESCE(model, json_extract(metadata_json, '$.model'), '') AS model,
                COALESCE(json_extract(metadata_json, '$.item_slug'), '') AS item_slug,
                COALESCE(json_extract(metadata_json, '$.item_type'), '') AS item_type,
                COALESCE(json_extract(metadata_json, '$.total_cost_usd'), 0.0) AS exclusive_cost_usd,
                (
                    WITH RECURSIVE subtree(rid, cost) AS (
                        SELECT run_id,
                               COALESCE(json_extract(metadata_json, '$.total_cost_usd'), 0.0)
                        FROM traces AS inner_t
                        WHERE inner_t.run_id = traces.run_id
                        UNION ALL
                        SELECT t2.run_id,
                               COALESCE(json_extract(t2.metadata_json, '$.total_cost_usd'), 0.0)
                        FROM traces AS t2
                        JOIN subtree ON t2.parent_run_id = subtree.rid
                    )
                    SELECT COALESCE(SUM(cost), 0.0) FROM subtree
                ) AS inclusive_cost_usd,
                COALESCE(json_extract(metadata_json, '$.input_tokens'), 0) AS input_tokens,
                COALESCE(json_extract(metadata_json, '$.output_tokens'), 0) AS output_tokens,
                COALESCE(json_extract(metadata_json, '$.duration_ms'), 0) AS duration_ms,
                created_at
            FROM traces
            WHERE {where}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
        """

        count_sql = f"""
            SELECT COUNT(*) FROM traces WHERE {where}
        """

        count_params = list(params)
        params.extend([page_size, offset])

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            total = conn.execute(count_sql, count_params).fetchone()[0]

        cost_runs = [
            CostRun(
                run_id=row["run_id"],
                name=row["name"],
                model=row["model"] or "",
                item_slug=row["item_slug"] or "",
                item_type=row["item_type"] or "",
                exclusive_cost_usd=float(row["exclusive_cost_usd"]),
                inclusive_cost_usd=float(row["inclusive_cost_usd"]),
                input_tokens=int(row["input_tokens"]),
                output_tokens=int(row["output_tokens"]),
                duration_ms=int(row["duration_ms"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]
        return cost_runs, total

    def get_cost_by_slug(self) -> list[SlugCost]:
        """Return cost aggregated by work-item slug, ordered by total cost descending.

        Returns:
            List of SlugCost, one entry per distinct item_slug.
        """
        sql = """
            SELECT
                COALESCE(json_extract(metadata_json, '$.item_slug'), '') AS item_slug,
                COALESCE(json_extract(metadata_json, '$.item_type'), '') AS item_type,
                COALESCE(SUM(json_extract(metadata_json, '$.total_cost_usd')), 0.0) AS total_cost_usd,
                COUNT(*) AS task_count,
                COALESCE(AVG(json_extract(metadata_json, '$.total_cost_usd')), 0.0) AS avg_cost_usd
            FROM traces
            WHERE json_extract(metadata_json, '$.item_slug') IS NOT NULL
              AND json_extract(metadata_json, '$.total_cost_usd') IS NOT NULL
            GROUP BY item_slug, item_type
            ORDER BY total_cost_usd DESC
        """
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [
            SlugCost(
                item_slug=row["item_slug"],
                item_type=row["item_type"],
                total_cost_usd=float(row["total_cost_usd"]),
                task_count=int(row["task_count"]),
                avg_cost_usd=float(row["avg_cost_usd"]),
            )
            for row in rows
        ]

    def get_cost_by_node_type(self) -> list[NodeCost]:
        """Return cost aggregated by node/run name (e.g. execute_task, validate_task).

        Returns:
            List of NodeCost ordered by total cost descending.
        """
        sql = """
            SELECT
                name AS node_name,
                COUNT(*) AS task_count,
                COALESCE(SUM(json_extract(metadata_json, '$.total_cost_usd')), 0.0) AS total_cost_usd,
                COALESCE(AVG(json_extract(metadata_json, '$.total_cost_usd')), 0.0) AS avg_cost_usd
            FROM traces
            WHERE json_extract(metadata_json, '$.total_cost_usd') IS NOT NULL
            GROUP BY name
            ORDER BY total_cost_usd DESC
        """
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [
            NodeCost(
                node_name=row["node_name"],
                task_count=int(row["task_count"]),
                total_cost_usd=float(row["total_cost_usd"]),
                avg_cost_usd=float(row["avg_cost_usd"]),
            )
            for row in rows
        ]

    def get_tool_call_attribution(self) -> list[ToolCallCost]:
        """Return per-tool-call cost estimates, proportional to result_bytes within each task.

        For each cost_tasks row with a non-empty tool_calls_json, parses the JSON list and
        distributes the task's cost_usd across tool calls proportionally by result_bytes.
        Tool calls with no result_bytes receive no attribution and are excluded.

        Returns:
            List of ToolCallCost ordered by estimated_cost_usd descending, capped at
            TOP_TOOL_CALLS_LIMIT entries.
        """
        sql = """
            SELECT item_slug, task_id, cost_usd, tool_calls_json
            FROM cost_tasks
            WHERE tool_calls_json IS NOT NULL
        """
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()

        results: list[ToolCallCost] = []
        for row in rows:
            tool_calls = self._parse_tool_calls_json(row["tool_calls_json"])
            if not tool_calls:
                continue
            sum_bytes = sum(int(tc.get("result_bytes", 0)) for tc in tool_calls)
            if sum_bytes == 0:
                continue
            task_cost = float(row["cost_usd"])
            for tc in tool_calls:
                result_bytes = int(tc.get("result_bytes", 0))
                if result_bytes == 0:
                    continue
                estimated_cost = (result_bytes / sum_bytes) * task_cost
                results.append(
                    ToolCallCost(
                        tool_name=tc.get("tool", ""),
                        detail=self._tool_call_detail(tc),
                        result_bytes=result_bytes,
                        estimated_cost_usd=estimated_cost,
                        item_slug=row["item_slug"],
                        task_id=row["task_id"],
                    )
                )

        results.sort(key=lambda tc: tc.estimated_cost_usd, reverse=True)
        return results[:TOP_TOOL_CALLS_LIMIT]

    def _parse_tool_calls_json(self, tool_calls_json: str) -> list[dict]:
        """Parse a tool_calls_json string; returns an empty list on any error.

        Args:
            tool_calls_json: JSON string from the cost_tasks.tool_calls_json column.

        Returns:
            Parsed list of tool call dicts, or [] if the value is missing or invalid.
        """
        try:
            parsed = json.loads(tool_calls_json)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    def _tool_call_detail(self, tool_call: dict) -> str:
        """Extract a human-readable detail string from a tool call dict.

        Args:
            tool_call: A single tool call dict with optional file_path and command keys.

        Returns:
            file_path for Read/Edit/Write calls, truncated command for Bash,
            pattern for Grep/Glob, or empty string when none apply.
        """
        file_path: str = tool_call.get("file_path", "")
        if file_path:
            return file_path
        command: str = tool_call.get("command", "")
        if command:
            return command[:BASH_COMMAND_PREVIEW_LENGTH]
        return ""

    def _cost_run_filters(
        self,
        slug: Optional[str],
        item_type: Optional[str],
        date_from: Optional[str],
        date_to: Optional[str],
    ) -> tuple[list[str], list]:
        """Build WHERE conditions and params for list_cost_runs queries.

        Only rows that carry a total_cost_usd in metadata_json are included.

        Args:
            slug: Substring filter on item_slug (case-insensitive).
            item_type: Exact filter on item_type.
            date_from: ISO date lower bound on created_at.
            date_to: ISO date upper bound on created_at.

        Returns:
            Tuple of (conditions list, params list).
        """
        conditions = ["json_extract(metadata_json, '$.total_cost_usd') IS NOT NULL"]
        params: list = []
        if slug:
            conditions.append("json_extract(metadata_json, '$.item_slug') LIKE ?")
            params.append(f"%{slug}%")
        if item_type:
            conditions.append("json_extract(metadata_json, '$.item_type') = ?")
            params.append(item_type)
        if date_from:
            conditions.append("created_at >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("created_at <= ?")
            params.append(date_to)
        return conditions, params

    def get_slug_cost_runs(self) -> dict[str, list["CostRun"]]:
        """Return all cost-bearing runs with an item_slug, grouped by slug.

        Used to populate expandable row detail in the Cost by Work Item table.
        Inclusive cost is not computed here — exclusive cost only.

        Returns:
            Dict mapping item_slug to a list of CostRun ordered by exclusive
            cost descending.
        """
        sql = """
            SELECT
                run_id,
                name,
                COALESCE(model, json_extract(metadata_json, '$.model'), '') AS model,
                COALESCE(json_extract(metadata_json, '$.item_slug'), '') AS item_slug,
                COALESCE(json_extract(metadata_json, '$.item_type'), '') AS item_type,
                COALESCE(json_extract(metadata_json, '$.total_cost_usd'), 0.0) AS exclusive_cost_usd,
                COALESCE(json_extract(metadata_json, '$.input_tokens'), 0) AS input_tokens,
                COALESCE(json_extract(metadata_json, '$.output_tokens'), 0) AS output_tokens,
                COALESCE(json_extract(metadata_json, '$.duration_ms'), 0) AS duration_ms,
                created_at
            FROM traces
            WHERE json_extract(metadata_json, '$.item_slug') IS NOT NULL
              AND json_extract(metadata_json, '$.total_cost_usd') IS NOT NULL
            ORDER BY item_slug, exclusive_cost_usd DESC
        """
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()

        result: dict[str, list[CostRun]] = {}
        for row in rows:
            slug = row["item_slug"]
            run = CostRun(
                run_id=row["run_id"],
                name=row["name"],
                model=row["model"] or "",
                item_slug=slug,
                item_type=row["item_type"] or "",
                exclusive_cost_usd=float(row["exclusive_cost_usd"]),
                inclusive_cost_usd=0.0,
                input_tokens=int(row["input_tokens"]),
                output_tokens=int(row["output_tokens"]),
                duration_ms=int(row["duration_ms"]),
                created_at=row["created_at"],
            )
            if slug not in result:
                result[slug] = []
            result[slug].append(run)
        return result

    def _cost_run_order_by(self, sort: str) -> str:
        """Map a sort constant to a SQL ORDER BY clause for list_cost_runs.

        Args:
            sort: One of the COST_SORT_* constants.

        Returns:
            SQL ORDER BY fragment (without the ORDER BY keyword).
        """
        order_map = {
            COST_SORT_INCLUSIVE_DESC: "inclusive_cost_usd DESC",
            COST_SORT_EXCLUSIVE_DESC: "exclusive_cost_usd DESC",
            COST_SORT_DATE_DESC: "created_at DESC",
        }
        return order_map.get(sort, "inclusive_cost_usd DESC")


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
