# Leakage-Aware Tabular Classification Report

This repository contains the reusable Codex skill developed for IN6227 Assignment 1, Variant 2. It profiles ordinary tabular classification data, applies leakage-aware preprocessing and model selection, independently verifies saved predictions, and generates a concise evidence-backed report.

The repository intentionally excludes the supplied course dataset, assignment brief, report template, real run artifacts, and temporary render files.

## What the skill supports

- CSV, TSV, Excel, directory, or ZIP input
- Binary and single-label multiclass classification
- Numeric, categorical, boolean, and conservatively detected datetime predictors
- Missing values and unseen test categories
- Profile-adaptive nonlinear challenge: histogram gradient boosting for numeric/datetime-only data, random forest for mixed categorical data, both against logistic regression and a dummy baseline
- Stratified development validation and a protected final holdout
- Machine-readable run records, predictions, fold assignments, metrics, independent verification, DOCX, and PDF output
- Pre-CV checkpoints for likely time/group dependence, plus safe refusal for unresolved targets, invalid class structures, incompatible splits, and unsupported dependent validation

## Repository structure

```text
tabular-classification-report/   Reusable Codex skill
  SKILL.md                       Entrypoint and safety boundaries
  agents/openai.yaml             Codex UI metadata
  scripts/                       Profiling, modelling, verification, and reporting
  references/                    Decision policy and artifact/report contracts
  tests/                         Deterministic behavior tests
design/                          Skill contract and decision-system rationale
reviews/                         Recorded hardening and human-review evidence
forward-tests/                   Generalization runner and summarized results
reflection/                      Evidence-grounded Variant 2 Reflection draft
PROJECT_TRACKER.md               Requirement, decision, experiment, and oversight log
```

## Environment

Use Python 3.13 in an isolated environment. The final RUN-008 was verified with Python 3.13.4 and the exact package versions pinned in `requirements.txt`. Installing them together avoids mixing incompatible binary packages.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r tabular-classification-report/requirements.txt
```

LibreOffice is required only when converting the generated DOCX report to PDF.

## Run the workflow

Profile a dataset without modelling:

```bash
python tabular-classification-report/scripts/profile_data.py /path/to/dataset
```

Run profiling, development comparison, final evaluation, and independent verification:

```bash
python tabular-classification-report/scripts/train_evaluate.py /path/to/dataset
```

If a suspicious aggregate feature creates a human checkpoint, review its development-only sensitivity evidence and explicitly rerun with either `--aggregate-policy keep` or `--aggregate-policy drop`. The final test set is not evaluated before that decision.

If datetime or repeated entity-like fields create a dependency checkpoint, confirm the rows are genuinely independent before rerunning with `--dependency-policy independent`. If rows are grouped or ordered, identify the column with `--group-column` or `--time-column`; v1 then refuses unsafe shuffled validation.

After a run reaches `modelled` status, assemble the verified report source:

```bash
python tabular-classification-report/scripts/assemble_report_data.py runs/RUN-NNN
```

Generate a report using a DOCX copy of the supplied template and real submission metadata:

```bash
python tabular-classification-report/scripts/generate_report.py \
  runs/RUN-NNN/report/report_data.json \
  --template-docx /path/to/template.docx \
  --full-name "YOUR NAME" \
  --matric-number "YOUR MATRIC NUMBER" \
  --github-url "https://github.com/OWNER/REPOSITORY" \
  --model-name "MODEL NAME" \
  --model-version "MODEL VERSION" \
  --llm-interface "INTERFACE" \
  --output-docx runs/RUN-NNN/report/report_source.docx \
  --output-pdf runs/RUN-NNN/report/main_report.pdf \
  --soffice /path/to/soffice
```

The generator rejects placeholder metadata and PDF output longer than two pages.

## Verification

Run the full behavior suite:

```bash
python -m unittest discover -s tabular-classification-report/tests -p 'test_*.py'
```

The current pre-submission version passes 35 unit tests and all 13 full-grid Phase 5 forward-test scenarios. PHASE5-RUN-006 rechecks the earlier adaptive model-family routing, pre-CV time/group dependency checkpoints, formats, classes, reports, and safe-refusal branches after a report readability and pagination change. RUN-008 is the immutable real-data modelling evidence; its run fingerprint predates this report-only change. Failed diagnostic runs and successful reruns are summarized in [forward-tests/PHASE-5-RESULTS.md](forward-tests/PHASE-5-RESULTS.md).

## Reproducibility and privacy

Every run records data and skill fingerprints, random seed, versions, preprocessing, candidate settings, fold assignments, predictions, metrics, warnings, decisions, and verification results. Run directories are immutable.

Do not commit private or course-restricted datasets. The provided `.gitignore` excludes the supplied course materials and all locally generated run artifacts by default.
