# Systems Design: Completion Grouping Data Model and Query Layer

Design competition entry for task 0.1 of feature 81.
Parent design: docs/plans/2026-03-30-81-dashboard-group-retries-per-item-design.md
Work item: tmp/plans/.claimed/81-dashboard-group-retries-per-item.md

## Problem Statement

When an item is retried (e.g. outcome=warn followed by outcome=success), the dashboard
completions table shows separate rows for each attempt. Users perceive these as duplicate
entries. The system needs a grouping layer that consolidates rows sharing the same slug
into a single top-level entry with the final outcome, exposing retry history on demand.

## Architecture Overview

The grouping layer sits between the data sources (SQLite via TracingProxy, in-memory
CompletionRecord list) and the SSE snapshot serialiser. A single pure function
transforms flat completion lists into grouped completion lists. Both the proxy path
and the in-memory fallback path call this function, ensuring identical grouping
semantics regardless of data source.

```
                        +-------------------+
                        |   SQLite (proxy)  |
                        | list_completions()|
                        +---------+---------+
                                  |
                                  v
                   +-----------------------------+
                   | group_completions_by_slug() |  <-- shared utility
                   +-----------------------------+
                                  ^
                                  |
                  +---------------+---------------+
                  |                               |
       +----------+----------+       +-----------+-----------+
       | TracingProxy         |       | DashboardState        |
       | list_completions     |       | recent_completions    |
       | _grouped()           |       | (in-memory fallback)  |
       +----------------------+       +-----------------------+
                  |                               |
                  +---------------+---------------+
                                  |
                                  v
                   +-----------------------------+
                   | DashboardState.snapshot()   |
                   | recent_completions: grouped |
                   +-----------------------------+
                                  |
                                  v
                   +-----------------------------+
                   | SSE /api/stream             |
                   | event: state                |
                   +-----------------------------+
                                  |
                                  v
                   +-----------------------------+
                   | dashboard.js                |
                   | renderCompletions()         |
                   +-----------------------------+
```

## D1: Grouped Completions Query in TracingProxy

### Current State

`TracingProxy.list_completions()` (proxy.py:588-628) runs:

```sql
SELECT slug, item_type, outcome, cost_usd, duration_s, finished_at, run_id,
       tokens_per_minute, verification_notes
FROM completions
ORDER BY finished_at DESC
LIMIT ? OFFSET ?
```

This returns a flat list of dicts. When a slug has multiple completions (retries),
each appears as a separate row.

### New Method: list_completions_grouped()

Add a new method `list_completions_grouped()` to `TracingProxy`. This method is
purpose-built for the dashboard SSE feed; the existing `list_completions()` remains
unchanged for the /completions paginated page.

#### Query Strategy

Use the same `SELECT ... ORDER BY finished_at DESC` query as `list_completions()`,
but without pagination filters (the dashboard only shows recent completions, not
paginated results). The limit should be generous enough to capture retries --
use `COMPLETIONS_LIMIT * 3` as the row cap to account for items with multiple
retries while bounding memory.

Post-process in Python rather than using complex SQL (GROUP BY with subqueries
or window functions). This keeps the query simple, the grouping logic testable
in isolation, and avoids SQLite-specific syntax.

#### Post-Processing

Pass the flat row list to `group_completions_by_slug()` (the shared utility
described in the section below). The utility returns grouped entries limited
to the desired count.

#### Method Signature

```python
def list_completions_grouped(self, limit: int = COMPLETIONS_LIMIT) -> list[dict]:
    """Return completions grouped by slug for the dashboard SSE feed.

    Queries recent completions and groups rows sharing the same slug.
    For each slug, the most recent completion becomes the primary entry;
    older completions become the retries list.

    Args:
        limit: Maximum number of grouped entries to return.

    Returns:
        List of grouped completion dicts. Each dict has the standard
        completion fields for the primary (most recent) attempt, plus:
        - attempt_count: Total number of completions for this slug.
        - retries: List of prior-attempt dicts (oldest first), each with
          outcome, cost_usd, duration_s, finished_at, run_id.
    """
```

#### Implementation Outline

```python
GROUPED_QUERY_MULTIPLIER = 3

def list_completions_grouped(self, limit: int = COMPLETIONS_LIMIT) -> list[dict]:
    sql = """
        SELECT slug, item_type, outcome, cost_usd, duration_s, finished_at,
               run_id, tokens_per_minute, verification_notes
        FROM completions
        ORDER BY finished_at DESC
        LIMIT ?
    """
    with self._connect() as conn:
        rows = conn.execute(sql, [limit * GROUPED_QUERY_MULTIPLIER]).fetchall()
    flat = [dict(row) for row in rows]
    return group_completions_by_slug(flat, limit)
```

### Why Not SQL-Level Grouping?

SQL GROUP BY collapses rows into aggregates, losing per-row detail needed for
the retries list. Window functions (ROW_NUMBER() OVER PARTITION BY slug) could
identify the primary row, but building the retries array still requires
post-processing. Keeping all logic in Python:

- Is testable without a database
- Works identically for the in-memory fallback
- Avoids coupling to SQLite-specific SQL features
- Keeps the query plan simple (single table scan with ORDER BY on an indexed column)

## D2: In-Memory Grouping Fallback in dashboard_state.py

### Current State

When the proxy is unavailable, `DashboardState.snapshot()` (dashboard_state.py:303-318)
converts `self.recent_completions` (a list of `CompletionRecord` dataclass instances)
into a list of dicts:

```python
completions_list = [
    {
        "slug": c.slug,
        "item_type": c.item_type,
        "outcome": c.outcome,
        "cost_usd": c.cost_usd,
        "duration_s": c.duration_s,
        "finished_at": c.finished_at,
        "run_id": c.run_id,
    }
    for c in self.recent_completions
]
```

### Change

After converting to dicts, pass the list through the same
`group_completions_by_slug()` utility:

```python
flat_list = [
    {
        "slug": c.slug,
        "item_type": c.item_type,
        "outcome": c.outcome,
        "cost_usd": c.cost_usd,
        "duration_s": c.duration_s,
        "finished_at": c.finished_at,
        "run_id": c.run_id,
    }
    for c in self.recent_completions
]
completions_list = group_completions_by_slug(flat_list)
```

The proxy path also changes from `proxy.list_completions()` to
`proxy.list_completions_grouped()`:

```python
if proxy is not None:
    completions_list = proxy.list_completions_grouped()
else:
    # in-memory fallback with grouping
    flat_list = [...]
    completions_list = group_completions_by_slug(flat_list)
```

### Thread Safety

The grouping utility receives a list of plain dicts (copied from dataclass
fields under the lock). It performs no mutation of the input list -- it builds
new dicts for the output. The lock scope does not change.

## Shared Grouping Utility: group_completions_by_slug()

### Location

New file: `langgraph_pipeline/web/completion_grouping.py`

A dedicated module keeps the utility importable by both `proxy.py` and
`dashboard_state.py` without creating a circular import. The file is small
(under 60 lines) and has a single responsibility.

### Interface

```python
RETRY_FIELDS = ("outcome", "cost_usd", "duration_s", "finished_at", "run_id")

def group_completions_by_slug(
    completions: list[dict],
    limit: int = MAX_GROUPED_COMPLETIONS,
) -> list[dict]:
    """Group a flat list of completion dicts by slug.

    The input list MUST be sorted by finished_at descending (most recent first).
    For each unique slug, the first occurrence (most recent) becomes the primary
    entry. All subsequent occurrences become retries, listed oldest-first.

    Args:
        completions: Flat list of completion dicts sorted by finished_at DESC.
            Each dict must have at least: slug, item_type, outcome, cost_usd,
            duration_s, finished_at, run_id.
        limit: Maximum number of grouped entries to return.

    Returns:
        List of grouped completion dicts, ordered by the primary entry's
        finished_at descending. Each dict contains:
        - All fields from the primary (most recent) completion.
        - attempt_count (int): Total executions for this slug (1 = no retries).
        - retries (list[dict]): Prior attempts, oldest first. Each retry dict
          contains: outcome, cost_usd, duration_s, finished_at, run_id.
    """
```

### Algorithm

```python
def group_completions_by_slug(
    completions: list[dict],
    limit: int = MAX_GROUPED_COMPLETIONS,
) -> list[dict]:
    seen_order: list[str] = []            # preserves first-seen (most-recent) order
    groups: dict[str, list[dict]] = {}    # slug -> [row0 (newest), row1, ...]

    for row in completions:
        slug = row["slug"]
        if slug not in groups:
            seen_order.append(slug)
            groups[slug] = []
        groups[slug].append(row)

    result: list[dict] = []
    for slug in seen_order:
        if len(result) >= limit:
            break
        rows = groups[slug]
        primary = dict(rows[0])                        # shallow copy
        retries_raw = rows[1:]                         # older attempts
        primary["attempt_count"] = len(rows)
        primary["retries"] = [
            {field: r[field] for field in RETRY_FIELDS}
            for r in reversed(retries_raw)             # oldest first
        ]
        result.append(primary)

    return result
```

### Key Design Choices

1. **Input precondition: sorted by finished_at DESC.** Both callers (proxy query
   and in-memory list) already maintain this order. The function does not re-sort,
   keeping it O(n) rather than O(n log n).

2. **Retries listed oldest-first.** This matches chronological reading order when
   the user expands the retry history: "first attempt, second attempt, ..., final
   (shown in primary row)."

3. **Retry dicts contain only RETRY_FIELDS.** Sub-rows need outcome, cost, duration,
   timestamp, and trace link. Fields like item_type, tokens_per_minute, and
   verification_notes are redundant for retries (same item type; notes belong to
   the final attempt). This keeps the SSE payload lean.

4. **attempt_count is always present.** Even for items with no retries,
   `attempt_count=1` and `retries=[]`. This gives the frontend a single code
   path: check `attempt_count > 1` to decide whether to render the toggle.

5. **limit applied to grouped entries, not raw rows.** If limit=20, the result
   contains up to 20 unique slugs, each with all their retries. The proxy
   over-fetches raw rows (limit * 3) to ensure enough data for grouping.

## SSE Payload Shape Change

### Before (flat)

```json
{
  "recent_completions": [
    {
      "slug": "79-worker-cost-zero",
      "item_type": "defect",
      "outcome": "success",
      "cost_usd": 0.42,
      "duration_s": 185.3,
      "finished_at": 1743350400.0,
      "run_id": "abc-123"
    },
    {
      "slug": "79-worker-cost-zero",
      "item_type": "defect",
      "outcome": "warn",
      "cost_usd": 0.31,
      "duration_s": 120.7,
      "finished_at": 1743349800.0,
      "run_id": "def-456"
    }
  ]
}
```

### After (grouped)

```json
{
  "recent_completions": [
    {
      "slug": "79-worker-cost-zero",
      "item_type": "defect",
      "outcome": "success",
      "cost_usd": 0.42,
      "duration_s": 185.3,
      "finished_at": 1743350400.0,
      "run_id": "abc-123",
      "attempt_count": 2,
      "retries": [
        {
          "outcome": "warn",
          "cost_usd": 0.31,
          "duration_s": 120.7,
          "finished_at": 1743349800.0,
          "run_id": "def-456"
        }
      ]
    }
  ]
}
```

### Backward Compatibility

The SSE feed is consumed only by dashboard.js in the same deployment. There is
no external API contract. The frontend will be updated in the same feature branch,
so no backward-compatibility shim is needed.

New fields added:
- `attempt_count` (int): Always present. 1 for single-attempt items.
- `retries` (list): Always present. Empty list for single-attempt items.

Existing fields remain unchanged on the primary entry. The frontend can
safely access `c.attempt_count` and `c.retries` without version checks.

## File Impact Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `langgraph_pipeline/web/completion_grouping.py` | NEW | Shared `group_completions_by_slug()` utility |
| `langgraph_pipeline/web/proxy.py` | MODIFY | Add `list_completions_grouped()` method |
| `langgraph_pipeline/web/dashboard_state.py` | MODIFY | Call grouped method / apply grouping to fallback |
| `tests/test_completion_grouping.py` | NEW | Unit tests for the grouping utility |

## Test Strategy

### Unit Tests for group_completions_by_slug()

The utility is a pure function operating on plain dicts, making it trivially
testable without database fixtures or mocking.

Test cases:

1. **Empty list** -> returns empty list
2. **Single item, no retries** -> returns one entry with attempt_count=1, retries=[]
3. **Two rows same slug** -> returns one entry with attempt_count=2, retries has one dict
4. **Three rows same slug** -> retries list has two dicts, oldest first
5. **Mixed slugs** -> each slug grouped independently, order preserved by first-seen
6. **Limit applied** -> with limit=2 and 5 unique slugs, only first 2 returned
7. **Retry dict contains only RETRY_FIELDS** -> no item_type, tokens_per_minute leakage

### Integration Tests for list_completions_grouped()

Use an in-memory SQLite database with the completions table schema.

1. Insert multiple rows with same slug, different finished_at -> verify grouping
2. Insert rows with different slugs -> verify independent grouping
3. Verify limit parameter caps the result

### Snapshot Integration

Verify `DashboardState.snapshot()` returns grouped entries:

1. Add two completions with same slug via `remove_active_worker()`
2. Call `snapshot()` with proxy=None (in-memory path)
3. Assert the result has one entry with attempt_count=2

## Design Decision Rationale

### Why a new file instead of adding to proxy.py?

`proxy.py` is already large (700+ lines). The grouping utility is used by
both proxy.py and dashboard_state.py. Placing it in either creates a
directional dependency. A separate `completion_grouping.py` module:
- Avoids circular imports
- Keeps proxy.py focused on database operations
- Keeps dashboard_state.py focused on state management
- Makes the grouping logic independently testable

### Why not group at the database level?

SQLite supports GROUP BY and window functions, but:
- GROUP BY loses per-row detail needed for the retries list
- Window functions (ROW_NUMBER) identify primaries but still need Python to
  build the retries array
- Post-processing in Python works for both the proxy path and the in-memory path
- The grouping function is testable without a database

### Why over-fetch rows from the database?

The dashboard shows up to 20 grouped entries (COMPLETIONS_LIMIT = 20). If we
fetch exactly 20 rows, a slug with 3 retries would consume 3 of those 20 slots,
yielding fewer than 20 groups. Fetching `limit * 3` rows ensures enough data
for grouping even in heavy-retry scenarios. The multiplier 3 is conservative:
most items have 1-2 retries; the maximum retry count is 3 (max_attempts in
the pipeline YAML).

### Why retries oldest-first?

Chronological order matches the natural reading direction for a history
timeline: "first attempt failed, second attempt warned, third attempt
succeeded (shown in primary row)." This avoids cognitive reversal when
scanning the expanded retry rows.

## AC Coverage

| AC | How This Design Addresses It |
|----|------------------------------|
| AC1 | group_completions_by_slug() consolidates rows with the same slug into one entry |
| AC2 | The primary entry is the most recent (first in DESC order), showing the final outcome |
| AC3 | Prior attempts are nested in the retries list, never shown as top-level rows |
| AC4 | Primary record's outcome badge is the prominent status (unchanged rendering) |
| AC5 | attempt_count field enables the frontend to show a retry count badge without interaction |
| AC6 | retries list provides the data for expandable sub-rows (frontend concern, D4) |
| AC7 | retries are data-only; the frontend controls visibility (collapsed by default, D4) |
| AC8 | Each retry dict includes outcome, cost_usd, duration_s, finished_at for sub-row display |
