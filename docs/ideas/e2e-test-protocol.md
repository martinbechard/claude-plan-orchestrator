We need to use sonnet instead of opus for running validations - adjust the agent accordingly
We need a validation checklist of things to verify for example:
Rules for a CRUD operation:

- the create and edit operations should be done with the same modal, possibly with some fields not showing in each mode
- ensure the page loads more than once
- ensure data is properly saved when saving and reloaded later
- ensure we can cancel without saving
- ensure save is enabled appropriately when all mandatory fields are filled out
- etc.

We need functional spec -> page guide (as given to user) -> test plan (make sure we cover everything that the user can do. Explain how this covers the functionality). We need every requirement in the functional spec to be identifiable, and we need a coverage analysis to make sure we have enough test cases.

Come up with a generic checklist to be processed by claude haiku as part of the QA audit (have a QA audit subagent called by the QA agent running sonnet).

For investigating problems, start with Claude sonnet, then after 3 attempts at fixing it, use Claude Opus.
