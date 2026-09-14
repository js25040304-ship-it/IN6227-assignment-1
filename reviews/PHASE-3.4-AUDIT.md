# Phase 3.4 Methodology and Skill Audit

Date: 2026-09-14
Verdict: Pass for ordinary independent-row tabular classification after hardening; forward-testing remains required before final skill freeze.

## Scope

This audit reviewed the Phase 3.4 implementation, behavioral tests, RUN-005 artifacts, decision policy, artifact contract, and reproducibility claims. It distinguishes current-dataset validity from broader skill generalization.

## Resolved findings

| ID | Severity | Finding | Resolution evidence |
| --- | --- | --- | --- |
| M34-01 | Critical | The artifact contract required independent metric verification, but the training workflow did not generate it for future runs. | Added `scripts/verify_run.py`; RUN-006 `verification.json` independently checks metrics, confusion matrix, prediction rows, and evaluated rows. |
| M34-02 | Major | Cross-validation seeds were recorded but exact row-to-fold assignments were not persisted. | RUN-006 `fold_assignments.csv` contains all 31,109 unique development rows, with no unassigned row. |
| M34-03 | Major | Multiclass final metrics omitted macro/weighted precision and recall required by the decision policy. | Added all four metrics and behavioral assertions for multiclass output. |
| M34-04 | Major | `parent_profile_run` was an unverified label and could point to a run from different data. | Parent manifest is now resolved and its dataset SHA-256 must match; a mismatch test retains a failed run. |
| M34-05 | Major | A modelling exception could exit without the promised failed-run diagnostics. | Failures now retain manifest, profile, decision log, and `failure.json`; two failure-path tests pass. |
| M34-06 | Major | Model selection used the largest mean macro-F1 but did not execute the documented practical-tie rule. | Selection now uses paired identical-fold differences and a one-standard-error boundary before stability/simplicity tie-breakers. |
| M34-07 | Minor | High-cardinality categoricals could expand without a hard cap. | Fold-local one-hot encoding now uses unknown/infrequent handling, minimum frequency 2, and maximum 100 categories per input feature. |
| M34-08 | Minor | Convergence and other estimator warnings were not captured. | Logistic retry limit increased to 5,000 iterations; warnings are captured and unresolved convergence becomes a failed run. |

## RUN-006 verification

- Dataset SHA-256 matches parent RUN-005.
- Selected feature set excludes `composite_rank` as human-confirmed before test evaluation.
- Random forest beats logistic regression on four of five paired folds.
- Paired macro-F1 mean difference is 0.0093379; paired standard error is 0.0049814, so the result is not classified as a practical tie.
- All 31,109 development rows have one fold assignment: 6,222 / 6,222 / 6,222 / 6,222 / 6,221.
- All 13 automatic independent checks pass.
- RUN-006 final scalar metrics exactly match RUN-005, confirming deterministic reproduction under the same data, controls, seed, and environment.

## Remaining boundaries, not Phase 3.4 defects

- Grouped and ordered/time-dependent validation are outside v1. When the user supplies either dependency control, the skill now refuses random stratification and retains a failed diagnostic run.
- Broader claims of generalization remain conditional on Phase 5 forward-tests.
- Report rendering, page-limit verification, and human inspection of the final reported output remain Phase 3.5/3.6 and Phase 4.8 work.
