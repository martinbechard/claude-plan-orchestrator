# Validator Skill: Clause Extraction Validation (Step 1)

## Inputs to Retrieve
- **Raw backlog item file** (the original unstructured markdown)
- **Clause Register** (clauses.md in workspace -- the step output)

## Segments to Ignore

The following raw input segments are boilerplate metadata and should NOT be
expected in the clause register. Treat them as COVERED even if no clause
maps to them:
- LangSmith Trace lines (e.g. "LangSmith Trace: <uuid>")
- Status headers added by the pipeline (e.g. "## Status: Completed")

## Cross-Reference Procedure

1. Split the raw input into paragraphs or independently meaningful segments.
2. For each segment, check the Clause Register for at least one clause that
   maps to it. Record coverage status (COVERED or UNCOVERED).
3. For each clause in the register, verify the text preserves the original
   wording -- no paraphrasing, no interpretation, no added meaning.
4. Verify each clause has exactly one type code from the allowed set:
   C-PROB, C-FACT, C-GOAL, C-CONS, C-CTX, C-AC.
5. Verify clause IDs are sequential (C1, C2, ...) with no gaps or duplicates.
6. Verify the type summary counts match the actual clause type distribution.
7. Flag any clause that interprets ambiguous input without marking it as
   ambiguous -- the extractor should flag ambiguity, not resolve it.

## Quality Gates

| Gate | Rule | How to Check | Severity |
|------|------|-------------|----------|
| QG-1.1 | Every paragraph/sentence in raw input has at least one clause | Cross-reference table has no UNCOVERED segments | FAIL |
| QG-1.2 | No clause reinterprets or paraphrases the original wording | Compare clause text against raw input -- should be near-verbatim | WARN |
| QG-1.3 | Ambiguous statements are flagged, not silently interpreted | Check for ambiguity markers on clauses derived from unclear input | WARN |
| QG-1.4 | Each clause has exactly one type code | Scan for clauses with missing, multiple, or invalid type codes | FAIL |
| QG-1.5 | Clause IDs are sequential and unique (C1, C2, ... no gaps) | Parse IDs, check for monotonic sequence | FAIL |
| QG-1.6 | Type summary counts match actual clause types | Count clauses by type, compare to summary section | FAIL |

## Verdict Derivation

- Any FAIL-severity gate violated: **FAIL**
- Only WARN-severity gates violated: **WARN**
- All gates pass: **PASS**

## Report Format

```
## Step 1 Cross-Reference: Raw Input -> Clauses

| # | Raw Input Segment | Mapped Clause(s) | Status |
|---|-------------------|-------------------|--------|
| 1 | "<first paragraph>" | C1 [PROB], C2 [FACT] | COVERED |
| 2 | "<second paragraph>" | C3 [GOAL] | COVERED |
| ... | ... | ... | ... |

Uncovered segments: <count>
Total clauses: <count>
Type distribution: <count> PROB, <count> FACT, <count> GOAL, <count> CONS, <count> CTX, <count> AC

## Quality Gate Results
| Gate | Result | Evidence |
|------|--------|----------|
| QG-1.1 | PASS/FAIL | <detail> |
| QG-1.2 | PASS/WARN | <detail> |
| QG-1.3 | PASS/WARN | <detail> |
| QG-1.4 | PASS/FAIL | <detail> |
| QG-1.5 | PASS/FAIL | <detail> |
| QG-1.6 | PASS/FAIL | <detail> |

Step 1 Verdict: PASS/WARN/FAIL
```
