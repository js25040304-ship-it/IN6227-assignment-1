# Final grader audit

Date: 2026-09-21; final verification refreshed 2026-09-23
Scope: Variant 2 Skill, generated main report, Reflection, release state, current tests, and security review
Mode: final post-repair assessment; GitHub source release verified; no NTULearn upload was performed

## Overall verdict

The local submission PDF is content-complete and visually submission-ready. The preferred local DOCX/PDF workflow is well tested, the optional LaTeX renderer passes its regression, compilation, and visual checks, and the reviewed source is publicly available on GitHub at commit `6141425bb283d3a9eb8b5b69a1ab4ff7895218b5`.

Recommended decision: **content and GitHub source release accepted; NTULearn submission pending**. Submit only the verified three-page PDF when explicitly authorized.

## One-to-one assignment check

| Assignment requirement | Current evidence | Verdict |
| --- | --- | --- |
| Individual submission | One named student throughout | Pass |
| First-page matric number and full name | HU YINGXIN; G2608370F | Pass |
| Required assignment and variant lines | `IN6227-Assignment-1`; `Variant-2` | Pass |
| Reusable end-to-end classification Skill | Packaged Skill with profiling, modelling, verification, and reporting | Pass on preferred route |
| Dataset path as input | `run_workflow.py` accepts a dataset path | Pass |
| AI-selected preprocessing and model policy | Typed preprocessing plus adaptive logistic/boosting/forest candidate policy | Pass |
| Generalise beyond the supplied dataset | Current PHASE5-RUN-013 passes 13/13 scenarios; six modelled cases also generate and compile LaTeX | Pass |
| Generated main report no longer than two pages | Main report is exactly two A4 pages and was generated through the local DOCX/PDF route | Pass |
| Data exploration and cleaning | Missingness, outliers, duplicates, imbalance, split overlap, and policies are reported | Pass |
| Feature selection/engineering | `composite_rank` review, sensitivity evidence, and final exclusion are explained | Pass |
| Training, tuning, and stopping | Candidate families, fixed grids, selected settings, folds, seed, and one-pass bounded search are reported | Pass |
| Evaluation and comparison | Dummy, logistic regression, and random forest are compared with class-aware metrics | Pass |
| Findings and discussion | Trade-offs, cost threshold, limitations, and conclusion are explicit | Pass |
| GitHub repository link | Clickable public URL appears on page 1 | Pass for link presence |
| Model name/version and interface | Both Codex and DeepSeek environments are disclosed | Pass |
| Reflection outside the two-page limit | One separate Reflection page follows the two-page report | Pass |
| Human oversight | Concrete stop/review/decision actions are described | Pass |
| Critical evaluation | `composite_rank` removal is challenged conditionally | Pass |
| Trustworthiness | Manual confusion-matrix/recall check and automated 54-check verification are distinguished | Pass |
| Latest Skill Markdown available to teacher | Public `main` is commit `6141425...`; anonymous raw `SKILL.md` access verified | Pass |
| Single PDF for NTULearn | Three-page package: two-page report plus one-page Reflection | Pass; not uploaded |

## Current verification evidence

- Unit tests: 56 passed, 0 failed on the current worktree, including 19 LaTeX-route regressions.
- Official Skill validator: passed.
- PHASE5-RUN-013: 13/13 scenarios passed on the current worktree.
- Optional LaTeX route: 6/6 modelled cases generated and compiled locally with Tectonic 0.17.0 as two-page A4 PDFs; no unresolved placeholders, misspelled reference token, raw hostile-label `\\input`, clipping, overlap, broken table, or unreadable text remained across the 12 visually inspected pages.
- Final PDF: 3 A4 pages, no JavaScript, no form fields, visually clean.
- Final PDF SHA-256: `95b72b120dd147e6306543533c38c3a03cb077d9f017606e1b328221c8ed9df5`.
- Security review: complete coverage, no embedded credentials or private keys; the previously identified Low LaTeX-label injection path is fixed and regression-tested.

## Resolved findings

### M1. Advertised LaTeX route did not satisfy the Skill's generalisation claim — resolved locally

The earlier optional `render_latex_report.py` route passed only one of six representative modelled cases. Regression tests were added before implementation changes, then the renderer was generalized and rerun.

- Single-file tasks now describe internal holdouts without fabricating a supplied-test profile.
- Multiclass and unresolved-positive tasks no longer use invented binary semantics.
- Confusion matrices are interpreted by recorded labels rather than by a fixed index.
- Boosting references, selected-model comparisons, empty parameter fallbacks, and aggregate-feature prose are corrected.

Post-repair evidence: 19 focused tests pass; all six modelled cases generate `.tex` and compile to two-page A4 PDFs; the full 56-test suite, Skill validator, and 13-case Phase 5 grid pass.

The prior compiler gap is closed: an official Apple Silicon Tectonic 0.17.0 binary was checksum-verified against the GitHub release digest and used from a temporary directory. The compiler and cache are not part of the repository or submission.

### M2. Public GitHub did not contain the current final implementation — resolved

The reviewed 24-file source whitelist was committed locally and pushed to public `main`. Remote inspection now returns `6141425bb283d3a9eb8b5b69a1ab4ff7895218b5`, and an anonymous request successfully reads the current `tabular-classification-report/SKILL.md`.

Impact: the former release blocker is closed. Supplied course data, assignment files, private run artifacts, temporary renders, and identity-bearing PDFs remain excluded from GitHub.

## Resolved Low finding and release warning

### L1. Dataset class label was inserted into LaTeX without escaping — resolved locally

All dataset-controlled labels now pass through one-pass LaTeX escaping before interpolation. Hostile labels, commas, and placeholder-like text are regression-tested; strict GitHub URL validation also closes the adjacent raw-URL sink. Default DOCX/PDF generation remains unaffected.

Verification: the hostile-label test confirms that the payload is rendered as text and cannot become a raw `\\input` command.

### R1. `output/` was not ignored — resolved locally

The final identity-bearing PDFs remain local under `output/`, and `.gitignore` now explicitly excludes that directory.

Release control: use `reviews/GIT-SUBMISSION-WHITELIST.txt`; do not use a broad add operation.

## Teacher-perspective assessment

### Skill implementation

Strong evidence: typed refusal/checkpoint behavior, fold-local preprocessing, adaptive challenger selection, immutable runs, all-model verification, current 13-scenario forward testing, and a working one-command local PDF route.

The earlier LaTeX overclaim and release-state mismatch are resolved. The public source, current Skill fingerprint, final audit, and linked report now agree.

### Report

The two-page main report meets the brief, keeps quantitative claims traceable, explains the selected model rather than celebrating accuracy alone, includes limitations, and has a defensible reading order and visual hierarchy. Three references are sufficient for this short applied report because each supports a concrete method or metric choice and none is orphaned.

### Reflection

The Reflection directly covers Human oversight, Critical evaluation, and Trustworthiness. It does not reduce oversight to sending prompts; it records decisions that changed workflow progression and distinguishes computational consistency from unresolved domain assumptions. The user reviewed a Chinese translation and confirmed the first-person account.

## Ordered completion plan

1. Keep datasets, supplied course files, runs, temporary renders, and identity-bearing PDFs out of GitHub.
2. Upload the verified single PDF to NTULearn only after explicit authorization.
