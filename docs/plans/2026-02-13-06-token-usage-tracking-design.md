# Token Usage Tracking and Cost Reporting - Design Document

> **For Claude:** REQUIRED SUB-SKILL: Use the implement skill to execute this plan task-by-task.

**Goal:** Track token consumption across orchestrator tasks and auto-pipeline work items, producing per-task and aggregate usage reports.

**Architecture:** Add a TaskUsage dataclass to hold per-task metrics (tokens, cost, cache stats). Modify run_claude_task() to always use structured JSON output from the Claude CLI, parse the result event, and populate TaskUsage on every TaskResult. Add a PlanUsageTracker to accumulate per-task usage into section-level and plan-level totals. Write a usage-report.json alongside the plan YAML when the plan completes. Enhance per-task log files with usage data.

**Tech Stack:** Python 3 (plan-orchestrator.py, auto-pipeline.py), JSON (CLI output parsing, usage report), YAML (plan files)

---

## Architecture Overview

### TaskUsage Dataclass

New dataclass added alongside TaskResult in plan-orchestrator.py:

    @dataclass
    class TaskUsage:
        input_tokens: int = 0
        output_tokens: int = 0
        cache_read_tokens: int = 0
        cache_creation_tokens: int = 0
        total_cost_usd: float = 0.0
        num_turns: int = 0
        duration_api_ms: int = 0

TaskResult gets an optional field:

    usage: Optional[TaskUsage] = None

### CLI Output Capture Strategy

The Claude CLI provides full usage data in its JSON output. Currently the orchestrator only uses structured output in verbose mode.

**Non-verbose mode change:** Add --output-format json to the CLI command. After the process completes, parse the final stdout as JSON to extract the result object containing usage fields.

**Verbose mode change:** Modify stream_json_output() to capture and return the result event data (it already parses it at line 1433, but only prints it). Return the parsed result dict so run_claude_task() can extract usage.

**Both paths produce a TaskUsage** that is attached to the returned TaskResult.

### Usage Extraction

From the CLI result JSON:

    input_tokens = result.get("usage", {}).get("input_tokens", 0)
    output_tokens = result.get("usage", {}).get("output_tokens", 0)
    cache_read_tokens = result.get("usage", {}).get("cache_read_input_tokens", 0)
    cache_creation_tokens = result.get("usage", {}).get("cache_creation_input_tokens", 0)
    total_cost_usd = result.get("total_cost_usd", 0.0)
    num_turns = result.get("num_turns", 0)
    duration_api_ms = result.get("duration_api_ms", 0)

The total_cost_usd field is authoritative (not calculated from tokens).

### PlanUsageTracker

A class that accumulates usage across all tasks:

    class PlanUsageTracker:
        def __init__(self):
            self.task_usages: dict[str, TaskUsage] = {}

        def record(self, task_id: str, usage: TaskUsage) -> None
        def get_section_usage(self, plan: dict, section_id: str) -> TaskUsage
        def get_total_usage(self) -> TaskUsage
        def get_cache_hit_rate(self) -> float
        def format_summary_line(self, task_id: str) -> str
        def format_final_summary(self) -> str

Cache hit rate: cache_read_tokens / (cache_read_tokens + input_tokens) when denominator > 0, else 0.

### Summary Output

After each task completes, print a usage summary line:

    [Usage] Task 1.1: $0.0234 | 1,234 in / 567 out / 890 cached (72% cache hit) | Running: $0.0456

After all tasks complete, print a final summary:

    === Usage Summary ===
    Total cost: $0.1234
    Total tokens: 12,345 input / 5,678 output
    Cache: 8,901 read / 2,345 created (72% hit rate)
    API time: 45.6s across 12 turns
    Per-section breakdown:
      Phase 1: $0.0456 (3 tasks)
      Phase 2: $0.0778 (2 tasks)

### Usage Report File

After plan completion, write .claude/plans/logs/{plan-name}-usage-report.json:

    {
      "plan_name": "Token Usage Tracking",
      "completed_at": "2026-02-13T15:30:00",
      "total": {
        "cost_usd": 0.1234,
        "input_tokens": 12345,
        "output_tokens": 5678,
        "cache_read_tokens": 8901,
        "cache_creation_tokens": 2345,
        "cache_hit_rate": 0.72,
        "num_turns": 12,
        "duration_api_ms": 45600
      },
      "sections": [
        {"id": "phase-1", "name": "Phase 1", "cost_usd": 0.0456, "task_count": 3},
        ...
      ],
      "tasks": [
        {"id": "1.1", "name": "Task name", "cost_usd": 0.0123, ...},
        ...
      ]
    }

### Log File Enhancement

The existing per-task log files (.claude/plans/logs/task-*.log) get additional lines in the header:

    === Claude Task Output ===
    Timestamp: 2026-02-13T15:30:00
    Duration: 45.6s
    Return code: 0
    Cost: $0.0123
    Tokens: 1234 input / 567 output / 890 cache_read / 234 cache_create
    Turns: 5
    API time: 12345ms

### Auto-Pipeline Integration

The auto-pipeline already invokes the orchestrator as a child process. The usage report file is written by the orchestrator itself, so the auto-pipeline does not need to parse orchestrator stdout for usage data. Instead:

1. After execute_plan() returns, read the usage report JSON if it exists
2. Accumulate per-work-item totals (plan creation + orchestrator execution)
3. At session end, write a session-level summary to .claude/plans/logs/pipeline-session-{timestamp}.json

---

## Key Files

### Modified Files

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | TaskUsage dataclass, parse CLI JSON output, PlanUsageTracker, usage report, log enhancement |
| scripts/auto-pipeline.py | Read usage reports, aggregate per-session |

### New Files

| File | Purpose |
|------|--------|
| tests/test_token_usage.py | Unit tests for TaskUsage, PlanUsageTracker, usage parsing |
| .claude/plans/logs/*-usage-report.json | Generated usage reports (not committed) |

---

## Design Decisions

1. **Always use --output-format json in non-verbose mode.** This is the minimal change to get structured output. The user experience changes slightly: instead of raw text stdout, we get JSON. But since non-verbose mode already shows progress dots (not raw output), the display is unaffected. We parse the JSON after process completion.

2. **Use total_cost_usd from CLI, never calculate cost from tokens.** The CLI's cost calculation accounts for pricing tiers, model variants, and cache discounts. Recalculating would be fragile and duplicate logic.

3. **PlanUsageTracker lives in plan-orchestrator.py, not a separate module.** The orchestrator is a single-file script by convention. Adding a class to it follows the existing pattern of TaskResult, CircuitBreaker, OutputCollector.

4. **Usage report goes to .claude/plans/logs/ alongside task logs.** This is the natural home for execution artifacts. The report filename includes the plan name for easy identification.

5. **stream_json_output() returns usage data via a shared mutable reference.** Rather than changing its signature (which would break threading), we pass a dict that it populates with the result event data. This is thread-safe since only one thread writes to it.

6. **Auto-pipeline reads the usage report file rather than parsing orchestrator stdout.** This is cleaner and avoids fragile stdout parsing. The orchestrator writes the report, the pipeline reads it.

7. **Cache hit rate uses cache_read / (cache_read + input_tokens).** This measures what fraction of input context was served from cache vs. freshly processed. A higher rate means lower cost per token.
