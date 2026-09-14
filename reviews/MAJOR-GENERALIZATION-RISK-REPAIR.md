# Major Generalization Risk Repair

Date: 2026-09-14
Scope: the two Major risks found by the final grading simulation: time/group dependency handling and fixed model-family selection.

## Regression-first evidence

The tests were added before implementation changes:

- profiling must expose datetime and repeated entity-like dependency candidates;
- modelling must stop before creating cross-validation or test artifacts when a dependency candidate is unresolved;
- an explicit independent-row confirmation must be recorded before shuffled validation may proceed;
- numeric-only data must use logistic regression plus histogram gradient boosting, while mixed categorical data retains logistic regression plus random forest;
- report generation must render and discuss the adaptive boosting candidate without hard-coded random-forest prose.

The first test invocation showed the new profile assertions failing because `dependency_candidates` did not exist and the adaptive report assertion failing because the model label and narrative were hard-coded. Training regressions could not execute in that invocation because the earlier temporary environment was no longer present; the durable repository-local environment was recreated from the pinned requirements before the full red-to-green verification. No test expectation was weakened to obtain a pass.

## Implemented controls

1. Profiling now records every datetime predictor as a conservative time-review candidate and repeated entity-like values as a group-review candidate. These signals are explicitly review triggers, not claims that dependence exists.
2. The default modelling policy creates an immutable `needs_input` run before fold construction. `--dependency-policy independent` is the only supported confirmation path to shuffled validation; explicit `--group-column` or `--time-column` still causes v1 to refuse unsupported validation.
3. The substantive candidate pair is selected from training predictor types before tuning: logistic regression plus histogram gradient boosting for numeric/datetime-only data, or logistic regression plus random forest for mixed categorical data.
4. The paired-fold practical-tie rule and report prose are model-name agnostic. Final-test metrics remain excluded from candidate routing and model selection.

## Verification

- Unit tests: 35 passed, 0 failed.
- Official skill validator: passed.
- PHASE5-RUN-005: 13/13 scenarios passed with full grids and two-page report checks.
- FT-010A and FT-010B: time and group candidates both stopped before `cv_results.csv` or `test_metrics.json` existed.
- FT-001 and FT-008: numeric-only data used the histogram-gradient-boosting challenger.
- FT-002: mixed categorical data used the random-forest challenger.
- RUN-008: real-data full-grid reproduction selected random forest using development folds; all three models and 54 verification checks passed.

## Grading conclusion

Both Major risks are closed. The implementation now matches the contract's pre-CV dependency gate, and the nonlinear challenger is challenging without becoming an unconstrained model zoo. The candidate-routing rule is observable, deterministic, tested across data structures, and independent of final-test outcomes.
