---
name: tabular-classification-report
description: Run a reproducible end-to-end workflow for ordinary tabular binary or single-label multiclass classification and generate an evidence-backed report. Use when a user supplies a CSV, TSV, Excel file, directory, or ZIP dataset and asks for classification analysis, model comparison, automated preprocessing, evaluation, or report generation. Do not use for regression, clustering, multilabel, image, text-only, or time-series tasks.
---

# Tabular Classification Report

Build a trustworthy classification result whose report can be traced to saved machine-readable evidence.

## Workflow

1. Resolve the supplied dataset path without uploading its contents.
2. For profile-only work, run `python <skill-path>/scripts/profile_data.py <dataset-path>`. For the end-to-end modelling stage, run `python <skill-path>/scripts/train_evaluate.py <dataset-path>` from the intended project output directory. Both allocate the next immutable `runs/RUN-NNN/`; use optional flags only for explicit user controls. Do not bypass a failed input, target, schema, type-compatibility, or class-validity gate.
3. Read [decision-policy.md](references/decision-policy.md) when selecting preprocessing, models, metrics, validation, or leakage responses.
4. Ask one focused question only when target identity, split semantics, positive-class meaning, or leakage/time/group risk cannot be resolved safely.
5. Resolve every recorded review warning before final evaluation. Fit all learned preprocessing inside the development pipeline. Keep labelled final test data outside feature decisions, tuning, threshold selection, and model choice. When datetime or repeated entity-like predictors suggest dependent rows, pause before cross-validation unless a human explicitly confirms independent rows with `--dependency-policy independent`; if dependence is real, refuse shuffled validation. When an aggregate/rank feature is suspicious, run the recorded with/without development comparison and pause before test evaluation unless a human has explicitly selected `--aggregate-policy keep` or `drop`.
6. Compare two meaningfully different substantive classifiers against a dummy baseline. Always use regularized logistic regression as the reference. Use histogram gradient boosting as the nonlinear challenger for numeric/datetime-only feature sets and random forest when categorical predictors require bounded one-hot encoding. Select from development evidence and report both substantive models.
7. Write every run using the stable files in [artifact-schema.md](references/artifact-schema.md). Never overwrite an earlier run.
8. Generate the report from saved artifacts, not from memory. First run `python <skill-path>/scripts/assemble_report_data.py <run-directory>` and use only the resulting `report/report_data.json` for quantitative report claims. For IN6227 output, read [in6227-report.md](references/in6227-report.md), convert the supplied legacy `.doc` template to `.docx` without modifying the source, then run `scripts/generate_report.py` with real identity, GitHub, model/version, and interface metadata. Missing metadata must stop generation; never leave placeholders. Render the DOCX to PDF and inspect every page.
9. Require `fold_assignments.csv` and the separate `scripts/verify_run.py` recomputation before accepting model results. Then verify row reconciliation, report values, and rendered page layout before calling later report stages complete.

## Boundaries

- Support binary and single-label multiclass classification on independent tabular rows.
- Detect datetime and repeated entity-like candidates, require an explicit independence decision before shuffled cross-validation, and refuse ordinary random validation when the user confirms a group or time dependency. Grouped and ordered validation remain outside v1 rather than being silently approximated.
- Stop cleanly for absent or ambiguous targets, single-class data, classes with fewer than two usable rows, unsafe archives, incompatible splits, or unsupported task types.
- Treat identifiers, suspicious aggregates, time columns, repeated entities, and near-perfect predictors as leakage warnings requiring evidence, not automatic accusations.
- Never impute target labels, invent domain meaning, choose a model from final test performance, or defend an imbalanced model with accuracy alone.
- Keep useful partial diagnostics after a failed modelling stage, but label the run failed and do not generate a success report.

## Reproducibility

Use a dedicated environment matching `requirements.txt`; do not mix binary packages compiled for different Python minor versions. Record input and full skill-package fingerprints, exclusions, seed, Python and package versions, split strategy, fold scores, preprocessing, search spaces, selected parameters, predictions, warnings, human checkpoints, and artifact paths. Reusing the same compatible inputs, controls, seed, and skill version should reproduce the split and materially identical metrics.
