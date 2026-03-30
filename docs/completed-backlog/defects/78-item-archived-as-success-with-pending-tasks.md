# Item archived as success with pending tasks

The archival node does not verify that all plan tasks reached a terminal status (verified, failed, skipped). An item can be archived as "success" while tasks are still pending or blocked by unresolved dependencies.

## Reproduction

Item 74-item-page-step-explorer was archived as outcome=success, but tasks 0.4 and 0.5 were still in "pending" status. The executor returned without completing them (deadlocked on unvalidated dependency), the pipeline routed to archive, and archive committed the item as complete.

## Expected behavior

Before archiving, the archival node should check whether all plan tasks are in a terminal status. If pending tasks remain, the outcome should reflect that (e.g. outcome=warn with a message identifying the skipped tasks), not silently report success.

## Affected code

- langgraph_pipeline/pipeline/nodes/archival.py - archive node




## 5 Whys Analysis

Title: Item archived as success with pending tasks
Clarity: 4

5 Whys:

W1: Why was item 74 archived as success despite tasks 0.4 and 0.5 remaining pending?
    Because: The archival node does not verify that all plan tasks reached terminal status before committing [C1, C3].

W2: Why doesn't the archival node perform this verification?
    Because: The current implementation lacks state validation logic in its pre-commit checks [C1]. It commits the outcome without checking whether tasks are verified, failed, skipped, or still pending.

W3: Why were tasks 0.4 and 0.5 still pending when execution ended?
    Because: The executor deadlocked on unvalidated dependencies and returned without completing them [C4]. The blocking dependency was never resolved by upstream validation.

W4: Why did the pipeline route to archival when tasks were incomplete?
    Because: There is no upstream gate validating task terminal status before archival [C2]. The pipeline proceeds to archive regardless of execution state [C5].

W5: Why is this validation missing from the archival node's design?
    Because: The archival node was implemented to commit outcomes without a pre-commit gate that checks task lifecycle state [C1, C6] [ASSUMPTION: validation was not included in initial design].

Root Need: The archival node must validate that all plan tasks have reached terminal status (verified, failed, or skipped) before committing [C1, C5]. If pending tasks remain, the outcome should reflect that status (e.g., outcome=warn with identified skipped tasks) rather than silently reporting success [C2, C6].

Summary: The archival node lacks pre-commit validation to ensure all plan tasks are in terminal status before archiving, allowing incomplete plans to be marked as successful.
