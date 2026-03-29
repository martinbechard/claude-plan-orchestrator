# Systems Design: Dashboard Task Status Visual Differentiation

Design: docs/plans/2026-03-28-73-three-state-task-lifecycle-design.md (D6)
Requirements: docs/plans/2026-03-28-73-three-state-task-lifecycle-requirements.md
Work Item: tmp/plans/.claimed/73-three-state-task-lifecycle.md
Target ACs: AC21, AC22, AC23
Date: 2026-03-28

## Problem Statement

The dashboard currently treats "completed" as the terminal success state for visual
rendering. With the introduction of "verified" (D1), the UI must visually distinguish
tasks that finished execution (awaiting validation) from tasks that are fully done
(validated or validation not applicable). The current five-status rendering pipeline
must expand to six statuses while maintaining backward compatibility via effective_status.

## Architecture Overview

The task status rendering pipeline has two parallel paths that must stay synchronized:

```
YAML Plan File
    |
    v
_load_plan_tasks()          (item.py:509-554)
    |                        Reads task.status from YAML sections
    v                        Returns [{id, name, status, agent}, ...]
    |
    +--------> Jinja2 template (item.html:1098-1114)     [server-side, initial render]
    |          task-icon--{status} CSS class
    |          Icon glyph selection via if/elif chain
    |          Progress counter via selectattr filter
    |
    +--------> planTasksHtml() (item.html:1524-1549)     [client-side, 10s polling]
               task-icon--{status} CSS class
               Icon glyph selection via if/else chain
               planTaskCountText() for progress counter
```

Both paths read the raw YAML status value and apply identical rendering logic. Any
change to status rendering must be applied to BOTH paths.

## Data Flow: Status to Pixels

### Layer 1: State Definition (executor/state.py)

Current (D1 will change this):
```
TaskStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]
```

After D1:
```
TaskStatus = Literal["pending", "in_progress", "completed", "verified", "failed", "skipped"]
```

The effective_status() helper (D2) is a read-time transformation used by dependency
resolution and progress counting in the executor. The dashboard does NOT need to call
effective_status because it reads the stored YAML status directly. By the time a task
reaches "verified" in the YAML, it is definitively verified. The backward-compatibility
concern (legacy plans with "completed" meaning "done") is handled by effective_status
in the executor nodes, not in the UI layer.

### Layer 2: YAML Loading (web/routes/item.py)

The _load_plan_tasks() function (line 509) reads raw status from YAML:
```python
"status": task.get("status", "pending"),
```

No changes needed here. The function already passes through whatever status value is
stored in the YAML. When tasks are set to "verified" by the validator node, that value
will flow through unchanged.

### Layer 3: Dynamic API Endpoint (web/routes/item.py)

The /item/{slug}/dynamic endpoint (line 193) returns plan_tasks as JSON. No changes
needed -- it already serializes whatever _load_plan_tasks returns.

### Layer 4: Server-Side Rendering (Jinja2)

Location: web/templates/item.html

#### 4a. Task Icon CSS Class (line 1102)

Current:
```html
<span class="task-icon task-icon--{{ task.status }}" ...>
```

No change needed to this pattern. The CSS class is derived dynamically from the status
value. Adding "verified" to the CSS means adding a new .task-icon--verified rule.

#### 4b. Icon Glyph Selection (lines 1104-1107)

Current:
```jinja2
{% if task.status == 'completed' %}&#10003;
{% elif task.status == 'in_progress' %}&#9679;
{% elif task.status == 'skipped' %}&mdash;
{% else %}&nbsp;{% endif %}
```

Must add a branch for "verified" with a distinct glyph. The "failed" status currently
falls through to the else branch (empty space) -- this should also get a dedicated glyph
for completeness.

#### 4c. Task Name Strikethrough (line 1109)

Current:
```jinja2
<span class="task-name {% if task.status == 'completed' %}task-name--done{% endif %}">
```

Both "completed" and "verified" tasks should show the done styling. "Verified" is fully
done; "completed" is execution-done (still visually distinguished from pending/in_progress).
The condition should match both statuses.

#### 4d. Progress Counter (lines 1091-1094)

Current Jinja2:
```jinja2
{{ plan_tasks | selectattr('status', 'equalto', 'completed') | list | length }}
/ {{ plan_tasks | length }}
```

This counts only "completed" as done. After D1/D5, progress counting must align with the
new semantics:
- "verified" = fully done (always counts)
- "completed" = execution done, awaiting validation (counts toward progress since user
  expects to see forward movement when a task finishes executing)

The counter should sum both "completed" and "verified" tasks. This gives users accurate
feedback: they see the counter increment when a task finishes executing, not only after
validation completes. The alternative (counting only "verified") would cause a confusing
gap where a task appears done (checkmark icon) but the counter hasn't incremented.

### Layer 5: Client-Side Rendering (JavaScript)

Location: web/templates/item.html (inline script)

#### 5a. planTasksHtml() (lines 1524-1549)

Must mirror all Jinja2 changes:
- Add "verified" icon glyph branch
- Add "failed" icon glyph branch
- Apply task-name--done for both "completed" and "verified"

#### 5b. planTaskCountText() (lines 1552-1558)

Current:
```javascript
if (tasks[i].status === 'completed') { completed++; }
```

Must count both "completed" and "verified" tasks, matching the Jinja2 counter logic.

### Layer 6: CSS Class Definitions

Location: web/templates/item.html (inline style block, lines 426-442)

Current classes defined:
```
.task-icon--completed   (green background, dark green text)
.task-icon--pending     (gray background, light gray text, border)
.task-icon--in_progress (yellow background, amber text)
.task-icon--skipped     (gray background, medium gray text)
```

Missing: .task-icon--failed (currently falls through to no styling)

Required additions:
- .task-icon--verified  (new terminal success state)
- .task-icon--failed    (was always missing, should be added for completeness)

## CSS Class Mapping Strategy for Six States

Each status maps to a CSS class, icon glyph, and semantic meaning:

| Status       | CSS Class              | Semantic Category | Visual Role                      |
|-------------|------------------------|-------------------|----------------------------------|
| pending     | task-icon--pending     | Not started       | Neutral/empty, awaiting start    |
| in_progress | task-icon--in_progress | Active            | Draws attention, currently running|
| completed   | task-icon--completed   | Intermediate done | Execution finished, more to come |
| verified    | task-icon--verified    | Terminal success  | Fully done, nothing remaining    |
| failed      | task-icon--failed      | Terminal failure  | Error state, needs attention     |
| skipped     | task-icon--skipped     | Terminal neutral  | Deliberately bypassed            |

### Color Semantics

The color system must:
1. Differentiate "completed" (intermediate) from "verified" (terminal) at a glance
2. Use color-blind safe combinations (WCAG 2.1 AA)
3. Preserve existing color meanings where possible

Proposed color strategy (specific hex values deferred to UX design):

- **pending**: Gray (unchanged) -- neutral, inactive
- **in_progress**: Yellow/amber (unchanged) -- active, attention
- **completed**: Blue or teal -- indicates "done but in transit" (distinct from green)
- **verified**: Green (inherits current completed green) -- terminal success
- **failed**: Red -- error state (was missing, now explicit)
- **skipped**: Gray (unchanged) -- neutral, bypassed

The key insight: current "completed" green (#d1fae5/#065f46) should migrate to "verified"
since green universally means "done." The "completed" (awaiting validation) state needs a
different color to convey "in progress toward done" -- blue or teal is the natural choice,
as it sits between the active yellow and the terminal green on the semantic spectrum.

### Icon Glyph Strategy

| Status       | Glyph        | Unicode   | Rationale                                     |
|-------------|-------------|-----------|-----------------------------------------------|
| pending     | (empty)     | &nbsp;    | No action taken (unchanged)                   |
| in_progress | filled dot  | &#9679;   | Active indicator (unchanged)                  |
| completed   | checkmark   | &#10003;  | Execution done (retain familiar glyph)        |
| verified    | double check| &#10003;&#10003; or shield | Conveys extra confirmation   |
| failed      | cross       | &#10007;  | Error indicator                               |
| skipped     | dash        | &mdash;   | Bypassed (unchanged)                          |

The glyph choice for "verified" must fit in a 15x15px box at 9px font-weight-700.
Options: double checkmark (may be too wide), filled checkmark with circle, shield icon,
or a single bold checkmark with distinct color. The UX design will finalize.

## Progress Bar and Task Count Integration

### Backend Progress String (edges.py)

The _tasks_completed_str() function (line 120) counts completed tasks for routing
decisions within the executor LangGraph. After D5, this will use effective_status to
count "verified" as done. This is internal to the executor and does NOT affect the
dashboard directly.

### Dashboard Progress Counter

The dashboard progress counter (Jinja2 + JS) is independent of the executor's progress
counting. It reads raw YAML status values, not effective_status. The counter formula:

```
numerator = count(status in {"completed", "verified"})
denominator = count(all tasks)
display = "{numerator} / {denominator}"
```

Both "completed" and "verified" increment the numerator because:
1. Users expect to see forward movement when a task finishes executing
2. The icon and color already distinguish the two states visually
3. Showing "3/12" when 3 tasks have executed (even if not yet validated) is more
   intuitive than "0/12" when the user can see 3 checkmarks in the task list

### Future: Segmented Progress Bar

If a segmented/visual progress bar is added (currently only a text counter exists),
each segment should be colored by status:
- Green segments for verified tasks
- Blue/teal segments for completed (awaiting validation) tasks
- Red segments for failed tasks
- Yellow segments for in_progress tasks
- Gray segments for pending/skipped tasks

This creates a visual timeline of plan progress where the color gradient shifts from
left (gray/yellow) to right (blue/green) as execution proceeds.

## Backward Compatibility

### Legacy Plans

Plans created before the "verified" status exists will have tasks with status
"completed" meaning "fully done." The dashboard renders whatever status value it reads
from YAML. For these legacy plans:
- "completed" tasks render with the "completed" visual treatment (blue/teal, not green)
- This is cosmetically different from the old green but functionally correct
- No migration is needed because effective_status handles the semantic interpretation
  in the executor layer

If visual parity with old behavior is desired for legacy plans, the _load_plan_tasks()
function could apply effective_status before passing to templates. However, this adds
complexity and is not recommended -- legacy plans are historical artifacts and the slight
visual change is acceptable.

### Dashboard Main Page

The main dashboard page (dashboard.html + dashboard.js) does NOT show per-task statuses.
It shows item-level outcomes (success/warn/fail) via CompletionRecord. No changes needed
to the main dashboard page for this feature.

## Files to Modify

| File | Changes Required |
|------|-----------------|
| web/templates/item.html (CSS) | Add .task-icon--verified and .task-icon--failed classes |
| web/templates/item.html (Jinja2) | Add verified/failed glyph branches, update done condition, update progress counter |
| web/templates/item.html (JS planTasksHtml) | Mirror Jinja2 icon/glyph changes |
| web/templates/item.html (JS planTaskCountText) | Count both completed and verified |

All changes are confined to a single file (item.html) because the task status rendering
is fully contained in the inline styles and scripts of that template. No changes needed
to style.css, dashboard.js, or dashboard.html.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Jinja2 and JS renderers diverge | Visual flicker on first poll refresh | Code review checklist: verify both paths match |
| 15px icon box too small for double checkmark | Glyph overflow or illegibility | Use single glyph with distinct color; UX design validates |
| Color-blind users cannot distinguish completed/verified | Accessibility failure | Use shape+color redundancy (different glyphs) not just color |
| Legacy plans show different color for "completed" | Minor visual regression | Acceptable trade-off; no migration needed |

## Testing Strategy

1. **Visual inspection**: Render item page with a plan containing all six statuses
2. **Jinja2/JS parity**: Verify initial server render matches first JS refresh
3. **Progress counter**: Plan with mix of completed/verified tasks shows correct count
4. **Color contrast**: Verify WCAG 2.1 AA contrast ratios for all six status colors
5. **Browser compatibility**: Test in Chrome, Firefox, Safari (vanilla JS, no transpilation)
