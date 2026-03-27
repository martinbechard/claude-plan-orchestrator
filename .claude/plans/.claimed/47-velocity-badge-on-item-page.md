# Show average velocity (tokens/min) as a badge next to pipeline stage on item page

## Summary

When viewing a work item on /item/<slug>, the average token velocity during
execution should be displayed as a tag/badge next to the pipeline stage
status (e.g. "executing" | "2.4k tok/min"). This value comes from the
active worker's current_velocity or from the completions table for finished
items. This same velocity value drives the colour of the dashboard timeline
bars in velocity mode.

## Acceptance Criteria

- Does the item detail page show a velocity badge (e.g. "2.4k tok/min")
  next to the pipeline stage when a worker is active?
  YES = pass, NO = fail
- For completed items, does the badge show the final average velocity
  from the completion record? YES = pass, NO = fail
- Is the velocity value consistent with what the dashboard timeline
  shows for the same item in velocity colour mode?
  YES = pass, NO = fail

## LangSmith Trace: 3299899e-dcbd-49c3-a8c4-8d597a156496


## 5 Whys Analysis

I appreciate the brainstorming skill context, but your request is more specific: you've asked for a **5 Whys root cause analysis** of an already well-defined backlog item, not for me to brainstorm or design something new. The backlog item is concrete with clear acceptance criteria. Let me execute that analysis as requested:

---

**Title:** Enable real-time execution performance visibility at the item level

**Clarity:** 4 out of 5
(Clear what to build and where; acceptance criteria are specific. Minor gap: assumes understanding of why velocity matters for user decisions.)

**5 Whys:**

1. **Why show a velocity badge next to pipeline stage on the item page?**
   Because users viewing an item's detail page need to see execution speed alongside status—it's the natural place users look when they drill down into a specific work item.

2. **Why is execution speed visibility specifically at the item-detail level important?**
   Because when users navigate to an item page, they're investigating that particular execution. Showing velocity there provides real-time performance context without requiring them to cross-reference the dashboard.

3. **Why do users need real-time performance context during an active run?**
   Because degraded performance (slowdown, bottleneck) isn't visible until completion if users only check afterward. Real-time visibility allows detection of problems *while the run is still executing*.

4. **Why is detecting problems during execution (not after) valuable?**
   Because it enables intervention—users can stop, adjust, or investigate inefficient runs before they consume more resources. Post-run detection only informs future decisions; real-time detection enables present action.

5. **Why is the ability to intervene during execution a priority?**
   Because pipeline execution consumes resources (compute, tokens, time). Users have financial and operational incentives to avoid wasting resources on slow/degraded runs, and want assurance their work is executing efficiently rather than wastefully.

**Root Need:** Users need real-time execution efficiency visibility during active pipeline runs so they can make cost-conscious intervention decisions (continue, stop, adjust) rather than discovering suboptimal performance only after completion.

**Summary:** The velocity badge serves as an efficiency alarm—enabling users to catch and respond to performance degradation during execution, not after.
