# Nav: active item styling looks amateurish

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Medium

## Summary

The active navigation item uses a plain blue underline (border-bottom: 2px solid
#7eb8f7) which looks cheap. Needs a professional redesign using frontend-design
skill.

## Current Style

    nav a.active { color: #7eb8f7; border-bottom: 2px solid #7eb8f7; }

## Expected Behavior

A polished active state that clearly communicates the current page without
looking like a default browser style. Consider a pill/capsule highlight,
a subtle background fill, a top accent bar, or an inset indicator — executed
with precision against the dark (#1a1a2e) nav background.
