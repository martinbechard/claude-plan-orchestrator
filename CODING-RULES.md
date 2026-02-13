# Coding Rules

Standard rules and best practices for AI-generated code. These rules apply to any project
using the plan orchestrator. Adapt the examples to your language and framework.

Each rule explains **why** it exists (the BECAUSE chain), so the AI can make correct
judgment calls when the letter of the rule doesn't quite fit the situation.

---

## 0. File Headers and Design Traceability

- **RULE:** Every source file MUST include a header comment with:
  - File path (relative to project root)
  - One-line summary of the file's purpose
  - Reference to the design document that defines its behavior (if one exists)
  - **BECAUSE:** Headers create an explicit link between implementation and specification,
    preventing architectural drift.
  - **BECAUSE:** When an AI agent picks up a task in a fresh session, the header tells it
    where to find the design context without searching.

- **RULE:** Before modifying existing code, ALWAYS verify changes against the design document
  referenced in the header. If there is a discrepancy, raise the issue rather than silently
  diverging.
  - **BECAUSE:** Ensures implementation continues to align with the agreed-upon specification.
  - **BECAUSE:** Catches unintended deviations early, before they cascade.

- **RULE:** Major design changes or significant refactorings MUST be discussed and approved
  before implementation.
  - **BECAUSE:** Prevents costly rework if changes are later deemed undesirable.
  - **BECAUSE:** In an orchestrated plan, one agent's unauthorized design change can break
    assumptions held by subsequent tasks.

- **RULE:** Design documents are the single source of truth for module behavior. When changing
  code, the corresponding design doc MUST be updated to reflect the changes. Conversely, when
  code seems incorrect, consult the design doc to understand the intended behavior.
  - **BECAUSE:** Synchronized design and code reduces confusion and prevents drift.
  - **BECAUSE:** Design documents provide essential context for recovering intended behavior.

- **RULE:** After implementing changes and ensuring tests pass, ALWAYS perform a code review
  (manual or automated) against the project's standards.
  - **BECAUSE:** Code reviews catch issues that tests cannot: readability, maintainability,
    adherence to conventions, and subtle logic errors.

## 1. Naming Conventions

- **RULE:** Follow your language's community conventions consistently:
  - **PascalCase** for classes, interfaces, type definitions, React components
  - **camelCase** for variables, functions, methods, utility files
  - **ALL_CAPS_SNAKE_CASE** for manifest constants (values that never change at runtime)
  - **kebab-case** for configuration files and non-code assets
  - **BECAUSE:** Predictable naming reduces cognitive load. You can tell a file's purpose
    from its casing alone.

- **RULE:** File names containing a single primary class or component MUST be named to match
  that class (e.g., `StatusManager.ts` for class `StatusManager`).
  - **BECAUSE:** Creates a predictable mapping between the artifact and the filesystem,
    reducing time spent searching for definitions.

- **RULE:** Variable, function, and method names MUST be clear, descriptive, and reflect their
  purpose. Avoid cryptic abbreviations or overly generic names (e.g., `data`, `manager`, `temp`).
  - **BECAUSE:** The name itself should convey intent and nature, reducing the need for
    comments and preventing ambiguity.

- **RULE:** Function/method names SHOULD indicate their purpose through word choice:
  - **Nouns/noun phrases** for functions that retrieve without side effects:
    `orderCount`, `getUserProfile`, `isActive`
  - **Verbs/verb phrases** for functions that alter state or perform actions:
    `updateStatus`, `calculateTotal`, `saveConfiguration`
  - **BECAUSE:** Signals to the reader whether calling the function might change system state.
    This is the Command-Query Separation principle.

- **RULE:** Avoid variable names that are easily confused (e.g., `orderCount` vs `orderCounts`
  for different concepts). Be precise.
  - **BECAUSE:** Subtle naming differences for distinct concepts lead to hard-to-find bugs.

- **RULE:** Naming conventions MUST be applied consistently across the entire codebase.
  - **BECAUSE:** A uniform style makes the codebase feel cohesive and easier to navigate.

## 2. File Organization and Imports

- **RULE:** Organize files into standard top-level directories based on their category:
  - `src/` - All primary source code
  - `scripts/` - Utility scripts for build, deployment, development tasks
  - `docs/` - Documentation, design documents, plans
  - `test/` or `tests/` - Test code, mocks, fixtures
  - **BECAUSE:** Establishes a conventional structure that makes it easy to locate artifacts
    and clearly separates source from supporting files.

- **RULE:** Separate shared contracts from implementation:
  - Shared interfaces/types/constants should live in dedicated directories
    (e.g., `src/interfaces/`, `src/types/`, `src/constants/`)
  - Items used only within a single module may remain co-located in that module
  - **BECAUSE:** Centralizing shared contracts improves discoverability and prevents
    scattering definitions across modules.
  - **BECAUSE:** Clearly separates public API contracts from internal implementation details.

- **RULE:** Any single source file exceeding 200 lines SHOULD be refactored into a module
  folder with an entry point (`index.ts`, `__init__.py`, etc.) that exports only the
  public API.
  - **BECAUSE:** Prevents excessively long files that are hard to read, understand, and maintain.
  - **BECAUSE:** Enforces a clear public API for each component.

- **RULE:** Module entry points (e.g., `index.ts`) MUST only contain import/export statements.
  No implementation logic.
  - **BECAUSE:** The entry point defines the public contract. Mixing in logic blurs the boundary.

- **RULE:** Each exported class SHOULD reside in its own distinct file.
  - **BECAUSE:** One file, one purpose. Makes code review and maintenance simpler.

- **RULE:** Test files MUST mirror the source directory structure.
  - **EXAMPLE:** Tests for `src/services/workflow/Executor.ts` go in
    `test/services/workflow/Executor.test.ts`.
  - **BECAUSE:** Clear, predictable relationship between code and its tests.

- **RULE:** Before creating a new file for a type, interface, or class, check whether a
  suitable definition already exists. If it does, import it. If it does not, create it in
  the correct location and register it in whatever central registry the project uses.
  - **BECAUSE:** Prevents duplication and ensures a single source of truth for definitions.

- **RULE:** Organize imports logically: external libraries first, then project-level aliases,
  then relative imports. Remove all unused imports.
  - **BECAUSE:** Consistent organization improves readability and makes dependencies clearer.
  - **BECAUSE:** Unused imports clutter code and can cause confusion during refactoring.

- **RULE:** Actively avoid and resolve circular dependencies between modules.
  - **BECAUSE:** Circular dependencies cause runtime errors, make code harder to test,
    and hinder modularity. Separating contracts into shared directories can break cycles.

## 3. Code Structure and Readability

- **RULE:** Methods SHOULD NOT exceed 30-40 lines. Extract complex logic into helper methods.
  - **BECAUSE:** Shorter methods are easier to understand, test, and maintain. They tend to
    have a single responsibility.

- **RULE:** Classes SHOULD NOT exceed 300 lines. If a class grows beyond this, refactor into
  a module folder.
  - **BECAUSE:** Large classes often violate the Single Responsibility Principle (SRP) and
    are hard to manage.

- **RULE:** Functions accepting more than two parameters MUST use a parameter object.
  Name the type descriptively (e.g., `CreateUserParams`, `SearchOptions`).
  - **BECAUSE:** Parameter objects improve readability and maintainability, especially when
    adding or removing parameters.

- **RULE:** Prioritize code clarity and correctness over premature abstraction. Apply
  abstractions when patterns are clear, not speculatively.
  - **BECAUSE:** Maintainability and understandability come first. Three similar lines are
    better than a premature abstraction that nobody understands.

- **RULE:** Focus on minimal, necessary changes to achieve the goal. Avoid over-engineering.
  - **BECAUSE:** Simpler solutions are easier to understand, test, and maintain.
  - **BECAUSE:** Minimizing scope reduces the risk of unintended side effects.
  - **BECAUSE:** In orchestrated plans, each task should do one thing well. Gold-plating
    delays the plan and introduces risk.

## 4. Types and Type Safety

- **RULE:** Never use `any` as a type. Always create proper types for groups of fields.
  TypeScript is all about types; using `any` defeats the purpose.
  - **BECAUSE:** `any` bypasses all type checking, hiding bugs that the compiler would
    otherwise catch.

- **RULE:** Use the correct construct for the purpose:
  - `interface` for contracts that classes can implement or objects must adhere to
  - `type` for data shapes, function signatures, unions, intersections
  - `class` when behavior (methods), internal state, or inheritance is required
  - **BECAUSE:** Choosing the right construct signals intent and makes the code self-documenting.

- **RULE:** Avoid "Primitive Obsession." Use specific types instead of raw primitives
  (`string`, `number`, `boolean`) to represent domain concepts.
  - **EXAMPLE:** Use `type UserId = string` or `type Currency = 'USD' | 'EUR' | 'GBP'`
    instead of bare strings.
  - **BECAUSE:** Domain-specific types improve type safety, self-documentation, and
    centralize validation logic.

- **RULE:** Groups of primitives that are always used together SHOULD be encapsulated in
  an interface or type.
  - **BECAUSE:** Improves cohesion and makes the relationship explicit.

- **RULE:** Use type assertions (`as any`, `as unknown as Type`) sparingly, with
  justification. Fix underlying type mismatches instead.
  - **BECAUSE:** Type assertions bypass safety and can hide bugs.

- **RULE:** Never pepper code with literal constants. Use manifest constants defined at the
  top of the file (or in a constants module) for any numeric or string value that has meaning.
  - **BECAUSE:** Magic numbers and strings are cryptic, error-prone, and hard to update.
  - **BECAUSE:** Constants with descriptive names make code self-documenting.

## 5. Coupling and Cohesion

- **RULE:** Classes MUST have a single, well-defined responsibility (Single Responsibility
  Principle / SRP). Each class should have one reason to change.
  - **BECAUSE:** High cohesion makes classes easier to understand, test, and maintain.

- **RULE:** Methods MUST perform a single logical operation.
  - **BECAUSE:** Single-purpose methods are more readable and testable.

- **RULE:** Minimize coupling between modules. Depend on interfaces rather than concrete
  implementations, especially across module boundaries.
  - **BECAUSE:** Loose coupling makes the system more flexible and resilient to change.

- **RULE:** Do not access private members of other classes. Interact through the public API.
  - **BECAUSE:** Violating encapsulation creates tight coupling that breaks when internals change.

- **RULE:** Avoid "Feature Envy." If a method mostly operates on another class's data,
  move it to that class.
  - **BECAUSE:** Improves cohesion and reduces coupling.

- **RULE:** Utility functions used by only one class SHOULD be private to that class or
  its module, not exported globally.
  - **BECAUSE:** Keeps related logic together and avoids polluting the module scope.

## 6. Error Handling

- **RULE:** Avoid empty `catch` blocks. Always log the error or re-throw appropriately.
  - **BECAUSE:** Empty catches silently swallow errors, hiding problems that compound over time.

- **RULE:** Do not use exceptions for normal control flow. Use conditional logic instead.
  - **BECAUSE:** Misusing exceptions is inefficient and obscures the actual logic.

- **RULE:** Provide clear, informative error messages that include context (what was being
  attempted, what values were involved).
  - **BECAUSE:** Good error messages cut debugging time from hours to minutes.

- **RULE:** When logging, always include variable names alongside values:
  `log("Failed to process order: orderId=${orderId}, status=${status}")`
  - **BECAUSE:** Knowing which variable holds which value makes trace logs dramatically
    easier to read.

- **RULE:** When troubleshooting unexpected values, consider whether the variable name is
  misleading. Rename for clarity if so.
  - **BECAUSE:** Clear naming aids debugging by making intent explicit.

## 7. Comments and Documentation

- **RULE:** Every exported function, interface, type, class, and global variable MUST have
  a doc comment (JSDoc, docstring, etc.) explaining its purpose.
  - **BECAUSE:** Documentation alongside the code improves understanding and maintainability.

- **RULE:** Write comments to explain _why_, not _what_. The code should explain the what.
  Focus on rationale, business rules, workarounds, and non-obvious decisions.
  - **BECAUSE:** The "why" is context that code alone cannot convey.

- **RULE:** Remove commented-out code. That's what version control is for.
  - **BECAUSE:** Commented code is noise that becomes outdated and confusing.

- **RULE:** Ensure comments are accurate and up-to-date. Fix or remove misleading ones.
  - **BECAUSE:** An incorrect comment is worse than no comment.

- **RULE:** Avoid excessive comments. If you feel the need to comment heavily, refactor
  the code for clarity instead (better naming, smaller functions, clearer structure).
  - **BECAUSE:** Self-documenting code is preferred. Comments that restate the obvious add
    clutter.

- **RULE:** Remove development-phase comments (TODO, FIXME, attribution) before task
  completion. Use task trackers and commit messages instead.
  - **BECAUSE:** Stale TODOs accumulate as noise. The orchestrator's YAML plan is the
    proper place to track remaining work.

## 8. Conditional Logic

- **RULE:** Avoid large `switch` statements or long `if/else if/else` chains.
  - **BECAUSE:** Hard to read, maintain, and extend. Often violates the Open-Closed Principle.

- **RULE:** Consider polymorphism (via interfaces) or lookup maps/objects instead of
  complex conditionals.
  - **BECAUSE:** Leads to cleaner, more extensible, and testable designs.

## 9. UI Feedback Patterns

- **RULE:** Before implementing success/error notifications in a component, check for
  existing toast, notification, or alert components in the project's UI library.
  - **BECAUSE:** Reusing the existing notification system ensures visual consistency and UX
    quality.
  - **BECAUSE:** Inline state-based message divs (`{error && <div>...</div>}`) create
    visual inconsistency, shift content, and require manual cleanup (setTimeout, etc.).

- **RULE:** Use the project's established notification system for all user feedback. Do not
  add inline success/error state variables for displaying feedback messages.
  - **BECAUSE:** A centralized notification system handles auto-dismiss, positioning, and
    styling consistently.

## 10. Build and Dev Server Management

- **RULE:** After code changes, do not assume hot module replacement (HMR) will pick them up.
  When in doubt, restart the dev server.
  - **BECAUSE:** HMR is unreliable for many change types (new imports, structural changes,
    hook changes). A restart takes seconds and guarantees a clean state.

- **RULE:** When the dev server shows manifest or module errors, restart the server first
  before attempting cache cleanup.
  - **BECAUSE:** A restart solves the vast majority of these issues instantly.

- **RULE:** Always stop the dev server before running a production build. Dev caches and
  build caches can conflict.
  - **BECAUSE:** Cache conflicts produce mysterious errors that waste debugging time.

- **RULE:** Never use `--no-lint` when building new code. It hides errors.
  - **BECAUSE:** Lint errors often indicate real problems. Suppressing them creates
    technical debt.

## 11. Test Discipline

- **RULE:** After ANY code change, run the related tests before moving on.
  - **BECAUSE:** Catching regressions immediately is orders of magnitude cheaper than
    finding them later.

- **RULE:** Failing tests are YOUR responsibility. Fix them immediately --- do not defer or
  assume they were "already broken."
  - **BECAUSE:** In an AI-orchestrated workflow, you are the sole developer. All failures
    result from your changes. Leaving them creates compounding tech debt.

- **RULE:** TypeScript errors in test files count as broken tests.
  - **BECAUSE:** If it doesn't compile, it doesn't test.

- **RULE:** When splitting large test suites, migrate incrementally: move one test group
  at a time, verify it passes, then continue.
  - **BECAUSE:** Incremental migration minimizes risk and ensures continuous validity.

## 12. AI-Specific Discipline

These rules address failure modes specific to AI code generation.

- **RULE:** Never remove existing functionality when asked to "clean up" or "simplify."
  Ask before removing any feature, field, or calculation.
  - **BECAUSE:** AIs sometimes interpret "simplify" as "delete." Working features are never
    clutter.

- **RULE:** Do not add features, refactor code, or make "improvements" beyond what was asked.
  A bug fix doesn't need surrounding code cleaned up. A simple feature doesn't need extra
  configurability.
  - **BECAUSE:** Over-engineering is a common AI failure mode. Each unnecessary addition
    introduces risk and costs tokens.

- **RULE:** When a value is NULL or missing, show that state honestly (0, empty,
  "Not configured"). Do not invent fallback logic to show data from unrelated sources.
  - **BECAUSE:** Invented fallbacks mask real problems and confuse users who expect to see
    actual state.

- **RULE:** Never use "file is too large" as an excuse to defer work. If a file is too large,
  split it into smaller modules and integrate them immediately.
  - **BECAUSE:** "Deferred" is not a valid status. Work is either done or needs to be done now.

- **RULE:** Commit frequently. Uncommitted work is lost when the session ends.
  - **BECAUSE:** In an orchestrated workflow, each task runs in a fresh session. If the task
    doesn't commit, the work vanishes.

---

## Adapting These Rules

This document is a template. To adapt it for your project:

1. **Add project-specific paths** - Replace generic directory examples with your actual
   layout (e.g., `src/components/` for React, `app/models/` for Rails)
2. **Add framework rules** - Add sections for your framework (e.g., React hooks rules,
   Django model conventions, API design standards)
3. **Add a definitions registry** - Consider maintaining a `definitions.md` that maps each
   class/interface/type to its canonical file path and design document
4. **Add your build commands** - Replace generic "run the build" with your actual commands
   (e.g., `pnpm run build`, `cargo build`, `go build ./...`)
5. **Reference from SKILL.md** - The implement skill's Step 3 says "Read the project's
   coding rules." Point it at this file.
