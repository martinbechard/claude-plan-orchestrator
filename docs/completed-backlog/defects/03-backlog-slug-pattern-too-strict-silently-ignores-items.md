# Backlog slug pattern too strict — silently ignores items without 2-digit prefix

## Status: Open

## Priority: Medium

## Summary

`scan_backlog` uses `BACKLOG_SLUG_PATTERN = re.compile(r"^\d{2,}-[\w-]+$")` to
validate backlog filenames. This requires two or more leading digits. Any item file
that uses a single digit (e.g. `9-foo.md`) or no digit prefix at all (e.g.
`spec-aware-validator.md`) is silently skipped — it never appears in the scan
results and is never processed. Because the skip is silent (no log warning, no Slack
notification), the item sits in the backlog directory indefinitely with no indication
that anything is wrong.

This keeps happening because backlog items created on the fly — by the pipeline
itself, via Slack intake, or manually — do not always produce a two-digit prefix.
Single-digit numbers are natural when there are fewer than ten items of a type, and
prose slugs with no number are natural for one-off analysis items.

## Observed Incidents

- `9-ux-designer-opus-sonnet-loop-with-slack-suspension.md` — ignored due to
  single-digit prefix; manually renamed to `10-` on 2026-03-24.
- `spec-aware-validator-with-e2e-logging.md` — ignored due to no digit prefix;
  manually renamed to `11-` on 2026-03-24.

## Fix

Two complementary changes:

1. **Relax the regex** in `scan.py`: change `r"^\d{2,}-[\w-]+$"` to
   `r"^\d+-[\w-]+$"` to accept any number of leading digits (1+). This fixes the
   single-digit case without any other changes.

2. **Accept digit-free slugs**: further loosen to `r"^[\w][\w-]*$"` (any slug
   starting with a word character) so that prose-named analysis items like
   `cost-analysis.md` are also valid. The item type is already determined by which
   directory it lives in, so the slug does not need a numeric prefix to be
   unambiguous.

3. **Emit a warning** for any `.md` file in a backlog directory that still fails
   validation after the relaxed check (e.g. files starting with `.` or containing
   spaces), so silent ignoring is replaced with a visible signal.

The slug pattern is also referenced in `paths.py` and any code that constructs
slugs from filenames — audit all callers when changing the pattern.

## Source

Recurring issue observed on 2026-03-24; two items confirmed silently ignored in
feature-backlog at time of discovery.
