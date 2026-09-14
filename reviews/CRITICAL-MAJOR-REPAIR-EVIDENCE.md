# Critical/Major Repair Evidence

Date: 2026-09-14

## Scope and sequence

This pass addressed every Critical/Major issue found in the grading review. Regression assertions were added first and run against the old behavior; only then was the implementation changed and revalidated.

The first expanded run executed 31 tests and produced 14 failures plus 1 error. It reproduced zeroed full-feature CV values, fabricated multiclass binary metrics, `None recall`, omitted outlier/tuning evidence, missing all-model predictions, an unlabelled-test crash, and insufficient report-assembly verification.

## Repairs

| Defect | Repair and regression evidence |
| --- | --- |
| Multiclass probability metrics lost or fabricated | Preserve `roc_auc_ovr_weighted`; report weighted OvR ROC-AUC only; omit unsupported AP. Covered by assembler and report tests. |
| Full feature-set CV scores shown as zero | Record and use `selected_feature_set`. Covered by the full-feature report test. |
| Only the selected model verified | Save `predictions_all_models.csv` and recompute metrics for dummy, logistic, and random forest. Covered by training tests and RUN-007. |
| Saved verification could become stale | Hash metric/prediction inputs and rerun verification during assembly. Covered by the post-verification mutation test. |
| No semantic positive label rendered as `None recall` | Use balanced accuracy and class-balanced narrative. Covered by the unresolved-positive-label test and FT-007. |
| Outlier and tuning evidence omitted | Carry IQR counts into report data and state retention policy, evaluated values, and selected settings. Covered by report tests. |
| Contract promised unsupported controls | Remove separate `test_path` and user-selectable primary metric promises; document directory/ZIP pairs and fixed v1 Macro-F1. |
| Unlabelled test set crashed | Add predictions-only verification mode and omit final metrics explicitly. Covered by the training test and FT-009. |
| Forward tests used smoke grids and narrow formats | Remove `--smoke`; add TSV, XLSX, five-class, A/B, directory-pair, and unlabelled-test cases. |
| Real run predated final code | Rerun supplied data as RUN-007 using the final Skill fingerprint. |

## Final evidence

- Unit regression suite: 31 passed, 0 failed.
- Official Skill validator: passed.
- Full-grid forward testing: PHASE5-RUN-004, 11 passed, 0 failed; every generated main report was at most two pages.
- Real-data run: RUN-007, Skill SHA-256 `1038f884145b62765ac9c937692d6819d3ff8e4bab20a509ed424081589a2899`.
- RUN-007 verification: all three models covered; 54 checks passed.
- RUN-007 selected result: random forest; held-out Macro-F1 `0.7687520004525927`; balanced accuracy `0.8003023502362533`; positive recall `0.771780303030303`; 13,333 labelled test rows.
- RUN-007 report-data assembly reran verification against current input hashes and passed.

## Remaining submission work

The audited software defects are repaired, but the assignment itself is not submitted. Final identity/model/interface metadata, a real GitHub URL, the final PDF and reflection, visual QA of that PDF, link verification, and NTULearn submission remain open.
