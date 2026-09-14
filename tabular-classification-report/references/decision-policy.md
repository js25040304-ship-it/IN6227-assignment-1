# Decision Policy

Read this reference before choosing preprocessing, models, metrics, validation, or leakage responses.

## Gate order

Resolve input, target, task type, rows, and split structure before modelling. Then audit schema and leakage, build fold-safe preprocessing, compare a dummy baseline and two substantive classifiers, freeze the selected development configuration, evaluate the labelled final test once, and verify artifacts before reporting.

## Data audit

Record shapes, types, target counts, missingness, duplicates, constants, near-constants, numeric ranges, infinities, zeros, robust outlier flags, categorical cardinality, unseen test levels, suspicious IDs, high correlations, and train/test compatibility.

- Never impute target labels. Exclude missing training labels and record the count.
- Exclude all-missing and constant predictors with reasons.
- Impute other predictors inside the model pipeline.
- Flag predictors above 40% missingness; the threshold is a review signal, not an automatic deletion rule.
- Report duplicate or conflicting-predictor rows. Check exact predictor overlap across splits.
- Detect outliers, but do not delete or winsorize solely from an IQR rule.
- Treat string columns as datetime only when at least 95% of observed values parse and at least two distinct timestamps remain; record the evidence and assess temporal validation risk separately.

## Leakage

Remove clear leakage, including the target among predictors, preprocessing fitted before splitting, confirmed post-outcome fields, target copies, and final-test use during development.

Flag suspected leakage when a predictor is identifier-like, outcome-named, near-perfectly associated with the target, a suspicious aggregate, repeated across splits, or temporally unavailable at prediction time. Challenge it with a with/without sensitivity comparison when feasible; request human input when evidence cannot resolve the risk.

For a supplied labelled final test set, finish the aggregate sensitivity comparison using development folds, then obtain the keep/drop decision before computing final-test metrics. Never use the final-test difference to resolve that decision.

Make high-correlation and aggregate/rank findings visible in the run warning list and decision log. A stored profile value that never affects a downstream decision is not a completed audit.

## Preprocessing

- Numeric: median imputation; scale for scale-sensitive linear models.
- Boolean: stable binary or two-level categorical treatment while preserving missingness.
- Categorical: impute then one-hot encode with unknown handling.
- High-cardinality categorical: estimate expansion and use documented rare-level grouping, a supported alternative, exclusion with sensitivity analysis, or a checkpoint. Never target-encode outside folds.
- Datetime: derive prediction-time-valid components and first assess whether ordered validation is needed.
- Free text: unsupported in v1; request exclusion or stop.

A justified choice to retain all usable predictors is valid. Remove constants and confirmed IDs/leakage. Do not automatically drop correlated features; compare their effects across regularized linear and tree models.

## Models

Always score a `DummyClassifier` as a sanity baseline. It does not count as one of the two substantive models.

Controlled substantive pair:

1. regularized `LogisticRegression` as the common linear reference;
2. `HistGradientBoostingClassifier` for numeric/datetime-only usable predictors, or `RandomForestClassifier` when categorical predictors are present.

Record the profile-based challenger choice before tuning. Use a small, recorded search over regularization/class weighting for logistic regression; learning rate, iterations, leaf count, and L2 regularization for histogram gradient boosting; or tree count, depth, leaf size, feature sampling, and class weighting for random forest. Resolve convergence warnings within a bounded retry. Use resource-aware fallbacks rather than silently truncating work or installing performance-focused libraries.

## Metrics

Use macro-F1 as the default model-selection metric. Permit a valid user override.

For binary tasks, also report per-class precision, recall and F1, balanced accuracy, ROC-AUC when scores exist, average precision when the positive class is resolved, a confusion matrix, and accuracy for context only. Without a semantic positive class, report per-class results and macro averages rather than silently treating the minority as positive.

For multiclass tasks, report macro and weighted precision, recall and F1, balanced accuracy, confusion matrix, and one-vs-rest ROC-AUC only when valid.

Treat a minority share below 35% or a majority-to-minority ratio above 1.5 as an imbalance review signal. Never select or justify such a model using accuracy alone.

## Validation

- Use shuffled stratified cross-validation for ordinary independent rows.
- Treat detected datetime predictors and repeated entity-like values as review candidates, not proof of dependence. Stop before creating folds unless a human explicitly confirms independent rows.
- Default to five folds when each development class has at least five rows.
- Otherwise use at most the smallest class count, with at least two folds, and state high uncertainty.
- Stop when any class has fewer than two usable development rows.
- Reuse identical folds across models.
- Use group-aware or ordered validation when dependence is material; because those strategies are outside v1, refuse the modelling run rather than silently substituting random stratification.
- Tune only on development data. Compare the best substantive models using paired scores from the identical folds. Rank by the primary metric, then stability, baseline advantage, supporting trade-offs, simplicity, and runtime.
- Treat the models as a practical tie when the paired mean macro-F1 difference is no larger than one standard error of the paired fold differences; then prefer fold stability and finally logistic simplicity.
- Use the default decision threshold in v1 unless a cost objective is supplied. Any tuning uses out-of-fold development predictions, never final test labels.

## Integrity gate

Require target exclusion from predictors, fold-safe preprocessing, untouched final-test development, reconciled row counts, confusion-matrix totals matching evaluated rows, independently reproduced metrics, aligned row references, consistent class semantics, report values matching artifacts, recorded fingerprints/versions/decisions, and a visually valid report.
