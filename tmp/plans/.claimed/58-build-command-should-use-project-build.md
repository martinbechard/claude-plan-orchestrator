# Replace fragile build command with proper project-wide syntax check

## Summary

The build command in orchestrator-config.yaml hardcodes specific file paths
to compile. When files get deleted, the build fails. Replace with a
project-wide Python syntax check that automatically covers all .py files.

## Acceptance Criteria

- Does the build command check ALL .py files under langgraph_pipeline/?
  YES = pass, NO = fail
- Does it work without listing specific file paths?
  YES = pass, NO = fail
- Does it fail if any .py file has a syntax error?
  YES = pass, NO = fail

## LangSmith Trace: 449a921e-e973-4458-a144-984841c68ba1


## 5 Whys Analysis

Now I'll apply systematic debugging principles to analyze this backlog item using the 5 Whys method.

---

**Title:** Build command fragility caused by manual file list maintenance

**Clarity:** 4/5

The request is well-specified with clear acceptance criteria. It clearly describes the problem (hardcoded paths break) and the desired solution (auto-discover all .py files). Minor gap: doesn't explain *why* the original design chose selective compilation.

**5 Whys:**

1. **Why does the build command fail when files are deleted?**
   Because orchestrator-config.yaml hardcodes specific file paths that must exist for the command to succeed.

2. **Why was the build command designed to hardcode specific file paths instead of auto-discovering them?**
   Because the original implementation chose explicit control over which files to validate, either for performance reasons or to intentionally exclude certain files.

3. **Why does explicit control over file lists create brittleness over time?**
   Because as developers add, rename, and delete files, the hardcoded list becomes stale. Developers forget to update config.yaml in sync with code changes, causing silent omissions.

4. **Why are silent omissions from validation dangerous for a Python project?**
   Because syntax errors in unvalidated files won't be caught until runtime, potentially causing failures in production or during manual testing later in the pipeline.

5. **Why should the build system automatically validate ALL .py files rather than maintaining an explicit list?**
   Because automatic discovery removes the coupling between code changes and build configuration—developers can't accidentally forget to register new files, and deleted files don't break the build.

**Root Need:** 

Decouple the build validation system from manual project structure maintenance. The system should self-adapt to code changes (files added/deleted) without requiring configuration updates, ensuring consistent syntax validation across the entire codebase.

**Summary:** 

The fragile build command reflects an outdated assumption that developers will manually maintain file lists in sync with code changes; the root need is automated discovery and uniform validation of all Python files.
