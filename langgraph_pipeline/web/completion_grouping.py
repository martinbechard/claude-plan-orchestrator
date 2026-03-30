# langgraph_pipeline/web/completion_grouping.py
# Pure grouping utility that consolidates flat completion rows by slug.
# Design: docs/plans/2026-03-30-81-dashboard-group-retries-per-item-design-1-systems.md

"""Completion grouping logic for the dashboard SSE feed.

Provides a single pure function that transforms a flat list of completion
dicts (sorted by finished_at DESC) into a grouped list where each slug
appears exactly once, with retry history nested inside.
"""

# ─── Constants ────────────────────────────────────────────────────────────────

MAX_GROUPED_COMPLETIONS = 20

# Fields preserved on each retry entry. item_type, tokens_per_minute, and
# verification_notes are omitted — they are redundant for sub-rows (same item
# type; notes belong to the final attempt only).
RETRY_FIELDS = ("outcome", "cost_usd", "duration_s", "finished_at", "run_id")


# ─── Public API ───────────────────────────────────────────────────────────────


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
        limit: Maximum number of grouped entries to return. Applied to the
            number of distinct slugs, not the number of raw rows.

    Returns:
        List of grouped completion dicts, ordered by the primary entry's
        finished_at descending. Each dict contains:
        - All fields from the primary (most recent) completion.
        - attempt_count (int): Total executions for this slug (1 = no retries).
        - retries (list[dict]): Prior attempts, oldest first. Each retry dict
          contains: outcome, cost_usd, duration_s, finished_at, run_id.
    """
    seen_order: list[str] = []
    groups: dict[str, list[dict]] = {}

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
        primary = dict(rows[0])
        retries_raw = rows[1:]
        primary["attempt_count"] = len(rows)
        primary["retries"] = [
            {field: r[field] for field in RETRY_FIELDS}
            for r in reversed(retries_raw)
        ]
        result.append(primary)

    return result
