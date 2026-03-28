# Archive 126 design docs classified as ARCHIVE by the audit

## Summary

The audit classified 126 docs as ARCHIVE — completed work with no ongoing
architectural value. Move them to docs/plans/archive/ to reduce noise.

## Acceptance Criteria

- Is docs/plans/archive/ created with all 126 ARCHIVE-classified docs?
  YES = pass, NO = fail
- Does docs/plans/ only contain KEEP and UPDATE docs after archiving?
  YES = pass, NO = fail

## LangSmith Trace: f5267658-8199-47a1-b933-ee0f666d4f0f


## 5 Whys Analysis

Title: Archive 126 completed design docs to reduce noise in active documentation
Clarity: 4
5 Whys:

1. Why do we need to move 126 design docs to an archive folder?
   - Because an audit identified them as ARCHIVE-classified docs representing completed work with no ongoing architectural value, yet they remain in the active docs/plans/ folder creating noise.

2. Why did the audit classify these docs as ARCHIVE rather than KEEP or UPDATE?
   - Because these docs documented finished projects, closed decisions, or historical context that no longer inform current or future development work.

3. Why are completed docs still sitting in the active documentation folder months or years after the work finished?
   - Because there's no automated or systematic process to move docs out of the active folder once the work they document is complete; they accumulate until someone explicitly archives them.

4. Why is clutter in the active documentation folder a problem?
   - Because it reduces signal-to-noise ratio for engineers looking for relevant context, makes it harder to distinguish what's currently relevant to decision-making, wastes time sifting through obsolete docs, and erodes trust in the documentation system.

5. Why does it matter for the documentation system to be clean and trustworthy?
   - Because design docs serve as the source of truth for architectural decisions and project context; outdated docs can mislead decisions, confuse onboarding, slow down problem-solving, and ultimately reduce the effectiveness of the development process.

Root Need: Establish a clean, trustworthy documentation structure where active design docs reflect current architectural decisions and ongoing work, with completed work archived separately to improve team efficiency and decision quality.

Summary: The core need is to separate the signal (active decisions) from the noise (completed work) in design documentation so engineers can quickly find relevant context without being misled by stale docs.
