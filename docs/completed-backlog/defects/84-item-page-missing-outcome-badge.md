# Work item page does not display the outcome

The work item detail page shows status badges but does not display the outcome (success/warn/fail) from the completion record. The outcome should appear as the first badge in the status badge list so users can immediately see how the item finished.




## 5 Whys Analysis

Title: Missing outcome badge on work item detail page
Clarity: 4 (clear problem statement and goal; lacks implementation context)
5 Whys:

W1: Why is the outcome not displayed on the work item detail page?
    Because: The work item detail page shows status badges [C2], but does not render the outcome (success/warn/fail) from the completion record [C1, C3]

W2: Why is it necessary to display the outcome?
    Because: Users need to immediately see how the item finished [C5]

W3: Why should the outcome appear as the first badge specifically?
    Because: The outcome should be the primary visual indicator—appearing first in the status badge list ensures users see the final result before other status details [C4, C5]

W4: Why is immediate visibility of outcome critical?
    Because: The outcome (success/warn/fail) is the most important status signal for understanding whether work succeeded [C4, C5] [ASSUMPTION: user research indicates outcome is the first question asked]

W5: Why hasn't the outcome been integrated into the status badge display?
    Because: The completion record contains outcome data [C3], but the badge rendering logic doesn't currently retrieve or display it [ASSUMPTION: implementation gap reason]

Root Need: Provide immediate visual feedback on work item completion outcomes so users can assess success/failure at a glance without additional investigation [C1, C4, C5]

Summary: Display work item completion outcome as the first status badge to give users immediate visibility into whether items succeeded, warned, or failed.
