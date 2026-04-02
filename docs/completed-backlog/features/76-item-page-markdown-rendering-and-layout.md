# Item page: render markdown and respect two-column layout

Two issues with the item detail page artifact display:

1. Markdown files are shown as raw text. They used to be rendered as formatted HTML (headings, lists, code blocks, etc.). Restore markdown rendering for all artifact content sections.

2. When an artifact section is expanded, it takes the full page width and pushes or overlaps the right column (plan tasks, completion history, etc.). Expanded content should stay within its column and not affect the sidebar layout.




## 5 Whys Analysis

Title: Item page artifact display — markdown rendering and layout integrity
Clarity: 4/5

**5 Whys:**

W1: Why can't users see properly formatted artifact content?
Because markdown files are displayed as raw text instead of processed HTML [C1, C2]

W2: Why is the artifact display not rendering markdown to HTML?
Because the markdown-to-HTML conversion isn't being applied in the display component [C1] [ASSUMPTION]

W3: Why would markdown rendering have stopped if it previously worked?
Because C2 states it "used to be rendered" — the implementation either reverted, changed rendering approach, or the processor was removed [C2] [ASSUMPTION]

W4: Why does the page layout break when artifacts are expanded?
Because the expanded content section takes full page width instead of being constrained to its column [C4, C5]

W5: Why doesn't the layout respect the two-column design when content expands?
Because the CSS or layout constraints on the artifact section don't enforce width/overflow limits appropriate for a sidebar layout [C5] [ASSUMPTION]

**Root Need:** Restore markdown rendering in artifact sections (C3) and implement layout constraints that preserve the two-column page structure during expansion (C5), while fixing the raw text display problem (C1) and the layout overflow issue (C4).

**Summary:** Users need artifacts to display as properly formatted markdown while maintaining stable two-column layout integrity when expanding sections.
