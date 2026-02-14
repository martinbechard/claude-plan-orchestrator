---
name: coding-rules
description: Coding standards and best practices for AI-generated code. This is a condensed summary; read the full CODING-RULES.md at the project root for complete details and rationale behind each rule.
---

# Coding Rules (Summary)

This skill provides a condensed overview of the project's coding standards. Each section
below summarizes a rule category. For the full rules with rationale (the BECAUSE chains)
and examples, read **CODING-RULES.md** at the project root.

## Rule 0: File Headers and Design Traceability

Every source file must include a header comment with the file path, a one-line purpose
summary, and a reference to the relevant design document. Before modifying code, verify
changes against the design document referenced in the header. Design documents are the
single source of truth for module behavior; keep them synchronized with the code.

## Rule 1: Naming Conventions

Use PascalCase for classes, interfaces, types, and React components. Use camelCase for
variables, functions, methods, and utility files. Use ALL_CAPS_SNAKE_CASE for manifest
constants. Use kebab-case for configuration files. File names must match their primary
class or component. Names must be clear, descriptive, and follow Command-Query Separation
(nouns for queries, verbs for mutations).

## Rule 2: File Organization and Imports

Organize files into standard directories (src/, scripts/, docs/, tests/). Separate shared
contracts (interfaces, types, constants) from implementation. Files exceeding 200 lines
should be refactored into a module folder with an entry point that exports only the public
API. Entry points must contain only import/export statements. Organize imports as: external
libraries, project aliases, relative imports. Remove unused imports. Avoid circular
dependencies.

## Rule 3: Code Structure and Readability

Methods should not exceed 30-40 lines; extract complex logic into helpers. Classes should
not exceed 300 lines. Functions with more than two parameters must use a parameter object.
Prioritize code clarity over premature abstraction. Focus on minimal, necessary changes;
avoid over-engineering.

## Rule 4: Type Safety

Never use the any type; create proper typed interfaces. Use interface for contracts, type
for data shapes and unions, class when behavior or state is required. Avoid primitive
obsession; use domain-specific types. Never use literal magic numbers or strings; define
manifest constants at the top of the file or in a constants module.

## Rule 5: Coupling and Cohesion

Classes must have a single responsibility (SRP). Methods must perform a single logical
operation. Depend on interfaces rather than concrete implementations. Do not access private
members of other classes. Avoid Feature Envy (move methods to where the data lives).
Utility functions used by only one class should be private to that class.

## Rule 6: Error Handling

Never use empty catch blocks; always log or re-throw. Do not use exceptions for control
flow. Provide clear error messages with context (what was attempted, which values were
involved). Include variable names alongside values in log statements.

## Rule 7: Comments and Documentation

Every exported symbol must have a doc comment explaining its purpose. Write comments to
explain why, not what. Remove commented-out code (use version control). Keep comments
accurate and up-to-date. Avoid excessive comments; refactor for clarity instead. Remove
TODO/FIXME comments before task completion; use the YAML plan to track remaining work.

## Rule 11: Test Discipline

Run related tests after any code change. Failing tests are your responsibility; fix them
immediately. TypeScript errors in test files count as broken tests. When splitting large
test suites, migrate incrementally (one group at a time, verify, continue).

## Rule 12: AI-Specific Discipline

Never remove existing functionality when asked to simplify. Do not add features or
improvements beyond what was asked. Show actual state honestly (null, empty, not configured);
never invent fallback data. Never defer work because a file is too large; split and
integrate immediately. Commit frequently; uncommitted work is lost when the session ends.

---

For the full rules with rationale, examples, and additional categories (conditional logic,
UI feedback, build management), read **CODING-RULES.md** at the project root.
