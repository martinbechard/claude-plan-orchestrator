# Validator Skill: E2E and UI Validation (Step 3 + Step 5b)

## Step 3: E2E Test
If the work item or task references a test file (tests/*.spec.ts):
- Run: pnpm test:e2e tests/e2e/<test-file>
- Failure = FAIL. Include full output in Evidence.

**UI acceptance criteria detection:** Scan all acceptance criteria from the work
item. Any criterion that references user-visible behavior qualifies as a UI
criterion. Look for patterns like:
- "Does the page show X", "displays X", "shows Y", "page contains Z"
- "filter works", "link navigates to", "button does X"
- "table lists", "column appears", "row includes"

For each UI criterion found:
1. Write a targeted Playwright .spec.ts test under tests/e2e/ that navigates to
   the relevant page and verifies the criterion using accessible selectors
   (getByRole, getByText, getByLabel)
2. Run: pnpm test:e2e tests/e2e/<test-file>.spec.ts
3. Include the test result (PASS/FAIL) in the validation findings
4. Clean up the .spec.ts file after the test runs

If no UI criteria and no referenced test file, skip this step.

## Step 5b: End-to-end gate
For acceptance criteria that involve the web UI ("displays X", "shows Y",
"page contains Z"), use Playwright e2e tests instead of curl.

The web server runs at http://localhost:7070. For each UI criterion:

1. Create a targeted .spec.ts test under tests/e2e/ that:
   - Navigates to the relevant page
   - Uses accessible selectors (getByRole, getByText, getByLabel)
   - Asserts the expected content or behavior is present
2. Run: pnpm test:e2e tests/e2e/<test-file>.spec.ts
3. If the test passes = PASS for that criterion
4. If the test fails = FAIL, include the Playwright error output in Evidence
5. Clean up the test file after running

For simple static content checks where a full browser is unnecessary, curl
remains acceptable as a quick alternative. Because the web server may be
mid-restart when a new route is first checked, apply one retry on 404:

    http_status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:7070/<path>)
    if [ "$http_status" = "404" ]; then
        sleep 2
        http_status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:7070/<path>)
    fi
    if [ "$http_status" = "404" ]; then
        echo "FAIL: route still 404 after retry"
    else
        curl -s http://localhost:7070/<path> | grep "<expected text>"
    fi

Only report WARN for criteria that genuinely require complex user interaction
(multi-step form flows, drag-and-drop) that even Playwright cannot easily test.
