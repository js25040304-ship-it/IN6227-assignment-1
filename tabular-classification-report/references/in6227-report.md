# IN6227 Variant 2 Report Requirements

Read this reference only when generating the IN6227 Assignment 1 deliverable.

## Main report

Generate one PDF main report of no more than two pages. Cover data exploration and cleaning, feature selection or engineering, training configuration including tuning and stopping criteria, evaluation and comparison of two classifiers, findings, and discussion.

At the top of page one include the user's matric number, full name, the exact line `IN6227-Assignment-1`, and `Variant-2`.

Include model name and version, LLM interface, and the GitHub link containing the skill Markdown. Never invent missing identity, environment, or repository values.

Follow the supplied Word template's two-column layout, Times New Roman 10-point body, in-text placement of compact tables/figures, and existing margins. Replace outdated 2023 placeholders. Do not shrink type or line spacing merely to fit the page limit.

The preferred complete route is `scripts/run_workflow.py`. It profiles, models, verifies, assembles `report/report_data.json`, and generates the two-column PDF locally through LibreOffice. When no DOCX template is supplied it creates a minimal internal template; Overleaf is not required.

Two manual output paths are also available. `scripts/generate_report.py` creates the DOCX/PDF, while `scripts/render_latex_report.py` fills `assets/report_template.tex` and emits one self-contained LaTeX file that compiles to the same two-column A4 layout with pdfLaTeX, needing no external figures and no `.bib` file. Choose one path per submission; both read only `report/report_data.json`, so every quantitative claim stays traceable to the verified run.

Never hand-edit generated report text. If the wording or layout must change, change the DOCX template, the LaTeX template, or the renderer, then regenerate.

## Reflection

Keep the short Reflection distinct from the generated two-page main report. Build it only from recorded human oversight, a challenged skill decision, a specific manual verification, and a confirmed future improvement. Do not fabricate first-person actions; ask the user to confirm final reflection statements.

## Submission checks

- main report is at most two pages;
- reflection is clearly separated;
- identity and Variant 2 metadata are present;
- GitHub link is accessible;
- figures, tables, symbols, and links render correctly;
- PDF is ready for NTULearn before 2026-10-07 23:59:59 Singapore time.
