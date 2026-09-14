# Phase 3.6 Report Generation and Layout QA

Date: 2026-09-14
Source run: `RUN-006`
Purpose: validate automated two-page report generation before inserting the user's final identity and repository metadata.

## Implementation

- `scripts/generate_report.py` consumes only verified `report/report_data.json` for quantitative claims.
- It requires non-placeholder full name, matric number, GitHub URL, model name/version, and LLM interface metadata.
- It uses the supplied report template's A4 geometry, full-width title block, two-column body, Times New Roman 10-point body, compact in-text table/figure treatment, and understated header/footer styling.
- It supports binary and multiclass wording; binary reports show positive-class recall, while multiclass reports use balanced accuracy.
- It creates an editable DOCX source and can convert it to PDF through LibreOffice.

## Template fidelity

- Original template SHA-256 before and after work: `0970df1de8f5cb6ec4b55ea9ce5c3637d3c44b502c2287e27e6a1214492588df`.
- The legacy `.doc` was converted to a temporary `.docx` inspection copy; the source was not edited.
- The converted reference's trailing blank page and inconsistent third-section margins were identified as conversion residue and intentionally not reproduced.
- Detailed template measurements and slot decisions are recorded in `tmp/report-build/artifact.md` during development.

## Iterative visual findings

1. First render exposed column-width table overflow and an underfilled second page.
2. Fixed-width, left-aligned column tables resolved the clipped model-name and confusion-matrix columns.
3. A continuous-section page break placed page-two content above the intended margin in LibreOffice.
4. Replacing it with an explicit new-page two-column section plus controlled top spacing restored readable page-two placement.
5. A single-paragraph footer made page numbering stable across both pages.

## Final QA result

- Canonical DOCX render: 2 pages.
- Direct PDF output: 2 pages, A4 (`595.304 x 841.89` points), PDF 1.7.
- Visual inspection: no clipping, overlap, broken table, missing glyph, overflow, or blank trailing page.
- Extracted word bounds stayed inside the physical page: page 1 `x=54.1..525.7`, page 2 `x=54.1..541.1`; headers/footers remained within vertical bounds.
- Required text and values were extractable: assignment line, variant, selected model, confusion-matrix cells, reproducibility section, and references.
- No legacy template placeholders remained in the rendered QA PDF.
- The QA identity and GitHub URL were explicitly synthetic layout-test values. This PDF is not a submission artifact and must not be used as the final report.

## Pre-Phase-5 hardening recheck

At the user's request, Phases 3.5 and 3.6 were reopened and checked again before accepting the forward tests.

- Report prose now follows the actually selected model instead of assuming random forest.
- The GitHub value is a real external DOCX hyperlink and remains clickable after PDF conversion.
- Report generation rejects output exceeding two pages before copying the final files.
- Confusion-matrix layout remains bounded for larger multiclass tasks by using a compact lowest-recall summary when there are more than three classes; the full matrix remains in the run artifacts.
- Report-data assembly now rejects malformed numeric/JSON cells, empty or failed independent-verification checks, and any run whose test labels influenced feature or model selection.
- Phase 5 exposed one additional single-file edge case: `cross_split_checks` may correctly be null when no supplied test split exists. The report generator now handles this explicitly, with a regression test.
- The complete suite contains 24 passing tests: eight profiling, five modelling, seven report-data assembly, and four report-generation tests.
- A fresh RUN-006 QA build remained exactly two pages and retained the required quantitative values and clickable hyperlink.
- Phase 5's representative three-class and imbalanced reports were also rendered and inspected page by page; both remained legible and within margins.

## Gate remaining

The final RUN-006 report is intentionally not generated until the user supplies their real full name and matric number and a real GitHub link is available. P4.8 remains pending until that final artifact is rendered and inspected.
## Post-grading-repair RUN-007 QA

On 2026-09-14, the final-code RUN-007 report data was rendered with explicitly non-submission QA metadata after the Critical/Major repair pass. Structural inspection confirmed A4 format and exactly two pages. Both pages were rendered at 150 dpi and visually inspected in full.

The added outlier policy, exact evaluated parameter values, selected settings, corrected development metrics, three-model verification count, tables, and figure remained legible. No clipping, overlap, broken table, missing glyph, or margin overflow was observed. This render is layout evidence only; the identity-bearing final submission report remains pending.
