# Final submission audit

Date: 2026-09-23
Status: source committed and publicly verified on GitHub; PDF not submitted to NTULearn

## Assignment requirements

| Requirement | Evidence | Result |
| --- | --- | --- |
| First page identifies student, assignment, and Variant 2 | HU YINGXIN; G2608370F; IN6227-Assignment-1; Variant-2 | Pass |
| Main generated report is no more than two pages | Main report is exactly two A4 pages | Pass |
| Model name/version and LLM interface are disclosed | `gpt-5.6-sol` / GPT-5.6 Sol / Codex Desktop (medium); `deepseek-flash` / DeepSeek-V4.1-Flash / DeepSeek API | Pass |
| GitHub Skill Markdown is linked and teacher-readable | Public `main` commit `6141425...` and anonymous raw `SKILL.md` access were verified | Pass |
| Reflection covers Human oversight, Critical evaluation, and Trustworthiness | Three explicit headings on a separate one-page Reflection | Pass |
| Reflection is outside the two-page main-report limit | Final package pages 1-2 are the main report; page 3 is labelled Reflection | Pass |

## Content and evidence checks

- RUN-008 remains the immutable real-data evidence. The dummy baseline, logistic regression, and random forest passed all 54 independent consistency checks.
- The selected random forest held-out macro-F1 is `0.768752` (reported as `0.769`), and the displayed confusion matrix reconciles to 13,333 rows.
- The report names `composite_rank`, explains that prediction-time provenance was uncertain rather than proven leakage, and records the development-only sensitivity result before final evaluation.
- The random-forest search is described as four coupled settings per feature set, explicitly not a full factorial grid.
- All three references are cited in the body. No reference is orphaned.
- The Reflection distinguishes model assistance from human decisions and distinguishes automated consistency checking from unresolved domain assumptions.

## Verification results

- Unit tests: 56 passed, 0 failed, including 19 focused LaTeX-route regressions.
- Official SKILL validator: passed.
- PHASE5-RUN-013: 13 of 13 scenarios passed on the final local source.
- Optional LaTeX route: all six modelled cases generated self-contained `.tex` reports and compiled locally with checksum-verified Tectonic 0.17.0 into two-page A4 PDFs. All 12 pages were visually inspected after the final natural-column-flow repair.
- One-command QA: dataset-to-verified-PDF completed locally in `ONE-COMMAND-QA`; structural and coordinate regressions now prohibit manual column breaks, enforce strict left-then-right reading flow, place the model-selection Discussion below the first-page quality table, open page two at the semantic Limitations boundary, keep Reproducibility after Skill generalisation, and require a complete References block. The two-page A4 output was visually inspected and required neither Overleaf nor a user-supplied DOCX template.
- Real RUN-008 main-report QA: the first layout render was rejected automatically at three pages. After evidence-preserving compression, the identity-bearing candidate is exactly two A4 pages; page one ends with Discussion, page two begins with Limitations, the left column continues through Conclusion, and the intact References block begins the right column. Both pages were rendered and visually inspected, the GitHub hyperlink remained active, and the final 56-test suite passed.
- Candidate content audit: 35 of 35 checks passed. These rehashed all 11 RUN-008 source artifacts recorded by `report_data.json`, reconciled the sample counts and confusion matrix, recomputed positive recall and precision, checked the rounded macro-F1 and balanced accuracy, reconstructed the false-negative/false-positive cost threshold, verified the paired-fold selection diagnostics, confirmed 54 of 54 saved verification checks, and confirmed that all three references are cited in the body.
- Final PDF: `output/pdf/IN6227_Assignment1_G2608370F.pdf`, SHA-256 `95b72b120dd147e6306543533c38c3a03cb077d9f017606e1b328221c8ed9df5`; 3 A4 pages consisting of the unchanged 2-page main report plus 1-page Reflection.
- Reflection review: Accept, with no Critical or Major defect. Human oversight, Critical evaluation, and Trustworthiness are explicit, first-person, evidence-bound, and consistent with the tracker and saved calculations.
- Visual inspection: all three pages rendered cleanly with no clipping, overlap, broken tables, missing headings, or unreadable text. The Reflection footer explicitly states that it is outside the two-page main-report limit.

## Remaining external actions

1. Keep the exact GitHub source whitelist unchanged unless a later correction is required.
2. Upload the verified PDF to NTULearn only after explicit authorization.
