# Nav Active Item Styling Redesign

## Overview

Replace the plain `border-bottom: 2px solid #7eb8f7` active indicator on nav links
with a polished pill/capsule highlight that reads as clearly "selected" against the
dark `#1a1a2e` nav background.

## Key Files

- `langgraph_pipeline/web/static/style.css` — single change: replace `nav a.active` rule

## Design Decision

Use a pill/capsule approach: semi-transparent light background fill with the existing
accent colour (`#7eb8f7`) for the text, no border-bottom. This gives clear affordance
without the "default browser underline" feel and stays coherent with the existing
colour palette.

Proposed rule:

    nav a.active {
        color: #7eb8f7;
        background: rgba(126, 184, 247, 0.12);
        border-radius: 4px;
        padding: 0.25rem 0.625rem;
    }

The padding override extends the inherited `0.25rem 0` to add horizontal padding that
gives the capsule shape. No new classes, no JS changes.
