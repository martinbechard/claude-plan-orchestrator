# Design: Validator E2E Testing for UI Acceptance Criteria

## Problem

The validator agent reports "cannot verify at validation time -- requires runtime
confirmation" for acceptance criteria involving the web UI. Instead of giving up,
it should create and run Playwright tests to verify UI criteria programmatically.

## Architecture

### Components

1. **e2e-test-agent** (.claude/agents/e2e-test-agent.md)
   - New agent that creates targeted Playwright tests for specific UI criteria
   - Receives a criterion description and page URL
   - Writes a .spec.ts test file under tests/e2e/
   - Runs the test and reports PASS/FAIL
   - Uses accessible selectors (getByRole, getByText, getByLabel)

2. **Playwright Configuration** (playwright.config.ts)
   - Base URL: http://localhost:7070 (the pipeline dashboard)
   - Test directory: tests/e2e/
   - JSON reporter for machine-readable results (output to logs/e2e/)
   - HTML reporter for human review

3. **Validator Enhancement** (.claude/agents/validator.md)
   - Update Step 3 (E2E Test) to detect UI acceptance criteria
   - When UI criteria found: invoke e2e-test-agent to create and run tests
   - Parse test results and include in validation findings

4. **Project Setup**
   - Install Playwright and dependencies via npm/pnpm
   - Create tests/e2e/ directory structure
   - Add test:e2e scripts to project config

### Key Files to Create

- .claude/agents/e2e-test-agent.md -- new agent definition
- playwright.config.ts -- Playwright configuration
- tests/e2e/.gitkeep -- test directory placeholder

### Key Files to Modify

- .claude/agents/validator.md -- add e2e delegation logic for UI criteria
- langgraph_pipeline/shared/config.py -- e2e config may need spec_dir default

## Design Decisions

1. **Agent-based approach**: The e2e-test-agent creates tests dynamically rather
   than requiring pre-written tests. This matches the pipeline's autonomous nature
   where acceptance criteria are generated per work item.

2. **Playwright over curl**: curl can check static content but cannot verify
   interactive behavior (filters, navigation, dynamic rendering). Playwright
   handles both.

3. **JSON reporter**: Outputs to logs/e2e/ for the existing e2e-analyzer agent
   to consume, maintaining consistency with the analysis pipeline.

4. **Web server at 7070**: The pipeline already runs the dashboard at port 7070
   during execution. Playwright tests connect to this running instance rather
   than starting their own server.

## Task Breakdown

1. Set up Playwright infrastructure (config, dependencies, directory structure)
2. Create the e2e-test-agent definition
3. Update the validator agent to delegate UI criteria to e2e testing


## Acceptance Criteria

- Does an e2e-test-agent exist that can create Playwright tests?
  YES = pass, NO = fail
- When the validator encounters a UI criterion, does it create and run
  an e2e test instead of reporting "cannot verify"?
  YES = pass, NO = fail
- Does the e2e test actually navigate to the page and check the criterion?
  YES = pass, NO = fail
- Are test results included in the validation findings?
  YES = pass, NO = fail
