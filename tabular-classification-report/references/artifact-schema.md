# Artifact Schema

Read this reference when creating, resuming, or verifying a run.

## Immutable run layout

Use a monotonically named run directory such as `runs/RUN-001/`. Never overwrite a non-empty run directory.

```text
runs/RUN-001/
|-- run_manifest.json
|-- data_profile.json
|-- decision_log.json
|-- cv_results.csv
|-- model_comparison.csv
|-- sensitivity_results.csv
|-- test_metrics.json
|-- predictions.csv
|-- predictions_all_models.csv
|-- fold_assignments.csv
|-- verification.json
|-- figures/
`-- report/
    |-- report_data.json
    |-- main_report.pdf
    `-- report_source.docx
```

Profiling creates the first three JSON files. Later stages add only their own artifacts and update the manifest without deleting earlier evidence.

## Run manifest

Require schema version, run ID, status, timestamps, dataset and full skill-package fingerprints, sources, split roles, target, task type, labels, positive-label resolution, seed, versions, row reconciliation, later modelling configuration, warnings, human checkpoints, errors, and artifact paths.

Use status values `profiled`, `needs_input`, `failed`, `modelled`, `reported`, and `verified`. A later status must not erase warnings or earlier decisions.

## Data profile

Require one object for each split with shape, columns, types, missingness, uniqueness, duplicates, numeric summaries, categorical summaries, and target distribution when labelled. Include cross-split schema, category, and predictor-overlap checks where applicable.

## Decision log

Store an ordered list with stable decision IDs. Each entry has timestamp, stage, decision, reason, evidence, and whether it was automatic or human-confirmed.

## Tables and predictions

- `cv_results.csv`: model, parameters, fold summaries, primary metric, and variability.
- `model_comparison.csv`: dummy baseline and two substantive models with clearly separated development/final results.
- `sensitivity_results.csv`: development-only with/without comparisons for suspicious predictors when applicable.
- `predictions.csv`: stable row reference, true label when available, predicted label, and supported class scores.
- `predictions_all_models.csv`: the same row-level evidence for the dummy baseline and both substantive models, enabling independent verification of every reported final metric.
- `test_metrics.json`: final labelled test metrics only; omit it and record why when labels do not exist.
- `fold_assignments.csv`: stable development-row reference and its fixed validation-fold number.
- `verification.json`: deterministic independent recomputation from saved predictions, including tolerance and pass/fail results. The assignment's human manual check remains a separate oversight artifact.

## Verification

Check required JSON keys, paths, fingerprints, row reconciliation, unique run ID, absence of placeholders, and agreement between machine-readable results and the report. Do not cite or report a value that exists only in prose.

## Report data

Create `report/report_data.json` with `scripts/assemble_report_data.py` only after the run is modelled and independent verification passes. It is the quantitative source of truth for report generation and contains source fingerprints, task and split summaries, quality findings and their resolutions, preprocessing, validation, development comparisons, final metrics, selection evidence, and runtime versions. The assembler must fail rather than produce a success payload when artifacts disagree, the selected model is ambiguous, a report-critical warning is unresolved, or verification failed.
