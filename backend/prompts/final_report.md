---
name: final_report
version: 1
description: Per-call brief for the report writer — synthesis material + formatting/citation rules.
variables: [date, synthesis]
updated: 2026-06-24
---
Today's date is {date}. Using the material below, write the final deep-research report.

<Material>
{synthesis}
</Material>

CRITICAL: Write the report in the SAME language as the research objective above.

Write a detailed, professional report that:
1. Is well-organized with markdown headings (`#` title, `##` sections, `###` subsections).
2. Includes the specific facts and insights from the findings — be comprehensive; users expect a
   thorough deep-research answer. Sections may be long.
3. References sources inline using `[Title](URL)` and assigns each unique URL a citation number.
4. Provides balanced, thorough analysis. Write in paragraphs by default; use bullets/tables when
   they genuinely help.
5. Does NOT include self-referential commentary ("in this report", "as the writer") — just write
   the report.
6. Only uses facts present in the material above. If a sub-topic is marked incomplete, write from
   what is available and do not fabricate.

Structure the report however best fits the question (comparison, list, overview, or a single
answer) — sections are a fluid concept.

<Citation Rules>
- Assign each unique URL a single citation number in the text.
- You MUST end with a `### Sources` section listing every source you cite.
- Number sources sequentially without gaps (1, 2, 3, …).
- Each source is its own list line, e.g.:
  1. Source Title: URL
  2. Source Title: URL
- Citations are essential — get them right; readers rely on them.
</Citation Rules>
