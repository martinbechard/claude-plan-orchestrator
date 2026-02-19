# Chapter 15: The Loop That Wouldn't Stop

**Period:** 2026-02-19
**Size:** ~30 lines changed in `auto-pipeline.py`, new `force_pipeline_exit()` function, `completed_items` circuit breaker

## Three Seconds Per Cycle

The first sign of trouble was a log that repeated every three seconds:

```
Phase 2: Plan already fully completed - skipping orchestrator
Phase 3: Verifying symptoms...
Phase 4: Archiving...
[ARCHIVE] Already archived, skipping: docs/completed-backlog/features/17-...
Item complete: feature: 17 Read Only Analysis Task Workflow (0m 0s)
```

Feature 17 was done. Its plan was completed. Its destination file existed in the completed backlog. The archive step confirmed this. And then the scanner found it again, because it was still sitting in `docs/feature-backlog/`.

The bug was on a single line. `archive_item()` had an early return for the "already archived" case: if the destination file existed, log a message and return True. The problem: returning True without removing the source file. The normal archive path used `shutil.move`, which deletes the source as a side effect of moving it. The "already archived" path skipped the move entirely, because the destination was already there, and nobody had thought to ask whether the source was still there too.

The result was a three-second infinite loop. Process the item. Archive says "already done." Scanner finds the item. Process the item. Archive says "already done." The human had to kill the process manually.

## How an Item Gets Stuck

The scenario that produces a duplicate --- source and destination both existing --- is not exotic. It happens whenever an archive partially succeeds. The most common path: `shutil.move` copies the file to the destination, then the subsequent `git commit` of the move fails (perhaps because another process committed in the interim), and the exception handler returns False. The source file was copied but never deleted. On the next cycle, the destination exists, the source exists, and the early return kicks in.

It can also happen if someone manually copies a file to the completed directory without removing the original. Or if a previous pipeline session archived the file but crashed before committing the removal.

The point is: two copies of the same file is a state the system must handle, and "log a message and move on" is not handling it.

## The Fix: Remove the Source

The archive function now checks whether the source file still exists when the destination is already present, and removes it. The removal is committed to git so the state is clean for future runs. If the removal fails --- permissions, filesystem error, whatever --- the function returns False, which tells the caller the item is stuck and shouldn't be retried.

But returning False only prevents the retry within a single call to `process_item()`. The outer loop calls `scan_all_backlogs()` again, finds the file again, and tries again. The `failed_items` set catches failures, but only failures: `process_item` returning True (which it does when archive succeeds) doesn't add anything to the exclusion set.

## The Circuit Breaker

A new set, `completed_items`, tracks items that `process_item` returned True for. The scanner filters out both `failed_items` and `completed_items`, so an item that completed successfully but whose source file persists in the backlog directory will never be processed twice in the same session.

This is defense in depth. The archive fix prevents the specific bug. The circuit breaker prevents the class of bugs: any scenario where `process_item` returns True but the backlog file survives.

## The Emergency Exit

While building the circuit breaker, a broader question surfaced: what should happen when the pipeline detects an unrecoverable state? The archive failure case is one example, but there are others. What if the plan YAML is corrupted? What if the orchestrator binary is missing? What if a git operation leaves the repository in a state that no amount of retrying will fix?

Before this fix, each of these cases handled its own exit differently. Some returned False and hoped the caller would stop. Some logged a warning and continued. None of them created the stop semaphore, and none of them notified Slack.

`force_pipeline_exit()` is now the single function for unrecoverable errors. It does three things:

1. Creates the stop semaphore file so a restarted pipeline also halts immediately
2. Sends a Slack error notification if Slack is available
3. Calls `sys.exit()` to terminate the process

A module-level `_active_slack` reference, set once by the main entry point, gives the function access to the Slack notifier without requiring every intermediate call site to thread a slack parameter through its signature. The `send_status` method is already a no-op when Slack is disabled, so there's no conditional logic needed.

The archive failure path is the first caller. Others will follow as they're identified. The pattern is simple: if you detect a state that will cause infinite looping or data corruption, call `force_pipeline_exit(reason)` and let the human sort it out.

## What This Is Really About

The pipeline had been running for weeks without this bug manifesting, because the normal archive path works correctly. The bug required a specific precondition --- destination exists, source not deleted --- that only arises when something else has already gone partially wrong.

But "only arises when something else has already gone wrong" is exactly the condition under which you need the system to behave correctly. A pipeline that works perfectly when everything is fine and enters an infinite loop the moment something goes sideways is a pipeline that will eventually eat all your API credits at 2 AM.

The deeper lesson is about the relationship between success and cleanup. `process_item` returning True means "I finished processing this item." It does not mean "the item will never appear in the backlog again." Conflating task completion with state cleanup is a category error, and the infinite loop is the symptom. The circuit breaker makes the distinction explicit: completion is tracked independently of whether the filesystem reflects it.

## Verification

- `archive_item()` removes stale source file when destination exists; returns False on removal failure
- `completed_items` set filters scan results alongside `failed_items`
- `force_pipeline_exit()` creates stop semaphore, sends Slack notification, calls `sys.exit(1)`
- `_active_slack` module-level reference set by main entry point
- All 309 tests pass
- `plugin.json` bumped to 1.6.1
