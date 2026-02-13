# Chapter 3: The Coordination Protocol

**Commit:** `a2a6684` --- 2026-02-05
**Size:** ~80 new lines in orchestrator, plus `.claude/skills/agent-sync.md`
**Title:** "feat(orchestrator): Add subagent coordination with semaphore and messaging"

## The Problem with Parallel Agents

Even with conflict detection at the plan level, parallel Claude sessions can surprise you.
A task described as "modify the login form" might also touch a shared utility, a CSS module,
or a type definition file. The static analysis from Chapter 2 catches *declared* conflicts
but not *emergent* ones.

The solution was a runtime coordination protocol: file claims, heartbeats, and status files.

## The Subagent Context Injection

When running in parallel mode, the orchestrator injects a `SUBAGENT CONTEXT` header into
each Claude session's prompt:

```
## SUBAGENT CONTEXT (You are a parallel worker)

**SUBAGENT_ID:** subagent-8-2
**WORKTREE_PATH:** .worktrees/plan-task-8-2
**PARALLEL_GROUP:** phase-8-admin
**SIBLING_TASKS:** 8.1, 8.3

### MANDATORY: Follow the agent-sync protocol

You are running in parallel with other agents. Before editing ANY file:

1. Initialize your status file:
   echo '{"status":"starting","task_id":"8.2","heartbeat":"..."}' >
     .claude/subagent-status/subagent-8-2.json

2. Check claims before editing:
   cat .claude/agent-claims.json

3. Claim files before editing

4. Release claims when done
```

This means each Claude session knows:
- Its own identity (`SUBAGENT_ID`)
- Where it's working (`WORKTREE_PATH`)
- Who its siblings are (`SIBLING_TASKS`)
- The protocol it must follow

## The Claims File: agent-claims.json

The file-level mutex system uses a shared JSON file:

```json
{
  "claims": [
    {
      "agent": "subagent-8-1",
      "file": "src/components/community/posts/EditForm.tsx",
      "claimed_at": "2026-02-05T14:30:00Z"
    },
    {
      "agent": "subagent-8-2",
      "file": "src/components/community/messages/ShareLinkModal.tsx",
      "claimed_at": "2026-02-05T14:30:05Z"
    }
  ]
}
```

Before editing any file, an agent must:
1. Read the claims file
2. Check if the file is already claimed by another agent
3. Add its own claim
4. Edit the file
5. Release the claim when done

## Stale Claim Cleanup

The orchestrator gained a `cleanup_stale_claims()` function to handle agents that crash
or time out without releasing their claims:

```python
def cleanup_stale_claims(max_age_minutes=60):
    """Remove stale claims from agent-claims.json.

    A claim is stale if:
    - Its claimed_at timestamp is older than max_age_minutes
    - OR no corresponding subagent status file exists with recent heartbeat
    """
    for claim in claims:
        # Parse claimed_at timestamp
        age_seconds = (now - claimed_at).total_seconds()
        if age_seconds > max_age:
            removed_count += 1
            continue

        # Check subagent status file for heartbeat
        status_path = Path(f".claude/subagent-status/{agent_id}.json")
        if status_path.exists():
            if status.get("status") in ["completed", "failed"]:
                removed_count += 1
                continue

        active_claims.append(claim)
```

This runs before each parallel group execution, ensuring leftover claims from
crashed previous runs don't block new work.

## The Heartbeat Pattern

Each subagent is instructed to update its status file periodically:

```json
{
  "status": "working",
  "task_id": "8.2",
  "heartbeat": "2026-02-05T14:35:00Z",
  "current_file": "src/components/community/messages/ShareLinkModal.tsx"
}
```

The orchestrator can use these heartbeats to detect hung agents (agents that stop
updating but haven't written a final status). In practice, the 600-second timeout
on the Claude subprocess handles most hung agent cases, but heartbeats provide
additional observability.

## The Coordination Files

After this commit, the project had a clear set of coordination files:

| File | Purpose |
|------|---------|
| `.claude/agent-claims.json` | Runtime file mutex |
| `.claude/subagent-status/{id}.json` | Per-agent heartbeat and status |
| `.claude/plans/task-status.json` | Task result communication (orchestrator <-> Claude) |
| `.claude/skills/agent-sync.md` | Documentation of the full protocol |

## A Practical Assessment

The coordination protocol was a significant engineering effort, but its effectiveness
was mixed:

**What worked:**
- Status files gave the orchestrator visibility into agent progress
- Stale claim cleanup prevented deadlocks between runs
- The SUBAGENT_ID in prompts let Claude sessions identify themselves

**What was fragile:**
- The claims file is a classic shared-state coordination problem. Multiple agents
  reading and writing JSON concurrently can race, especially on local filesystems
- Claude doesn't always follow the protocol perfectly --- it might forget to claim
  files or fail to release claims on error paths
- The heartbeat mechanism was defined but never enforced (no "kill hung agent" logic)

## Questions

**Q: Why not use filesystem locks (flock) instead of a JSON claims file?**
Filesystem locks would be more robust against races but less observable. The JSON
approach lets the orchestrator read the claims file at any time to understand the
current state. It's also easier to debug --- you can `cat .claude/agent-claims.json`
to see what's happening.

**Q: Was the coordination protocol ever the cause of a production failure?**
Not directly, but the parallel merge issues (Chapter 2) were partly caused by the
worktree isolation not being as complete as expected. The coordination protocol
addressed a real concern but the bigger problem turned out to be the merge strategy.

**Q: Could this be simplified with a database (SQLite)?**
Yes, and it would solve the race condition issues. However, the coordination files
need to exist in the git worktrees alongside the code, and a SQLite database shared
across worktrees would introduce its own locking challenges. The JSON approach is
"good enough" for the 2-4 parallel agents typically running simultaneously.
