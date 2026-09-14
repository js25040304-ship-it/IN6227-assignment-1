# Tabular Classification Decision System

Status: Design baseline v1
Date: 2026-09-14

## 1 Decision principles

1. Protect evaluation validity before optimizing performance.
2. Prefer a simple documented decision over an unexplained complex choice.
3. Treat heuristics as warnings or proposals, not ground truth.
4. Fit every learned preprocessing step inside the training fold.
5. Keep the final test set outside model selection.
6. Preserve an audit trail for every exclusion, transformation, model, and metric.
7. Stop with a useful diagnostic when the evidence does not support a trustworthy result.

## 2 End to end decision flow

```text
Resolve input
  -> Resolve target and task type
  -> Validate rows, labels, and split structure
  -> Audit schema and leakage risks
  -> Build fold-safe preprocessing
  -> Select baseline and two candidate models
  -> Select metrics and validation strategy
  -> Tune on development data only
  -> Compare cross-validation performance and stability
  -> Freeze the selected configuration
  -> Evaluate once on labelled final test data
  -> Run integrity checks
  -> Generate artifacts and report
```

No later step may hide or bypass a failed earlier gate.

## 3 Data and schema audit

Record before modelling:

- physical source and fingerprint;
- table and split names;
- row and column counts;
- column names and inferred types;
- target classes, counts, and missing labels;
- predictor missingness by column and row;
- exact duplicate rows and duplicate predictor rows;
- constant and near-constant columns;
- numeric ranges, quantiles, zeros, infinities, and robust outlier flags;
- categorical cardinality, rare levels, and train/test level differences;
- date/time parse candidates;
- high-cardinality text or identifier candidates;
- split schema and datatype compatibility.

### 3.1 Duplicate policy

- Report exact duplicates.
- Remove exact duplicate training rows only when retaining them would unintentionally reweight identical observations; record the number and run a sensitivity check when duplicates are material.
- Never silently remove rows that share predictors but have conflicting labels; flag them as a data-quality issue.
- Check overlap between training and final test predictors. Exact overlap is a leakage warning and may require a grouped split or human review.

### 3.2 Missingness policy

- Drop rows with missing training labels and record them.
- Exclude all-missing and constant predictors with reasons.
- Keep other predictors by default and impute within the pipeline.
- Flag predictors above 40% missingness for sensitivity analysis or human review; do not automatically treat 40% as a universal deletion rule.
- Add missingness indicators only when missingness is material and cross-validation supports the added complexity.

### 3.3 Outlier policy

- Use quantiles, IQR flags, and distribution summaries to identify possible extreme values.
- Do not delete or winsorize rows solely because they cross an IQR threshold.
- Treat infinities and impossible parse results as errors or missing values with a recorded reason.
- Prefer models and scalers robust to observed distributions before destructive row removal.
- Apply transformations only inside the pipeline and retain them only when justified by validation or domain constraints.

## 4 Leakage audit

Classify each finding as `clear`, `suspected`, or `not detected`.

### 4.1 Clear leakage

- target column included among predictors;
- preprocessing fitted on all data before splitting or cross-validation;
- post-outcome field explicitly confirmed by the user or documentation;
- exact target encoding or deterministic target copy;
- final test labels used for feature selection, tuning, threshold choice, or model choice.

Clear leakage must be removed or the run must stop.

### 4.2 Suspected leakage

- column name suggests outcome, result, status-after-event, or aggregate rank;
- near-perfect association with the target;
- identifier-like feature is nearly unique and model performance depends heavily on it;
- a feature is mathematically reconstructible from target information;
- train/test overlap indicates repeated entities or observations;
- temporal order could allow future information into past predictions.

Suspected leakage triggers a documented challenge, not automatic accusation. Compare results with and without the feature when feasible and request human input when the risk cannot be resolved.

### 4.3 Identifier policy

- Exclude a column automatically only when it is both effectively unique and clearly named as an ID, row number, UUID, or index.
- Flag other high-cardinality columns rather than silently dropping them.
- Preserve a separate row reference for joining predictions back to source rows.

## 5 Feature typing and preprocessing

All learned operations live inside a scikit-learn `Pipeline` or equivalent fold-safe composite estimator.

| Feature type | Default treatment | Conditions and alternatives |
| --- | --- | --- |
| Numeric | Median imputation | Standardize for scale-sensitive linear models; tree model receives unscaled values where the pipeline design permits. |
| Boolean | Treat as a two-level categorical or stable 0/1 value | Preserve true missingness before conversion. |
| Low/moderate-cardinality categorical | Most-frequent or explicit missing-token imputation plus one-hot encoding with unknown handling | Group rare levels only when dimensionality or fold stability requires it; record the threshold. |
| High-cardinality categorical | Flag and estimate encoded dimensionality | Use rare-level grouping, supported alternative encoding, exclusion with sensitivity analysis, or a human checkpoint. Never target-encode outside folds. |
| Datetime | Derive defensible components such as year, month, weekday, or elapsed time | Do not preserve raw timestamps as arbitrary numbers; detect chronological validation needs first. |
| Free text | Unsupported in v1 | Ask to exclude it or route to a future text-capable version. |

### 5.1 Feature selection and engineering

- A justified decision to retain all usable features is valid.
- Remove constants and confirmed identifiers or leakage features.
- Use regularization or model-internal selection before adding a separate selection stage without evidence.
- Flag highly correlated numeric pairs; do not automatically remove them because regularized linear and tree models respond differently.
- For suspicious aggregate features, run a with/without sensitivity comparison when feasible.
- Every engineered feature must be computable from predictor information available at prediction time.

## 6 Model selection

### 6.1 Required baseline

Always evaluate a `DummyClassifier` using the same validation splits. It is a sanity check and does not count as one of the two required substantive models.

### 6.2 Profile-adaptive substantive pair

1. Regularized `LogisticRegression` as the common interpretable linear reference.
2. For numeric/datetime-only usable predictors, `HistGradientBoostingClassifier` as the nonlinear threshold/interaction challenger. When categorical predictors are present, use `RandomForestClassifier` after bounded one-hot encoding.

The challenger is fixed from the training-data type profile before tuning. This creates a meaningful linear/nonlinear comparison without selecting an algorithm from final-test performance.

### 6.3 Resource-aware fallbacks

- If one-hot expansion is too large for a reliable random forest run, group rare categorical levels or select a documented categorical-compatible fallback available in the environment.
- If the dataset is too large for the planned search budget, reduce the search space, use a reproducible stratified development sample for preliminary tuning, then refit the frozen configuration on full training data.
- If logistic regression fails to converge, scale numeric inputs, increase `max_iter` within a recorded limit, or use a suitable solver; do not ignore the warning.
- Do not install a new modelling library merely to chase performance unless its need and reproducibility value are clear.

### 6.4 Initial search spaces

Keep searches deliberately small and interpretable.

Logistic regression candidates:

- regularization strength `C` on a short logarithmic grid;
- `class_weight` as `None` or `balanced` when imbalance exists;
- solver compatible with the selected penalty;
- recorded convergence tolerance and `max_iter`.

Random forest candidates:

- number of trees;
- maximum depth including an unrestricted option when feasible;
- minimum samples per leaf;
- features considered per split;
- `class_weight` as `None` or `balanced` when imbalance exists.

Histogram gradient boosting candidates:

- learning rate;
- bounded iteration count;
- maximum leaf nodes;
- L2 regularization.

Use the same primary scoring rule and validation splits for fair comparison. Report the evaluated space, selected values, and stopping behavior.

## 7 Metric policy

### 7.1 Default model-selection metric

Use macro-averaged F1 as the default because it gives each class equal importance and applies to binary and multiclass classification. Permit an explicit user-selected metric when it matches the task.

### 7.2 Binary supporting metrics

- per-class precision, recall, and F1;
- balanced accuracy;
- ROC-AUC when probability or decision scores exist;
- average precision or PR-AUC when the positive class is resolved;
- confusion matrix;
- ordinary accuracy for context only.

When no semantic positive class is supplied, report per-class results and macro averages. Do not silently label the minority class as desirable or harmful.

### 7.3 Multiclass supporting metrics

- macro and weighted precision, recall, and F1;
- balanced accuracy;
- confusion matrix;
- one-vs-rest ROC-AUC only when valid scores and sufficient class representation exist.

### 7.4 Imbalance rule

Flag imbalance when class proportions are materially uneven. Treat a minority share below 35% or a majority-to-minority ratio above 1.5 as a review signal, not a universal scientific definition. In an imbalanced problem:

- never select or defend a model by accuracy alone;
- compare performance with the dummy baseline;
- consider class weighting within the tuning pipeline;
- show minority or per-class errors explicitly.

## 8 Validation policy

### 8.1 Cross-validation

- Use shuffled stratified cross-validation for ordinary independent rows.
- Default to five folds when every class has at least five development observations.
- Otherwise use at most the smallest class count, with a minimum of two folds, and report high uncertainty.
- Stop when any class has fewer than two usable development observations.
- Reuse the same splits across models.

### 8.2 Grouped or temporal data

- Flag every datetime predictor and repeated entity-like column as a dependency-review candidate.
- Stop before constructing shuffled folds until a human confirms row independence. Detection is a conservative review trigger, not proof of dependence.
- Prefer group-aware splitting when repeated entities are identified.
- Prefer ordered/forward validation for temporal prediction.
- Do not fall back silently to random stratification when dependence is plausible and material.

### 8.3 Hyperparameter selection

- Search only within development data.
- Rank by the primary metric, then use stability, complexity, and runtime as tie-breakers.
- Save fold scores, mean, standard deviation, and evaluated parameters.
- Treat small score differences relative to fold variability as practically tied rather than declaring a decisive winner.

### 8.4 Thresholds

- Use the estimator's default decision rule in v1 unless the user provides a cost objective.
- Any threshold optimization must use out-of-fold development predictions only and must be recorded separately.
- Never choose a threshold from final test labels.

### 8.5 Final test

- Freeze preprocessing, parameters, features, and threshold before final test evaluation.
- Evaluate the final test once.
- Compare final metrics with cross-validation mean and variation to identify possible distribution shift or overfitting.

## 9 Model choice and reporting rule

Choose the model with the best development evidence, not simply the highest test score.

Selection hierarchy:

1. primary cross-validation metric;
2. stability across folds;
3. advantage over dummy baseline;
4. material supporting-metric trade-offs;
5. simplicity and interpretability when performance is practically tied;
6. runtime and resource cost.

The report must include both substantive models even when one is selected. It must distinguish cross-validation results from final test results.

## 10 Integrity checks

Before a run can be marked successful:

- no target column is present in transformed predictors;
- preprocessing was fitted only through the development pipeline;
- the final test set did not enter tuning;
- row counts reconcile from source to exclusions to scored rows;
- confusion-matrix counts equal the number of evaluated labelled rows;
- independently recomputed metrics match saved metrics within numerical tolerance;
- class labels and positive-label interpretation are consistent;
- saved predictions align with stable row references;
- report numbers match machine-readable artifacts;
- random seed, versions, fingerprints, warnings, and decisions are present;
- generated report renders without clipping and satisfies the page limit.

## 11 Failure and uncertainty policy

| Condition | Required behavior |
| --- | --- |
| Missing or unreadable input | Stop and name the path or parse failure. |
| Unsafe ZIP member path | Refuse extraction and report the member. |
| Ambiguous table or target | Request one focused user choice before training. |
| Single-class target | Stop; classification evaluation is impossible. |
| Class with one usable row | Stop; stratified validation is not defensible. |
| Very small classes | Reduce fold count and state high uncertainty. |
| Train/test schema mismatch | Stop or align only clearly optional extra columns; record the decision. |
| Unlabelled test set | Produce predictions and cross-validation evidence; do not invent test metrics. |
| Unsupported free text, multilabel, regression, or time series | Explain the boundary and do not misclassify the task as supported tabular classification. |
| Memory or runtime limit | Reduce the documented search budget or stop with partial artifacts; never present partial work as a finished comparison. |
| Metric undefined | Explain why, omit it, and retain valid alternatives. |
| Model warning or convergence failure | Diagnose, retry within a bounded documented rule, or mark the candidate failed. |
| Report exceeds two pages | Reduce low-value content or visuals without changing required typography; rerender and verify. |

## 12 Supplied dataset application notes

These are run-specific evidence, not universal skill rules:

- Target candidate `label` is unambiguous by name.
- Training and test files are both labelled.
- Missing training labels must be excluded; the missing test label cannot enter final metrics.
- The class distribution is approximately 76% `no` and 24% `yes`, so accuracy alone is unsuitable.
- `composite_rank` is strongly correlated with several numeric predictors and must be challenged through a leakage review and with/without sensitivity run.
- The data contain mixed numeric and categorical predictors and are suitable for the default logistic-regression versus random-forest comparison.

## 13 Implementation gates

Implementation may begin when:

- input and output schemas match the skill contract;
- target and split rules have no unresolved contradiction;
- model and metric defaults have documented fallbacks;
- failure conditions are expressible as deterministic checks or clear human checkpoints;
- the run artifacts are sufficient to verify the final report and support Reflection.
