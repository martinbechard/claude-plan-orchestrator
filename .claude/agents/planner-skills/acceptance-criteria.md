# Planner Skill: Acceptance Criteria Format

Every task and every work item MUST have acceptance criteria written as a
checklist of specific YES/NO questions. Each question must be independently
verifiable by running a command, reading a file, or checking a specific value.

BAD (vague prose):
  - The analysis page displays real data after a worker completes

GOOD (verifiable questions):
  - Does the cost_tasks table contain a row with the real item slug and
    cost > $0.00 after running one work item? YES = pass, NO = fail
  - Does /analysis show that item's slug (not test data)? YES = pass, NO = fail
  - Are there zero rows containing test fixture data (e.g. "test-item",
    cost=0.01, tokens=100)? YES = pass, NO = fail

Rules for writing acceptance criteria:
- Each criterion is a question ending with "? YES = pass, NO = fail"
- The question must reference a specific observable outcome (a DB value, a
  page element, a command exit code, a file's contents)
- Criteria that require subjective judgement or cannot be verified without
  a running server must say "WARN if cannot verify at validation time"
- Never write criteria that can be satisfied by test fixture data alone
