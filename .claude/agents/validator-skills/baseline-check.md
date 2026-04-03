# Validator Skill: Baseline Check (Step 0)

Before evaluating the current changes, establish what was already broken:
1. Run `git stash` to temporarily revert uncommitted changes
2. Run the build command. Record if it PASSES or FAILS (this is the baseline)
3. Run the test command. Record pass/fail count (this is the baseline)
4. Run `git stash pop` to restore the changes

If the baseline already fails, those failures are PRE-EXISTING and must NOT
be counted against the current task. Only NEW failures (present after changes
but absent in the baseline) count as regressions.
