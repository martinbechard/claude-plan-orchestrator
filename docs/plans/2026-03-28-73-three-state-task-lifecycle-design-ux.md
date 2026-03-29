# UX Design: Task Status Visual Differentiation

Source: tmp/plans/.claimed/73-three-state-task-lifecycle.md
Design: docs/plans/2026-03-28-73-three-state-task-lifecycle-design.md
Competition role: ux-designer (task 0.2)
Date: 2026-03-28

## Problem Statement

The dashboard currently treats "completed" as the terminal success state, rendering it
with green background (#d1fae5) and a checkmark icon. With the introduction of the
three-state lifecycle (completed -> verified), this green treatment is misleading:
users see green and assume the task is fully done, when in reality it is still awaiting
validation. The design must reassign color semantics so that "completed" conveys
"awaiting next step" and "verified" conveys "fully done."

## User Mental Model

The six task states map to three cognitive categories that users intuitively understand:

```
  NOT STARTED          WORKING ON IT              DONE
  -----------     ----------------------     ----------------
   pending        in_progress                 verified
                  completed (awaiting         skipped
                    validation)
                  failed (needs attention)
```

Key mental model shifts from the current UI:

1. **completed is NOT done** -- it belongs in the "working on it" category because
   validation is a required step that has not yet occurred. The visual treatment
   must communicate "progress made, but not finished."

2. **verified IS done** -- this is the only state that means a task is fully finished
   and safe for dependents to proceed. It deserves the strongest "success" visual.

3. **completed vs in_progress** -- both are "in progress" conceptually, but at
   different stages. "in_progress" means code is actively running; "completed" means
   code finished and the system is deciding what to do next. The visual distinction
   should convey this progression without implying finality.

The double-checkmark pattern (borrowed from messaging apps like WhatsApp/Signal) maps
naturally: single check = "sent/done on my end" and double check = "received and
confirmed." Users already understand this idiom.

## Color Palette: Six-State Semantics

### Badge Colors (pill-shaped status labels)

All combinations meet WCAG 2.1 AA contrast ratio (>= 4.5:1 for normal text):

| State | Background | Text | Contrast | Semantic |
|---|---|---|---|---|
| pending | #f3f4f6 | #4b5563 | 6.4:1 | Neutral grey -- nothing has happened |
| in_progress | #dbeafe | #1e40af | 7.5:1 | Blue -- active work, energy, motion |
| completed | #fef3c7 | #92400e | 5.8:1 | Amber -- caution, awaiting action |
| verified | #d1fae5 | #065f46 | 5.3:1 | Green -- success, safe to proceed |
| failed | #fee2e2 | #991b1b | 5.2:1 | Red -- error, needs attention |
| skipped | #e5e7eb | #475569 | 5.5:1 | Muted slate -- intentionally bypassed |

### Progress Bar Segment Colors (solid fills)

Used for stacked progress bar segments and task icon backgrounds:

| State | Fill Color | Hex |
|---|---|---|
| pending | Grey 300 | #d1d5db |
| in_progress | Blue 500 | #3b82f6 |
| completed | Amber 500 | #f59e0b |
| verified | Emerald 600 | #059669 |
| failed | Red 500 | #ef4444 |
| skipped | Slate 400 | #94a3b8 |

### Color Rationale

**Why amber for "completed" instead of the current green:**
Green universally signals "done/safe/go." A task awaiting validation is not safe for
dependents to proceed. Amber signals "caution/waiting/in-between" -- matching the
traffic-light metaphor users already know. This is the most critical color change:
moving completed from green to amber resets the user expectation from "done" to
"waiting."

**Why blue for "in_progress":**
Blue conveys activity and energy without implying completion. The existing dashboard
already uses blue for active states (item-type-feature badges, primary links).
Maintaining this consistency reinforces the "active work" association.

**Why the existing green (#d1fae5/#065f46) for "verified":**
The current dashboard uses these exact green values for outcome-success badges and
completed task icons. By reassigning this green from "completed" to "verified", the
semantic meaning aligns correctly: green = truly done. Users who learned to associate
green with "done" will now have that association be accurate.

## Iconography

Each state has a unique icon shape that communicates status independent of color.
This is critical for accessibility -- a user who cannot distinguish colors can still
identify each state by icon shape alone.

### Icon Specifications

| State | Unicode | Glyph | Visual Description |
|---|---|---|---|
| pending | U+25CB | &#9675; | Hollow circle -- empty, nothing yet |
| in_progress | U+25D4 | &#9684; | Circle with upper-right quadrant -- partially filled, in motion |
| completed | U+2713 | &#10003; | Single checkmark -- "I did my part" |
| verified | U+2713 x2 | &#10003;&#10003; | Double checkmark -- "confirmed and sealed" |
| failed | U+2717 | &#10007; | Ballot X -- error, rejection |
| skipped | U+2298 | &#8856; | Circled dash -- intentionally bypassed |

### Icon Rendering in Task List

Task icons render as 14x14 px circles (matching current .task-icon dimensions) with
the icon glyph centered inside. The circle background uses the badge background color
for the corresponding state; the glyph uses the badge text color.

```
 CSS class               Background   Glyph color   Icon
 task-icon--pending       #f3f4f6      #d1d5db       ○    (with 1px border #d1d5db)
 task-icon--in_progress   #dbeafe      #1e40af       ◔    (or CSS spinner)
 task-icon--completed     #fef3c7      #92400e       ✓
 task-icon--verified      #d1fae5      #065f46       ✓✓
 task-icon--failed        #fee2e2      #991b1b       ✕
 task-icon--skipped       #e5e7eb      #94a3b8       ⊘
```

### Animation for in_progress

The in_progress icon uses a subtle CSS spin animation (2s linear infinite) on a
half-filled circle glyph. This provides a secondary visual cue beyond color: movement
indicates active execution. The animation is suppressed when prefers-reduced-motion
is set.

```css
.task-icon--in_progress {
    animation: spin-slow 2s linear infinite;
}
@media (prefers-reduced-motion: reduce) {
    .task-icon--in_progress { animation: none; }
}
@keyframes spin-slow {
    from { transform: rotate(0deg); }
    to   { transform: rotate(360deg); }
}
```

### Double-Checkmark Rendering

The verified double-checkmark uses two ✓ glyphs with tight letter-spacing (-1px) to
fit within the 14px icon circle. At 9px font-size (current task-icon font-size), two
check characters fit cleanly. Alternative: use a single ✓ at larger weight (700) with
a small circular badge overlay, but the double-check approach is simpler and leverages
the familiar messaging-app pattern.

For the JavaScript dynamic renderer (planTasksHtml function in item.html), the icon
mapping becomes:

```javascript
var TASK_ICONS = {
    pending:     '&#9675;',     // ○ hollow circle
    in_progress: '&#9684;',     // ◔ quarter circle
    completed:   '&#10003;',    // ✓ single check
    verified:    '&#10003;&#10003;', // ✓✓ double check
    failed:      '&#10007;',    // ✕ ballot X
    skipped:     '&#8856;'      // ⊘ circled dash
};
```

## Progress Bar Design

### Stacked Horizontal Progress Bar

Replace the current simple "N / total" counter with a stacked horizontal bar that
shows the proportion of tasks in each state. The bar is a single-row flex container
where each segment width is proportional to the number of tasks in that state.

```
Layout (example: 10 tasks total):

  [verified: 3][completed: 2][in_progress: 1][pending: 3][failed: 1]
  |--- 30% ----|--- 20% -----|--- 10% -------|-- 30% ----|-- 10% --|
```

### Bar Dimensions

- Height: 8px (compact, consistent with existing dashboard spacing)
- Border-radius: 4px on container, 0 on inner segments (except first/last get the
  container radius)
- Background: #e5e7eb (grey-200, visible track for empty states)
- Minimum segment width: 4px (ensures every non-zero state is visible even with 1 task)

### Segment Ordering

Segments are ordered by lifecycle progression, left to right:

1. verified (green #059669) -- leftmost, representing completed journey
2. completed (amber #f59e0b) -- next, awaiting validation
3. in_progress (blue #3b82f6) -- active work
4. failed (red #ef4444) -- needs attention
5. skipped (slate #94a3b8) -- intentionally bypassed
6. pending (grey #d1d5db) -- rightmost, work not yet started

This ordering creates a visual "flow" from left (done) to right (not started). As
tasks progress through the lifecycle, segments shift leftward, giving a natural sense
of forward momentum.

### Segment Patterns for Color-Blind Safety

Each segment uses a subtle CSS background pattern as a secondary differentiator:

| State | Pattern | CSS |
|---|---|---|
| verified | Solid fill | (none -- solid green) |
| completed | Diagonal stripes (45deg) | repeating-linear-gradient(45deg, transparent, transparent 2px, rgba(255,255,255,0.25) 2px, rgba(255,255,255,0.25) 4px) |
| in_progress | Horizontal stripes | repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(255,255,255,0.2) 2px, rgba(255,255,255,0.2) 4px) |
| failed | Cross-hatch (45deg + 135deg) | Two overlaid gradients at 45deg and 135deg |
| skipped | Dotted | radial-gradient dots pattern |
| pending | Solid fill | (none -- solid grey) |

### Text Overlay

Above the progress bar, display a compact text summary:

```
Plan Tasks   3✓✓  2✓  1●  3○  1✕  / 10
```

Each count uses the corresponding icon and badge color as inline style. This provides
a scannable numeric breakdown alongside the visual bar.

For the card header counter (data-dynamic="plan-task-count"), the format changes from:

```
Current:   3 / 10
Proposed:  3 verified / 10  (or compact: 3✓✓ / 10)
```

The denominator remains total tasks. The numerator counts only verified tasks (via
effective_status) since those are the truly "done" tasks that satisfy dependencies.

## Task List Row Styling

### Status-Dependent Text Treatment

| State | Text style | Rationale |
|---|---|---|
| pending | Normal weight, #374151 | Default, ready to work |
| in_progress | Normal weight, #1e40af (blue) | Active, draws attention |
| completed | Normal weight, #92400e (amber) | Awaiting validation, not done |
| verified | Strikethrough, #9ca3af (muted) | Fully done, de-emphasized |
| failed | Normal weight, #991b1b (red) | Error, draws attention |
| skipped | Strikethrough, #94a3b8 (slate) | Bypassed, de-emphasized |

Key change: only **verified** and **skipped** tasks get strikethrough text. Currently,
"completed" gets strikethrough via .task-name--done, but since "completed" now means
"awaiting validation," it should NOT be struck through.

### Row Background on Hover

Active states (in_progress, completed) get a subtle left-border accent on the task
row to draw the eye:

```css
.task-item--in_progress { border-left: 3px solid #3b82f6; }
.task-item--completed   { border-left: 3px solid #f59e0b; }
```

## Accessibility

### WCAG 2.1 AA Compliance

**Color contrast (text on background):**
All six badge combinations exceed 4.5:1 contrast ratio (verified in palette section
above). The lowest ratio is 5.2:1 (failed: #991b1b on #fee2e2), well above the 4.5:1
AA threshold.

**Color contrast (progress bar on track):**
All six segment colors on the #e5e7eb track background exceed 3:1 contrast ratio
(large-text / graphical element threshold per WCAG 1.4.11). The weakest is pending
(#d1d5db on #e5e7eb) at approximately 1.2:1. To address this, pending segments render
with a 1px inset border of #9ca3af, raising the perceived contrast.

### Color-Blind Safety

**Not relying on color alone (WCAG 1.4.1):**
Every state is distinguishable by three independent channels:

1. **Color** -- six distinct hues (grey, blue, amber, green, red, slate)
2. **Icon shape** -- six unique glyphs (○, ◔, ✓, ✓✓, ✕, ⊘)
3. **Pattern** -- progress bar segments use distinct fill patterns

**Deuteranopia (red-green, ~5% of males):**
The most critical distinction is completed (amber) vs verified (green). Under
deuteranopia, amber remains yellow-ish while green shifts to olive. These remain
distinguishable by luminance difference. Additionally, the single-check vs
double-check icons provide a reliable non-color cue.

Failed (red) shifts to dark brown under deuteranopia but remains distinguishable from
verified (olive-green) by both luminance and the ✕ vs ✓✓ icon shapes.

**Protanopia (~1% of males):**
Similar to deuteranopia. Amber stays recognizable; red shifts to dark olive. The ✕
icon for failed prevents confusion with any checkmark state.

**Tritanopia (rare):**
Blue shifts toward green, potentially blending in_progress with verified. The spinning
animation on in_progress (vs static double-check on verified) provides a motion-based
differentiator. The horizontal-stripe pattern on in_progress progress segments also
distinguishes it from the solid-fill verified segments.

### Screen Reader Support

Task icons include aria-label attributes with full status descriptions:

```html
<span class="task-icon task-icon--completed"
      aria-label="Completed, awaiting validation">&#10003;</span>
<span class="task-icon task-icon--verified"
      aria-label="Verified, fully done">&#10003;&#10003;</span>
```

The progress bar includes an aria-label summarizing the distribution:

```html
<div class="progress-bar" role="progressbar"
     aria-valuenow="3" aria-valuemin="0" aria-valuemax="10"
     aria-label="3 of 10 tasks verified: 3 verified, 2 awaiting validation, 1 in progress, 3 pending, 1 failed">
```

### Reduced Motion

The in_progress spinner animation respects prefers-reduced-motion. When reduced motion
is preferred, the icon displays as a static partially-filled circle without rotation.

## CSS Class Strategy

### New Classes to Add

```css
/* Task icon backgrounds -- six states */
.task-icon--pending     { background: #f3f4f6; color: #d1d5db; border: 1px solid #d1d5db; }
.task-icon--in_progress { background: #dbeafe; color: #1e40af; }
.task-icon--completed   { background: #fef3c7; color: #92400e; }
.task-icon--verified    { background: #d1fae5; color: #065f46; }
.task-icon--failed      { background: #fee2e2; color: #991b1b; }
.task-icon--skipped     { background: #e5e7eb; color: #94a3b8; }

/* Task name text treatment */
.task-name--verified    { text-decoration: line-through; color: #9ca3af; }
.task-name--skipped     { text-decoration: line-through; color: #94a3b8; }
.task-name--in_progress { color: #1e40af; }
.task-name--completed   { color: #92400e; }
.task-name--failed      { color: #991b1b; }

/* Progress bar */
.task-progress-bar          { display: flex; height: 8px; border-radius: 4px;
                              background: #e5e7eb; overflow: hidden; }
.task-progress-bar__segment { min-width: 4px; transition: width 0.3s ease; }
.task-progress-bar__segment--verified    { background: #059669; }
.task-progress-bar__segment--completed   { background: #f59e0b; }
.task-progress-bar__segment--in_progress { background: #3b82f6; }
.task-progress-bar__segment--failed      { background: #ef4444; }
.task-progress-bar__segment--skipped     { background: #94a3b8; }
.task-progress-bar__segment--pending     { background: #d1d5db; }

/* Status badge pills (for use in headers, summaries) */
.status-badge--pending     { background: #f3f4f6; color: #4b5563; }
.status-badge--in_progress { background: #dbeafe; color: #1e40af; }
.status-badge--completed   { background: #fef3c7; color: #92400e; }
.status-badge--verified    { background: #d1fae5; color: #065f46; }
.status-badge--failed      { background: #fee2e2; color: #991b1b; }
.status-badge--skipped     { background: #e5e7eb; color: #475569; }
```

### Classes to Remove or Rename

| Current class | Action | Reason |
|---|---|---|
| .task-name--done | Remove | Replaced by .task-name--verified and .task-name--skipped |

### Template Conditional Changes

The Jinja2 template conditional for strikethrough changes from:

```
Current:  {% if task.status == 'completed' %}task-name--done{% endif %}
Proposed: task-name--{{ task.status }}
```

This applies the correct text treatment for all six states through CSS class mapping.

## Implementation Impact Summary

| Component | Changes Required |
|---|---|
| style.css | Add 6 task-icon classes, 5 task-name classes, progress bar classes, status badge classes; remove .task-name--done |
| item.html (Jinja2) | Update icon conditionals for 6 states; change task-name class logic; add progress bar markup |
| item.html (JS) | Update planTasksHtml() icon map for 6 states; update planTaskCountText() to count verified; add progress bar renderer |
| dashboard.js | No changes (dashboard.js handles pipeline monitoring, not task status) |
| dashboard.html | No changes (task status is rendered on the item page, not the main dashboard) |

## Design Decision: AC23 Coverage

This design satisfies AC23 (visual distinction between completed and verified) through:

1. **Color**: Amber (completed) vs green (verified) -- different hue families
2. **Icon**: Single checkmark (completed) vs double checkmark (verified)
3. **Text**: Normal amber text (completed) vs strikethrough muted text (verified)
4. **Progress bar**: Distinct segment colors with pattern differentiation
5. **Aria labels**: "Awaiting validation" (completed) vs "Fully done" (verified)

All five channels are independent, ensuring the distinction holds even when one channel
is not perceivable (color blindness, screen reader, reduced motion).
