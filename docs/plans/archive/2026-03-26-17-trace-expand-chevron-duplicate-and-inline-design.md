# Design: Trace Detail — Fix Expand Chevron Duplicate and Inline Subrun Content

## Summary

Two bugs in `proxy_trace.html`'s grandchild-toggle section:

1. **Duplicate chevron**: The `.grandchild-toggle summary` element lacks CSS to suppress the
   browser's native disclosure widget (`::marker` / `-webkit-details-marker`). The global rule
   `details[open] > summary::before { content: "▼"; }` fires on open, adding a second glyph
   alongside the still-visible native `▶` marker.

2. **Link instead of inline details**: The expanded content renders only a navigation link to
   `/proxy/{child_run_id}`. The child run data (name, duration, inputs/outputs, error) should
   be shown inline without requiring page navigation.

## Root Cause

The `.row-details summary` class correctly uses `list-style: none` + `-webkit-details-marker: none`
to suppress the native marker. The `.grandchild-toggle summary` has no equivalent rules, so both
the native marker and the `::before` pseudo-element render when the `<details>` is open.

The inline content was never implemented — the template just emits a hyperlink.

## Architecture

### Files to Modify

| File | Change |
|---|---|
| `langgraph_pipeline/web/static/style.css` | Add `.grandchild-toggle summary` rules to suppress native marker and add closed-state `::before` chevron |
| `langgraph_pipeline/web/proxy.py` | Add `get_children_batch(run_ids)` method returning `dict[str, list[dict]]` |
| `langgraph_pipeline/web/routes/proxy.py` | Fetch and enrich grandchildren in `proxy_trace`; pass `grandchildren_by_parent` to template |
| `langgraph_pipeline/web/templates/proxy_trace.html` | Replace hyperlink with inline detail panel (name, duration, elapsed, inputs/outputs, error) |

### CSS Fix

```css
.grandchild-toggle summary {
    list-style: none;
    cursor: pointer;
}
.grandchild-toggle summary::-webkit-details-marker { display: none; }
.grandchild-toggle summary::before { content: "▶ "; font-size: 9px; color: #aaa; }
```

The existing global `details[open] > summary::before { content: "▼"; }` handles the open state.

### Data Pipeline

Add to `TracingProxy`:

```python
def get_children_batch(self, run_ids: list[str]) -> dict[str, list[dict]]:
    """Return direct child runs grouped by parent_run_id."""
```

Update `proxy_trace` route: call `get_children_batch(child_ids)`, enrich each grandchild with
`_enrich_run`, and pass `grandchildren_by_parent: dict[str, list[dict]]` to the template.

### Template Inline Panel

For each child with grandchildren, show a collapsible `<details>` containing:
- A row per grandchild: name, duration, elapsed start offset
- Collapsible inputs/outputs JSON blocks (`<details class="json-block">`)
- Error text if present

No navigation link; all data pre-loaded from the route.

## Design Decisions

- **Single batch query** for grandchildren avoids N+1 queries per page load.
- **Enrich grandchildren** in the route (reuse `_enrich_run`) so the template receives
  `display_duration` and other pre-computed fields.
- **CSS scoped** to `.grandchild-toggle` to avoid breaking `.row-details` or `.json-block`
  disclosure styling.
- Nested expand (great-grandchildren) is out of scope; the panel shows a count + link if
  a grandchild itself has children.
