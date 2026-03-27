# Design: Nav Active Item Styling Fix

## Problem

The navigation active item uses a basic blue underline/highlight that looks
unprofessional. The current style is:

```
nav a.active { color: #7eb8f7; background: rgba(126, 184, 247, 0.12); border-radius: 4px; padding: 0.25rem 0.625rem; }
```

While it already has a subtle background fill and border-radius (improved from the
original plain underline), it still needs a more polished, professional appearance.

## Key File

- langgraph_pipeline/web/static/style.css (line 44) -- the nav a.active rule

## Design Approach

The frontend-coder agent will use the frontend-design skill to redesign the active
nav item styling. The work item specifies options like pill/capsule highlight, subtle
background fill, top accent bar, or inset indicator -- executed with precision against
the dark (#1a1a2e) nav background.

Since the work item has "Implementation Status: Review Required", the agent must first
validate the current state against acceptance criteria, then fix any shortcomings.

## Scope

This is a CSS-only change to a single rule in style.css. No structural HTML changes
are expected. The task is small enough for a single frontend-coder session.
