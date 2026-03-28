# Traces list: remove redundant "Item slug" column

## Summary

The "Item slug" column repeats the Run name when they're the same (which
is always, after fixing the LangGraph naming). Remove this column.

## Acceptance Criteria

- Is the "Item slug" column removed from the traces table?
  YES = pass, NO = fail
- Does the table have: Trace ID, Run name, Start time, Duration, Cost,
  Model, Status — and nothing redundant? YES = pass, NO = fail

## LangSmith Trace: 0a44a12d-df9d-4e97-85cc-ad1c38619de2


## 5 Whys Analysis

Title: Remove redundant "Item slug" column from traces list
Clarity: 4
5 Whys:
1. Why is the "Item slug" column now redundant? — Because after the LangGraph naming fix, the item slug always matches the Run name exactly, making it duplicate information on the same row.

2. Why did they previously differ? — Because LangGraph node names were not aligned with the item slug/run name convention; the naming systems were inconsistent and could diverge.

3. Why wasn't LangGraph naming aligned with item slug/run name from the start? — Because the data model evolved without a unified naming strategy—different components (LangGraph, item slug, run name) added their own naming conventions independently.

4. Why did multiple naming systems develop in parallel? — Because the system grew organically without an upfront architectural decision about a single source of truth for what a "run" is called across all layers.

5. Why remove the column now instead of leaving it for potential future use? — Because redundant columns confuse users (ambiguity about which value to trust), waste valuable table space, and signal that the data model still has inconsistencies when it's now actually unified.

Root Need: Simplify the traces UI to reflect the corrected, unified naming model and reduce cognitive load on users reviewing trace metadata.

Summary: Remove visual redundancy to match the now-unified naming convention and improve traces table clarity.
