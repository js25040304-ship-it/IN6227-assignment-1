# Human Metric Check — RUN-006

Date confirmed: 2026-09-14
Run: `RUN-006`
Model checked: selected random forest
Source output: `runs/RUN-006/test_metrics.json`

## Reported confusion matrix

Using the stored class order, the four cells are:

- true negatives: 8,425
- false positives: 1,740
- false negatives: 723
- true positives: 2,445

## Manual calculations

Evaluated-row reconciliation:

`8425 + 1740 + 723 + 2445 = 13333`

Positive-class recall:

`2445 / (2445 + 723) = 2445 / 3168 = 0.7717803`

The result agrees with the RUN-006 reported positive-class recall of approximately `0.77178`.

## Human confirmation

The user stated in the project conversation on 2026-09-14 that they personally performed these calculations and confirmed that they were correct. This is recorded as human-oversight evidence H009. It is separate from the automated 13-check verification stored in `runs/RUN-006/verification.json`.
