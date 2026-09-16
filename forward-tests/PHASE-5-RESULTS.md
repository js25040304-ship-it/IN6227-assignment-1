# Phase 5 Forward-Test Results

Date: 2026-09-14
Purpose: test whether the reusable skill behaves correctly on structurally different classification datasets and on intentional refusal cases.

## Test protocol

- `forward-tests/run_phase5.py` creates deterministic synthetic inputs and assigns an immutable phase run directory.
- Modelled cases must complete profiling, model comparison, independent verification, report-data assembly, DOCX generation, and PDF conversion.
- Every generated PDF must contain no more than two pages.
- Refusal cases must return the expected manifest status and warning code without fabricating model results.
- Earlier phase runs are retained rather than overwritten.

## First run: PHASE5-RUN-001

Overall result: **failed, retained for diagnosis**.

| Case | Observed result | Diagnosis |
| --- | --- | --- |
| FT-001 numeric-only binary | Modelling and verification succeeded; report failed | Genuine skill defect: single-file runs stored `cross_split_checks` as null, while the report generator assumed a mapping |
| FT-002 mixed-type multiclass | Modelling and verification succeeded; report failed | Same genuine report defect |
| FT-003 missing/unseen category | Passed end to end | Missing-value warning and unseen `east` category were handled |
| FT-004 imbalanced binary | Modelling and verification succeeded; report failed | Same genuine report defect |
| FT-005A ambiguous target | Passed | Correctly returned `needs_input` with `TARGET_UNRESOLVED` |
| FT-005B absent target | Passed | Correctly returned `needs_input` with `TARGET_UNRESOLVED` |
| FT-006A too-small class | Skill correctly returned `failed` with `CLASS_TOO_SMALL`; harness marked it failed | Test-harness defect: it expected exit code 2 instead of the documented non-profiled exit code 3 |
| FT-006B single class | Skill correctly returned `failed` with `SINGLE_CLASS_TARGET`; harness marked it failed | Same test-harness defect |

Evidence: `forward-tests/artifacts/PHASE5-RUN-001/results.json`.

## Evidence-supported changes

1. The report generator now treats a null `cross_split_checks` value as an empty mapping and reports zero supplied-test overlap for a single-file holdout.
2. A dedicated regression test covers the null single-file case.
3. The forward-test harness now expects exit code 3 for both `needs_input` and terminal profiling failures and uses the manifest status to distinguish them.
4. No modelling policy, selection threshold, or metric was changed in response to synthetic performance.

After these changes, all 24 unit tests passed.

## Second run: PHASE5-RUN-002

Overall result: **8/8 scenarios passed**.

| Case | Expected behavior | Observed behavior | Result |
| --- | --- | --- | --- |
| FT-001 numeric-only binary | Infer a binary task, model and verify it, generate a two-page report | Selected logistic regression; verification passed; PDF has 2 pages | Pass |
| FT-002 mixed-type multiclass | Support numeric and categorical predictors and three classes | Selected logistic regression; all three classes evaluated; verification passed; PDF has 2 pages | Pass |
| FT-003 missing/unseen category | Impute missing data and safely encode an unseen test category | Recorded `MISSING_VALUES`; detected unseen `east`; selected random forest; verification passed; PDF has 2 pages | Pass |
| FT-004 imbalanced binary | Use macro-F1 and expose minority-class behavior against the dummy baseline | Recorded `CLASS_IMBALANCE`; primary metric was macro-F1; dummy positive recall was 0; selected logistic regression; verification passed; PDF has 2 pages | Pass |
| FT-005A ambiguous target | Request human input | `needs_input` with `TARGET_UNRESOLVED` | Pass |
| FT-005B absent target | Request human input | `needs_input` with `TARGET_UNRESOLVED` | Pass |
| FT-006A too-small class | Refuse unsafe stratification/modelling | `failed` with `CLASS_TOO_SMALL` | Pass |
| FT-006B single class | Refuse classification | `failed` with `SINGLE_CLASS_TARGET` | Pass |

Structural PDF inspection confirmed that all four modelled reports contain exactly two pages and a clickable GitHub hyperlink. Canonical DOCX renders for FT-002 and FT-004 were inspected page by page; no clipping, overlap, broken tables, missing glyphs, or margin overflow was found.

Evidence: `forward-tests/artifacts/PHASE5-RUN-002/results.json`, the per-case run directories beneath `forward-tests/artifacts/PHASE5-RUN-002/runs/`, and QA renders beneath `tmp/phase5-qa/`.

## Conclusion

The original Phase 5 passed its stated checks, but a later grading review showed that those checks were too narrow and used smoke grids.

## Hardened runs: PHASE5-RUN-003 and PHASE5-RUN-004

The harness was expanded to use the normal parameter grids and to cover TSV, XLSX, five-class reporting, unresolved A/B positive-class semantics, directory train/test discovery, and an unlabelled supplied test set. Modelled cases also require all-model metric verification, current evidence hashes, real development values in the report table, and task-appropriate probability-metric prose.

PHASE5-RUN-003 passed 10/11 scenarios. FT-002's generated metrics and two-page report were correct, but a harness substring check failed because PDF extraction inserted a line break between “weighted” and “OvR”. The failed run was retained and the assertion was corrected to normalize PDF whitespace.

PHASE5-RUN-004 passed 11/11 scenarios:

| Case | Added or retained coverage | Result |
| --- | --- | --- |
| FT-001 | Numeric binary TSV, full grid, full feature-set CV values | Pass |
| FT-002 | Mixed five-class XLSX, weighted OvR ROC-AUC, no fabricated AP | Pass |
| FT-003 | Missing values and unseen supplied-test category | Pass |
| FT-004 | Imbalanced binary task and dummy minority behavior | Pass |
| FT-005A/B | Ambiguous and absent target checkpoints | Pass |
| FT-006A/B | Too-small and single-class safe refusal | Pass |
| FT-007 | Binary A/B labels with no invented positive-class meaning | Pass |
| FT-008 | Directory-based labelled train/test pair | Pass |
| FT-009 | Unlabelled test predictions-only mode | Pass |

All reports generated in PHASE5-RUN-004 were at most two pages. Evidence is retained in `forward-tests/artifacts/PHASE5-RUN-003/results.json` and `forward-tests/artifacts/PHASE5-RUN-004/results.json`.

## Conclusion

Phase 5 now passes the hardened protocol. The skill generalizes across the tested task, format, semantic, and refusal branches; it verifies every reported model rather than only the selected model. Earlier failures and their repairs remain traceable.

## Major-risk rerun: PHASE5-RUN-005

After the final grading simulation identified missing automatic dependency gates and an overly fixed model pair, the harness was extended again. PHASE5-RUN-005 passed 13/13 full-grid scenarios.

- FT-001 and FT-008 confirmed that numeric-only data route to logistic regression plus histogram gradient boosting.
- FT-002 confirmed that mixed categorical data route to logistic regression plus random forest.
- FT-010A detected `event_date` as a time-review candidate and stopped before cross-validation.
- FT-010B detected repeated `subject_id` values as a group-review candidate and stopped before cross-validation.
- All previously covered formats, class structures, reports, all-model verification, and safe-refusal branches continued to pass.

Evidence: `forward-tests/artifacts/PHASE5-RUN-005/results.json` and `reviews/MAJOR-GENERALIZATION-RISK-REPAIR.md`.

## Report-readability rerun: PHASE5-RUN-006

On 2026-09-15, the report generator's parameter prose and table pagination were improved during the identity-bearing report review. PHASE5-RUN-006 then passed the same 13/13 full-grid scenarios, including six generated PDF reports. FT-002's five-class PDF and FT-004's imbalanced binary PDF were rendered and visually inspected on both pages; tables, captions, figures, and second-page sections remained legible with no split table, clipping, or overlap.

The modelling implementation was not changed in this rerun. RUN-008 remains immutable real-data evidence; its skill fingerprint belongs to the previous report-generator revision. Evidence: `forward-tests/artifacts/PHASE5-RUN-006/results.json` and `reviews/FINAL-REPORT-REVIEW.md`.
