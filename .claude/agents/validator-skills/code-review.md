# Validator Skill: Code Review (Step 4)

Read procedure-coding-rules.md. Check created/modified files:
- File headers (copyright, license, path, credit, purpose, witty remark)
- No any types
- No literal constants scattered in code
- For E2E tests: accessible selectors (getByRole/getByText/getByLabel)
- No embellishments beyond task requirements

## Lazy Solution Detection

Watch for implementations that technically pass but are not robust:
- Data discarded instead of preserved (e.g. overwriting records vs accumulating)
- Silent failures hiding real errors (bare except, swallowed exceptions)
- Hardcoded values where config or constants belong
- Shallow fixes that mask symptoms without addressing root causes
- Stubs or placeholders passed off as complete implementations
- Copy-paste code instead of proper abstractions
- Missing edge cases that real usage would hit

Code review issues = WARN unless broken functionality = FAIL.
