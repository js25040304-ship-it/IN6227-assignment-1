# Leakage-Aware Tabular Classification Report

This repository contains the reusable Codex skill developed for IN6227 Assignment 1, Variant 2. It profiles ordinary tabular classification data, applies leakage-aware preprocessing and model selection, independently verifies saved predictions, and generates a concise evidence-backed report.

The work used two disclosed LLM environments: `gpt-5.6-sol` (GPT-5.6 Sol, medium reasoning) through Codex Desktop for the initial SKILL workflow, and the `deepseek-flash` API alias (DeepSeek-V4.1-Flash during the recorded work period) through DeepSeek's OpenAI-compatible Responses API for later refinement and review. Final report numbers are generated from verified run artifacts, not copied from model prose.

The repository intentionally excludes the supplied course dataset, assignment brief, report template, real run artifacts, and temporary render files.

## What the skill supports

- CSV, TSV, Excel, directory, or ZIP input
- Binary and single-label multiclass classification
- Numeric, categorical, boolean, and conservatively detected datetime predictors
- Missing values and unseen test categories
- Profile-adaptive nonlinear challenge: histogram gradient boosting for numeric/datetime-only data, random forest for mixed categorical data, both against logistic regression and a dummy baseline
- Stratified development validation and a protected final holdout
- Machine-readable run records, predictions, fold assignments, metrics, independent verification, and report output as DOCX, PDF, or LaTeX
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

Use Python 3.13 in an isolated environment. The final RUN-008 was verified with Python 3.13.4 and the exact package versions pinned in `requirements.txt`. The current release candidate was revalidated with the repository-local Python 3.13 environment. Installing the pinned packages together avoids mixing incompatible binary packages.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r tabular-classification-report/requirements.txt
```

LibreOffice is required for the direct one-command PDF route. Overleaf is optional and is needed only if you deliberately choose the alternative LaTeX route.

## Run the workflow

The preferred route is one command from dataset to verified PDF. It creates a minimal internal DOCX template when no template is supplied, so it does not depend on Overleaf or on manually converting the legacy course template:

```bash
python tabular-classification-report/scripts/run_workflow.py /path/to/dataset \
  --full-name "Ada Student" \
  --matric-number "G1234567X" \
  --github-url "https://github.com/OWNER/REPOSITORY" \
  --model-name "gpt-5.6-sol" \
  --model-version "GPT-5.6 Sol" \
  --llm-interface "Codex Desktop"
```

The final JSON line gives the immutable run directory and generated PDF path. If the data creates a leakage or row-dependency checkpoint, the command exits before final-test evaluation and report generation. Review the recorded evidence, then rerun into a new run directory with `--source-profile-run` and an explicit decision such as `--aggregate-policy keep`, `--aggregate-policy drop`, or `--dependency-policy independent`. The workflow never silently resolves those decisions.

The lower-level commands below remain available for inspection, debugging, and staged runs.

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

## Generate the LaTeX report

The same verified run can be rendered as a self-contained LaTeX document instead of a DOCX. Every number is interpolated from `report_data.json`, so the rendered report cannot drift from the saved evidence.

```bash
python tabular-classification-report/scripts/render_latex_report.py \
  runs/RUN-NNN/report/report_data.json \
  --output-tex runs/RUN-NNN/report/main.tex \
  --full-name "YOUR NAME" \
  --matric-number "YOUR MATRIC NUMBER" \
  --github-url "https://github.com/OWNER/REPOSITORY" \
  --model-name "MODEL NAME" \
  --model-version "MODEL VERSION" \
  --llm-interface "INTERFACE" \
  --reasoning-effort "medium"
```

Compile the result with pdfLaTeX. The document needs no external figures and no `.bib` file, so any LaTeX service compiles it unchanged. The layout lives in `tabular-classification-report/assets/report_template.tex`; edit that template rather than the generated file.

## Verification

Run the full behavior suite:

```bash
python -m unittest discover -s tabular-classification-report/tests -p 'test_*.py'
```

The current pre-submission version passes 56 unit tests and all 13 full-grid Phase 5 forward-test scenarios. The unit suite includes direct dataset-to-PDF checks, human checkpoints, and 19 LaTeX-route regressions covering single-file holdouts, multiclass output, unresolved positive-class semantics, label-based confusion-matrix orientation, reference selection, template placeholders, hostile labels, URL validation, and natural left-then-right column flow. PHASE5-RUN-013 rechecks adaptive model-family routing, pre-CV time/group dependency checkpoints, formats, classes, reports, and safe-refusal branches after the final LaTeX layout repair. All six modelled report variants generated and compiled locally with Tectonic 0.17.0 as two-page A4 PDFs; all 12 pages were visually inspected. RUN-008 remains the immutable real-data modelling evidence; its run fingerprint predates report-only changes. Earlier review files preserve the state observed at their recorded dates; the current release state is authoritative in `RELEASE_MANIFEST.json` and `reviews/FINAL-GRADER-AUDIT-2026-09-21.md`. Failed diagnostic runs and successful reruns are summarized in [forward-tests/PHASE-5-RESULTS.md](forward-tests/PHASE-5-RESULTS.md).

## Reproducibility and privacy

Every run records data and skill fingerprints, random seed, versions, preprocessing, candidate settings, fold assignments, predictions, metrics, warnings, decisions, and verification results. Run directories are immutable.

Do not commit private or course-restricted datasets. The provided `.gitignore` excludes the supplied course materials and all locally generated run artifacts by default.
