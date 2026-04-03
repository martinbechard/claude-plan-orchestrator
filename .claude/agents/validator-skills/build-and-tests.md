# Validator Skill: Build and Unit Tests (Steps 1-2)

## Step 1: Build
Run the build command from the prompt.
- If it fails AND the baseline also failed with the same error = WARN (pre-existing)
- If it fails AND the baseline passed = FAIL (regression introduced by this task)
- If it passes = PASS

## Step 2: Unit Tests
Run the test command from the prompt.
- If tests fail AND the same tests failed in the baseline = WARN (pre-existing)
- If tests fail AND they passed in the baseline = FAIL (regression)
- If all tests pass = PASS
