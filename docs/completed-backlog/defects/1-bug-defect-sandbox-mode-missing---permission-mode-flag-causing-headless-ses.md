# :bug: *Defect: Sandbox mode missing --permission-mode flag, causing headless ses

## Status: Archived (verification failed)

## Priority: Medium

## Summary

I now have full context. Here's the analysis:

---

**Title:** Sandbox mode must include `--permission-mode acceptEdits` to prevent headless session deadlock

**Classification:** defect - The sandbox feature was shipped with an incomplete CLI flag combination, causing Write/Edit operations to silently deadlock in the default configuration.

**5 Whys:**

1. **Why did task 10.3 fail 3 times with "No status file written by Claude"?**
   Because the Claude agent session ended without ever writing any files — it prompted for user approval of Write/Edit operations and, receiving no input via `stdin=subprocess.DEVNULL`, timed out.

2. **Why did the agent prompt for approval when `--allowedTools` already listed Write and Edit?**
   Because `--allowedTools` only controls which tools are *available* to the agent, not whether they require interactive approval. The separate `--permission-mode` flag (which defaults to `"default"`, i.e. prompt-for-approval) was never set by `build_permission_flags()`.

3. **Why doesn't `build_permission_flags()` set `--permission-mode`?**
   Because when sandbox mode was implemented, the developer treated `--allowedTools` as sufficient for headless execution, not realizing the CLI has two independent permission axes: tool availability (`--allowedTools`) and approval behavior (`--permission-mode`). The non-sandbox fallback (`--dangerously-skip-permissions`) implicitly handles both axes, masking the gap.

4. **Why was the two-axis permission model not caught during development or testing?**
   Because the prior mode (`--dangerously-skip-permissions`) collapses both axes into one flag, so there was no precedent in the codebase for handling them separately. The sandbox feature was a new code path that introduced a partial understanding of the CLI's permission model without end-to-end headless testing of Write/Edit operations.

5. **Why does the orchestrator run Claude with `stdin=subprocess.DEVNULL` without guaranteeing all interactive prompts are suppressed?**
   Because there is no validation layer that checks CLI flag combinations for headless compatibility. The orchestrator assumes that configuring tool access is the same as configuring non-interactive execution, but the Claude CLI treats these as orthogonal concerns. A headless runner needs to explicitly opt into non-interactive mode for every axis the CLI exposes.

**Root Need:** When spawning Claude CLI in headless/non-interactive mode (`stdin=DEVNULL`), the orchestrator must guarantee that all interactive prompts are suppressed — not just tool availability, but also approval behavior. Any CLI flag combination that could trigger an interactive prompt is incompatible with headless execution and must be treated as a configuration error.

**Description:**
`build_permission_flags()` in both `plan-orchestrator.py:725` and `auto-pipeline.py:427` passes `--allowedTools` but omits `--permission-mode acceptEdits` when sandbox is enabled. This causes the Claude CLI to default to interactive approval prompts for Write/Edit, which deadlocks because the orchestrator runs with `stdin=subprocess.DEVNULL`. Add `--permission-mode acceptEdits` to the sandbox code path in both files, and consider adding a startup assertion that verifies the generated flag set is headless-compatible.

## Source

Created from Slack message by U0AG70DCQ1K at 1771695650.633589.
