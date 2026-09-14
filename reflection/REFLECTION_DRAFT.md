# Reflection

## Human oversight

I treated the SKILL's outputs as proposals to review rather than results to accept automatically. The prompts were only the interface through which I issued decisions; the oversight consisted of checking evidence, stopping progression, and deciding whether the workflow was safe to continue. When the workflow proposed moving to modelling, I required the unresolved profiling defects to be repaired first. Later, although the initial Phase 5 tests passed, I questioned whether the generalization checks were broad enough. This reopened the review and exposed unsupported report branches, incomplete all-model verification, weak time/group dependency handling, and an overly fixed model pair. I required regression tests before accepting the repairs.

My clearest modelling intervention concerned `composite_rank`. The SKILL flagged it as aggregate-like and highly correlated, but that did not prove leakage. I reviewed the development-only comparison with and without the feature. Because removal changed Macro-F1 by less than fold variability while eliminating uncertainty about prediction-time availability, I chose to drop it before the final test was evaluated. I also chose a bounded adaptive challenger policy: histogram gradient boosting for numeric/datetime-only data and random forest for mixed categorical data, with logistic regression as the common reference. If I repeated the work, I would obtain the construction formula and availability timing for aggregate features, plus entity/time dependency information, directly from the data owner before modelling.

## Critical evaluation

I found the proposed removal of `composite_rank` worth challenging because neither its name nor its correlation was sufficient evidence of leakage. Automatically deleting it could discard legitimate predictive information; automatically keeping it because of a slightly better score could preserve post-outcome information. I agreed with removal for this run only after considering both risks. The sensitivity analysis showed that the result did not materially depend on the feature, so exclusion had little development-performance cost and produced a more defensible evaluation. The labelled final test set was not used in this decision.

This remains a conditional judgement rather than a universal preprocessing rule. If domain evidence showed that `composite_rank` was calculated solely from information available at prediction time, I would reconsider retaining it. This case showed that statistical profiling can identify a question, but cannot resolve feature provenance without human or domain evidence.

## Trustworthiness

I manually reconstructed one reported result rather than relying only on the generated report. For the selected random forest, the confusion-matrix cells summed to the evaluated test size: `8,425 + 1,740 + 723 + 2,445 = 13,333`. I then calculated positive-class recall as `2,445 / (2,445 + 723) = 0.7717803`, matching the reported value. This check verified the class interpretation and denominator, not merely the displayed decimal.

I kept this manual check distinct from automated verification. In final RUN-008, the verifier recomputed metrics from saved row-level predictions for the dummy baseline, logistic regression, and random forest; all 54 consistency checks passed. RUN-008 also reproduced the selected random forest's held-out Macro-F1 of `0.768752`. These checks support computational consistency, but they do not prove that every real-world assumption is correct. Feature availability and row independence still require human judgement, which is why unresolved time/group structure now stops the SKILL before cross-validation.
