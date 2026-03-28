# Traces: duplicate start/end events showing as separate rows

## Summary

Each pipeline node appears twice in the traces DB — once for the start
event (end_time=NULL) and once for the end event (end_time set). The list
page shows both, doubling the number of rows. Duration shows 0.01s or
0.00s for rows that represent full pipeline runs.

## Acceptance Criteria

- Does the traces list show exactly ONE row per root trace (not two)?
  YES = pass, NO = fail
- Does each row show the REAL duration from the end event (minutes, not
  0.01s)? YES = pass, NO = fail
- Is the upsert implemented in record_run so start events are updated
  in-place when the end event arrives? YES = pass, NO = fail

## LangSmith Trace: 3e8ff155-b2ba-45bc-9f64-8847677fd97c


## 5 Whys Analysis

**Title:** Traces list duplicates rows because start/end events are stored separately instead of being consolidated

**Clarity:** 4/5 (Clear problem statement and acceptance criteria; some context needed on the record_run function)

**5 Whys:**

1. **Why does the traces list show duplicate rows for each pipeline execution?**
   → Because the database stores two rows per trace: one for the start event (end_time=NULL) and one for the end event (end_time set).

2. **Why are start and end events being stored as separate rows instead of consolidated into one?**
   → Because the `record_run` function currently uses INSERT to create new rows for each event, rather than UPSERT to update the existing start row when the end event arrives.

3. **Why was INSERT chosen over UPSERT in the initial implementation?**
   → Because the system was designed to capture a full event log of all pipeline lifecycle events sequentially, without optimizing for how the UI should present this data (one row per execution).

4. **Why does the system need to record both start and end events at all?**
   → To track the complete execution lifecycle (start time, end time, duration) and enable real-time progress monitoring. However, the final display only needs the end state with accurate duration.

5. **Why is it critical to update the start row in-place rather than leaving both rows?**
   → Because the traces list must show exactly one row per execution with the real final duration (minutes, not 0.01s), and duplicate rows inflate counts and show incorrect timing data.

**Root Need:** The traces data model must treat each pipeline execution as a single evolving entity (updated via upsert) rather than an event log (append-only rows), so the UI can display accurate execution metadata without deduplication.

**Summary:** The system stores start/end events as separate rows; migrating `record_run` to use upsert will consolidate them into single rows with accurate duration.
