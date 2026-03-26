# Agents must clean up test data and use random values for test fixtures

## Status: Open

## Priority: High

## Summary

The coder agent inserted test fixtures with recognizable placeholder values
(item_slug="12-test-item", cost=0.01, input_tokens=100, output_tokens=50)
into the production SQLite DB and left them there. The validator then saw
the page rendering this data and accepted it as "real." Two policies are
needed to prevent this class of bug.

## Policy 1: Clean up test data after testing

The coder agent must delete any test data it inserts during implementation.
If test data is needed to verify the code works, the agent must:
1. Insert the test data
2. Verify the feature works
3. Delete the test data before marking the task complete
4. Verify the feature shows the empty state correctly after cleanup

Add this rule to .claude/agents/coder.md and procedure-coding-rules.md.

## Policy 2: Use random/unique values for test fixtures

When creating test data, agents must use random or UUID-based values that
are clearly distinguishable from real data. This reduces the chance of
test data being mistaken for real data by the validator or by humans.

Examples:
- BAD: item_slug="12-test-item", cost=0.01, tokens=100
- GOOD: item_slug="test-{uuid4[:8]}", cost=random(0.1, 5.0),
  tokens=random(500, 50000)

Add this rule to .claude/agents/coder.md and the validator agent should
flag any test-fixture-looking values (exact round numbers like 100/50,
slugs containing "test-item") as WARN per step 5c.

## Immediate cleanup

Delete the fake rows from cost_tasks:
    DELETE FROM cost_tasks WHERE item_slug = '12-test-item';

## LangSmith Trace: 97f344a5-c3c0-4e79-9219-d7f82a8b2ae7
