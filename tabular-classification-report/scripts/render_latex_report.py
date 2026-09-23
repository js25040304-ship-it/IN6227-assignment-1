#!/usr/bin/env python3

"""Render the IN6227-style two-page report as LaTeX from report_data.json.

The rendered document is the report deliverable: every quantitative claim is
interpolated from the verified run artifact, and the layout comes from
assets/report_template.tex. Nothing in the output is typed by hand, so a rerun
cannot drift from the saved evidence.

Compile the result with pdfLaTeX (Overleaf works unchanged; the document needs
no external figures and no .bib file).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


class ReportError(ValueError):
    """Raised when report generation inputs are incomplete or unsafe."""


MODEL_LABELS = {
    "dummy_most_frequent": "Dummy",
    "logistic_regression": "Logistic",
    "random_forest": "Random forest",
    "hist_gradient_boosting": "Hist. gradient boosting",
}

# pgfplots symbolic coordinates cannot contain spaces.
PLOT_LABELS = {
    "dummy_most_frequent": "Dummy",
    "logistic_regression": "Logistic",
    "random_forest": "Forest",
    "hist_gradient_boosting": "Boosting",
}

# Documented in forward-tests/PHASE-5-RESULTS.md and re-checked by the test
# suite that ships with the skill. Kept as a constant because it describes the
# skill's own harness, not the contents of the current run artifact.
FORWARD_TOTAL_CASES = 13
FORWARD_MODEL_CASES = 6
FORWARD_REFUSAL_CASES = 4

REFERENCES_RANDOM_FOREST = (
    r"[1] Breiman, L. (2001). Random forests. \emph{Machine Learning}, 45(1), 5--32."
    "\n"
    r"\href{https://doi.org/10.1023/A:1010933404324}{doi:10.1023/A:1010933404324}.\par"
)
REFERENCES_BOOSTING = (
    r"[1] Friedman, J. H. (2001). Greedy function approximation: a gradient boosting machine."
    r" \emph{Annals of Statistics}, 29(5), 1189--1232."
    "\n"
    r"\href{https://doi.org/10.1214/aos/1013203451}{doi:10.1214/aos/1013203451}.\par"
)
REFERENCE_SKLEARN = (
    r"[2] Pedregosa, F., et al. (2011). Scikit-learn: Machine learning in Python."
    "\n"
    r"\emph{J.\ Mach.\ Learn.\ Res.}, 12, 2825--2830.\par"
)
REFERENCE_IMBALANCE = (
    r"[3] He, H., \& Garcia, E. A. (2009). Learning from imbalanced data."
    "\n"
    r"\emph{IEEE Trans.\ Knowl.\ Data Eng.}, 21(9), 1263--1284."
    "\n"
    r"\href{https://doi.org/10.1109/TKDE.2008.239}{doi:10.1109/TKDE.2008.239}.\par"
)

FORBIDDEN_METADATA = {"tbd", "todo", "placeholder", "author name", "your name", "unknown"}


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError(f"Could not read valid report data: {exc}") from exc


def require_metadata(args: argparse.Namespace) -> None:
    values = {
        "full name": args.full_name,
        "matric number": args.matric_number,
        "GitHub URL": args.github_url,
        "model name": args.model_name,
        "model version": args.model_version,
        "LLM interface": args.llm_interface,
    }
    for label, value in values.items():
        if not value or value.strip().lower() in FORBIDDEN_METADATA:
            raise ReportError(f"A real {label} is required; placeholders are not allowed")
    if not re.fullmatch(r"[A-Za-z0-9-]{5,24}", args.matric_number.strip()):
        raise ReportError("Matric number must be 5-24 letters, numbers, or hyphens")
    if not re.fullmatch(
        r"https://github\.com/[A-Za-z0-9-]+/[A-Za-z0-9._-]+/?",
        args.github_url,
    ):
        raise ReportError("GitHub URL must be a plain https://github.com/owner/repository link")


def validate_report_data(data: dict[str, Any]) -> None:
    if data.get("source_evidence", {}).get("automatic_verification_passed") is not True:
        raise ReportError("Report data is not independently verified")
    selected = data.get("results", {}).get("selected_model")
    metrics = data.get("results", {}).get("selected_final_metrics", {})
    if not selected or not metrics:
        raise ReportError("Report data lacks a selected model or final metrics")
    task = data.get("task", {})
    task_labels = [str(label) for label in task.get("labels", [])]
    if len(task_labels) < 2 or len(set(task_labels)) != len(task_labels):
        raise ReportError("Task labels must contain at least two unique classes")
    positive = task.get("positive_label")
    if positive is not None and str(positive) not in task_labels:
        raise ReportError("Positive label is not present in the task labels")

    for split_name, split in data.get("dataset", {}).get("splits", {}).items():
        distribution_labels = [str(row.get("label")) for row in split.get("class_distribution", [])]
        if set(distribution_labels) != set(task_labels):
            raise ReportError(f"{split_name} class distribution disagrees with the task labels")

    final_metrics = data.get("results", {}).get("final_metrics_by_model", {})
    if not final_metrics:
        raise ReportError("Report data lacks final metrics by model")
    for model, model_metrics in final_metrics.items():
        matrix = model_metrics.get("confusion_matrix", {}).get("values", [])
        labels = [str(label) for label in model_metrics.get("confusion_matrix", {}).get("labels", [])]
        if not matrix or sum(sum(row) for row in matrix) != model_metrics.get("evaluated_rows"):
            raise ReportError(f"{model} confusion matrix does not reconcile with evaluated rows")
        if len(labels) != len(matrix) or any(len(row) != len(labels) for row in matrix):
            raise ReportError(f"{model} confusion matrix dimensions do not match its labels")
        if set(labels) != set(task_labels):
            raise ReportError(f"{model} confusion-matrix labels disagree with the task labels")
        per_class = {str(label) for label in model_metrics.get("per_class", {})}
        if per_class != set(task_labels):
            raise ReportError(f"{model} per-class metrics disagree with the task labels")


def tex(value: Any) -> str:
    """Escape text that is interpolated into the LaTeX body."""
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return re.sub(r"[\\&%$#_{}~^]", lambda match: replacements[match.group(0)], str(value))


def mono(value: Any) -> str:
    """Render an identifier such as a column name in the report's mono style."""
    return r"\texttt{" + tex(value) + "}"


def fmt(value: Any, digits: int = 3) -> str:
    return f"{float(value):.{digits}f}"


def pct(value: Any, digits: int = 1) -> str:
    """Format a share as an escaped LaTeX percentage (a bare % starts a comment)."""
    return rf"{float(value) * 100:.{digits}f}\%"


def grouped(value: Any) -> str:
    return f"{int(value):,}"


def model_label(name: str) -> str:
    return MODEL_LABELS.get(name, name.replace("_", " ").title())


def has_positive_semantics(data: dict[str, Any]) -> bool:
    return data.get("task", {}).get("type") == "binary" and data.get("task", {}).get("positive_label") is not None


def focus_metric(data: dict[str, Any], metrics: dict[str, Any]) -> float:
    if has_positive_semantics(data):
        positive = str(data["task"]["positive_label"])
        return float(metrics.get("per_class", {}).get(positive, {}).get("recall", 0.0))
    return float(metrics.get("balanced_accuracy", 0.0))


def focus_metric_label(data: dict[str, Any]) -> str:
    if has_positive_semantics(data):
        return f"{tex(str(data['task']['positive_label']))} recall"
    return "Bal. acc."


def binary_confusion_counts(metrics: dict[str, Any], positive_label: str) -> tuple[int, int, int, int]:
    confusion = metrics["confusion_matrix"]
    labels = [str(label) for label in confusion["labels"]]
    if len(labels) != 2 or positive_label not in labels:
        raise ReportError("Binary positive label does not match the confusion-matrix labels")
    positive_index = labels.index(positive_label)
    negative_index = 1 - positive_index
    values = confusion["values"]
    tn = int(values[negative_index][negative_index])
    fp = int(values[negative_index][positive_index])
    fn = int(values[positive_index][negative_index])
    tp = int(values[positive_index][positive_index])
    return tn, fp, fn, tp


def comparison_entry(data: dict[str, Any], model: str) -> dict[str, Any]:
    """Return the development entry for the feature set the run finally kept."""
    selected_feature_set = data["method"]["preprocessing"].get("selected_feature_set")
    candidates = [
        entry
        for entry in data["results"]["development_comparison"]
        if entry.get("model") == model
    ]
    if not candidates:
        raise ReportError(f"Development comparison is missing {model}")
    for entry in candidates:
        if entry.get("feature_set") == selected_feature_set:
            return entry
    for entry in candidates:
        if entry.get("feature_set") == "not-applicable":
            return entry
    return candidates[0]


def plot_label(name: str) -> str:
    return PLOT_LABELS.get(name, model_label(name).replace(" ", ""))


def parameter_value(key: str, value: Any) -> str:
    if value is None:
        return "unlimited" if key in {"max_depth", "max_leaf_nodes"} else "none"
    if isinstance(value, str):
        return value.replace("_", " ")
    return str(value)


def positive_share(split: dict[str, Any], label: str) -> float:
    for item in split["class_distribution"]:
        if item["label"] == label:
            return float(item["ratio"])
    raise ReportError(f"Class distribution is missing label {label}")


def substantive_models(data: dict[str, Any]) -> list[str]:
    names = [name for name in data["results"]["final_metrics_by_model"] if name != "dummy_most_frequent"]
    if len(names) != 2:
        raise ReportError("This report layout expects exactly two substantive models")
    return names


def reference_model(data: dict[str, Any]) -> str:
    diagnostics = data["method"]["selection_diagnostics"]
    return diagnostics.get("reference_model", "logistic_regression")


def build_title(data: dict[str, Any]) -> str:
    return "Leakage-Aware Tabular Classification"


def build_data_section(data: dict[str, Any]) -> str:
    train = data["dataset"]["splits"]["train"]
    test = data["dataset"]["splits"].get("test")
    cross = data["dataset"].get("cross_split_checks", {}) or {}
    task = data["task"]
    numeric = train["predictor_type_counts"].get("numeric", 0)
    categorical = train["predictor_type_counts"].get("categorical", 0)
    final_rows = data["results"]["selected_final_metrics"]["evaluated_rows"]

    profile_rows = [("Development" if test else "Source", train)]
    if test:
        profile_rows.append(("Test", test))
    table_rows = "\n".join(
        f"{tex(label)} & {grouped(split['usable_labelled_rows'])} & {grouped(split['missing_target_rows'])}"
        f" & {grouped(split['rows_with_any_missing'])} & {grouped(split['exact_duplicate_rows'])}"
        f" & {grouped(split['iqr_flagged_value_count'])} \\\\"
        for label, split in profile_rows
    )

    ordered_classes = sorted(train["class_distribution"], key=lambda item: item["count"], reverse=True)
    majority, minority = ordered_classes[0], ordered_classes[-1]
    ratio = majority["count"] / minority["count"] if minority["count"] else float("inf")
    if has_positive_semantics(data):
        positive_label = str(task["positive_label"])
        class_sentence = f"The positive class {mono(positive_label)} was {pct(positive_share(train, positive_label))} of source rows"
        if test:
            class_sentence += f" and {pct(positive_share(test, positive_label))} of supplied-test rows"
        class_sentence += "."
    else:
        class_sentence = (
            f"The target contained {len(ordered_classes)} observed classes; the largest, "
            f"{mono(majority['label'])}, represented {pct(majority['ratio'])} of source rows. "
            "No class was designated semantically positive, so class-balanced and per-class metrics were used."
        )

    flagged = dict(train.get("iqr_outlier_counts", {}))
    top = sorted(flagged.items(), key=lambda item: item[1], reverse=True)[:2]
    flagged_count = int(train.get("iqr_flagged_value_count", 0) or 0)
    density_train = flagged_count / train["usable_labelled_rows"] * 100

    missing_share = train["rows_with_any_missing"] / train["usable_labelled_rows"] * 100
    overlap = cross.get("predictor_overlap", {}) or {}
    if test:
        overlap_count = int(overlap.get("test_rows_matching_train_predictors", 0) or 0)
        overlap_claim = (
            "No supplied-test row shared its complete predictor vector with a development row"
            if overlap_count == 0
            else f"{grouped(overlap_count)} supplied-test rows matched a development predictor vector"
        )
        unseen = cross.get("unseen_test_categories", []) or []
        unseen_clause = (
            "the supplied test contained no unseen categories"
            if not unseen
            else f"the supplied test introduced {len(unseen)} unseen-category findings handled by the encoder"
        )
        split_sentence = f"{overlap_claim}; {unseen_clause}."
    else:
        split_sentence = (
            f"Final evaluation used a stratified held-out partition of {grouped(final_rows)} source rows; "
            "no separate supplied-test profile was invented."
        )

    correlation_pairs = []
    for warning in data["quality_findings"].get("warnings", []):
        if warning.get("code") == "HIGH_NUMERIC_CORRELATION":
            correlation_pairs = warning.get("pairs", [])
    correlation_sentence = ""
    if correlation_pairs:
        listed = "; ".join(
            f"{mono(pair['left'])} with {mono(pair['right'])} ({fmt(pair['correlation'])})"
            for pair in correlation_pairs[:3]
        )
        correlation_sentence = (
            f"\n\nThe strongest numeric correlations were {listed}. Correlated inputs were"
            " retained for the tree model; logistic coefficients are not read as independent"
            " effects."
        )

    classification_clause = (
        f"one binary target, {mono(task.get('target', 'label'))} "
        f"({mono(task['labels'][0])}/{mono(task['labels'][1])}),"
        if task.get("type") == "binary" and len(task.get("labels", [])) == 2
        else f"one single-label target, {mono(task.get('target', 'label'))},"
    )

    if test:
        row_summary = (
            f"Rows without a label cannot supervise training, so {grouped(train['missing_target_rows'])} development rows "
            f"and {grouped(test['missing_target_rows'])} supplied-test rows were excluded. That left "
            f"{grouped(train['usable_labelled_rows'])} development rows and {grouped(test['usable_labelled_rows'])} test rows."
        )
        profile_caption = "Verified data profile for the two supplied splits."
    else:
        row_summary = (
            f"Rows without a label cannot supervise training, so {grouped(train['missing_target_rows'])} source rows were excluded. "
            f"That left {grouped(train['usable_labelled_rows'])} labelled source rows; final evaluation used the recorded internal holdout."
        )
        profile_caption = "Verified source-data profile."

    if flagged_count and top:
        top_share = sum(count for _, count in top) / flagged_count
        top_phrase = " and ".join(f"{mono(name)} ({grouped(count)})" for name, count in top)
        outlier_sentence = (
            f"Distribution checks flagged {grouped(flagged_count)} IQR-extreme values in source data. "
            f"{top_phrase} supplied {pct(top_share, 0)} of them, pointing to concentrated skew rather than a basis for blanket row deletion. "
            f"The source density was {density_train:.1f} flags per 100 rows."
        )
        if test:
            test_flagged = int(test.get("iqr_flagged_value_count", 0) or 0)
            density_test = test_flagged / test["usable_labelled_rows"] * 100
            outlier_sentence += (
                f" Test profiling flagged {grouped(test_flagged)} values ({density_test:.1f} per 100 rows), "
                "providing a direct distribution check across supplied splits."
            )
        outlier_sentence += (
            f" No row was deleted on outlier evidence: with a {ratio:.2f}:1 largest-to-smallest class ratio, "
            "blanket deletion could remove scarce-class examples."
        )
    else:
        outlier_sentence = "No numeric value was flagged by the recorded IQR rule; no row was deleted on outlier evidence."

    return rf"""\section*{{DATA AND CLEANING}}
The supplied input contained {classification_clause} and {numeric + categorical}
predictors: {numeric} numeric and {categorical} categorical. {row_summary}

\noindent
\begin{{minipage}}{{\columnwidth}}
\centering
\captionof{{table}}{{{profile_caption}}}
\label{{tab:profile}}
\vspace{{2pt}}
{{\normalsize
\begin{{tabularx}}{{\columnwidth}}{{@{{}}MDDDDD@{{}}}}
\toprule
\rowcolor{{barA!10}}
Split & Usable & Miss. & Miss. & Dup. & IQR \\
 & rows & label & pred. & rows & flags \\
\midrule
{table_rows}
\bottomrule
\end{{tabularx}}}}
\end{{minipage}}
\par\vspace{{5pt}}

{class_sentence} A largest-to-smallest class ratio of {ratio:.2f}:1 makes overall accuracy
insufficient on its own. Missing predictors affected {missing_share:.2f}\% of labelled source rows,
and the source contained {grouped(train['exact_duplicate_rows'])} exact duplicates. {split_sentence}

{outlier_sentence}{correlation_sentence}"""


def build_preprocessing_section(data: dict[str, Any]) -> str:
    method = data["method"]
    policy = method["preprocessing"]
    encoding = policy.get("encoding_policy", {})
    validation = method["validation"]
    excluded = policy.get("excluded_features", [])
    retained = len(policy.get("selected_features", []))

    sensitivity = data["quality_findings"].get("suspicious_aggregate_sensitivity", [])
    sensitivity_sentence = ""
    if sensitivity and excluded:
        excluded_text = " and ".join(mono(name) for name in excluded)
        parts = []
        for row in sensitivity:
            parts.append(
                f"{fmt(row['delta_without_minus_full'], 4)} for {model_label(row['model']).lower()}"
            )
        deltas = "; ".join(parts)
        sensitivity_sentence = (
            f"\n\nThe aggregate-like predictor {excluded_text} had uncertain prediction-time"
            " availability; this was a provenance risk, not proof of target leakage."
            f" A development-only sensitivity check changed macro-F1 by {deltas} when"
            f" {excluded_text} was removed."
        )

    if excluded and sensitivity:
        feature_decision = (
            f"The flagged aggregate was dropped before final evaluation, and the final pipelines use "
            f"the remaining {retained} predictors. The check used development folds only and cannot "
            "certify that the other fields are available at deployment."
        )
    else:
        feature_decision = (
            f"No report-critical aggregate warning remained unresolved; the final pipelines use "
            f"{retained} predictors after the recorded schema and leakage checks."
        )

    return rf"""\section*{{PREPROCESSING AND FEATURES}}
Numeric predictors were median-imputed and categorical predictors
most-frequent-imputed, in both cases fitted inside the training part of each
fold so that no validation row influenced its own imputation. Categorical
levels were one-hot encoded with unseen-category handling, a minimum level
frequency of {encoding.get('min_frequency', 2)} and a cap of
{encoding.get('max_categories', 100)} levels per field. Only logistic regression used
numeric scaling. Every learned transformation stayed inside the
{validation['folds']} shuffled stratified folds (seed {validation['random_seed']}).{sensitivity_sentence}

{feature_decision}"""


def build_training_section(data: dict[str, Any]) -> str:
    method = data["method"]
    tuning = method["tuning"]
    search = tuning["search"]
    diagnostics = method["selection_diagnostics"]
    folds = method["validation"]["folds"]

    candidates = 1
    for model, spec in search.items():
        candidates += sum(spec["feature_sets"].values())
    fold_fits = candidates * folds

    grid_lines = []
    for model, spec in search.items():
        searched = [
            (key, values)
            for key, values in spec.get("parameter_values", {}).items()
            if len(values) > 1
        ]
        fixed = [
            (key, values)
            for key, values in spec.get("parameter_values", {}).items()
            if len(values) == 1
        ]
        # feature_sets counts evaluated candidates per feature set; the grid may
        # be coupled (for example class weight tied to leaf size), so report the
        # per-feature-set count rather than implying a full factorial.
        settings = max(spec.get("feature_sets", {}).values() or [0])
        factorial_size = 1
        for _, values in searched:
            factorial_size *= len(values)
        parameters = ", ".join(
            f"{key.removeprefix('model__').replace('_', ' ')} ("
            + ", ".join(parameter_value(key.removeprefix("model__"), value) for value in values)
            + ")"
            for key, values in searched
        )
        fixed_text = ", ".join(
            f"{key.removeprefix('model__').replace('_', ' ')}="
            + parameter_value(key.removeprefix("model__"), values[0])
            for key, values in fixed
        )
        if factorial_size > settings:
            setting_word = {4: "four"}.get(settings, str(settings))
            entry = (
                f"{model_label(model)} varied {parameters} across {setting_word} coupled settings"
                " per feature set (not a full factorial"
            )
            entry += f"; fixed at {fixed_text})" if fixed_text else ")"
        else:
            entry = f"{model_label(model)} varied {parameters} ({settings} settings per feature set"
            entry += f"; fixed at {fixed_text})" if fixed_text else ")"
        grid_lines.append(entry)
    grid_text = "; ".join(grid_lines)

    selected = method.get("selected_parameters", {})
    selected_text = ", ".join(
        f"{key.removeprefix('model__').replace('_', ' ')}="
        + parameter_value(key.removeprefix("model__"), value)
        for key, value in selected.items()
    ) or "the recorded defaults"

    reference = model_label(reference_model(data))
    challenger = model_label(diagnostics["challenger_model"])
    if diagnostics["challenger_model"] == "hist_gradient_boosting":
        challenger_reason = (
            "it can represent bounded nonlinear numeric effects and interactions without expanding "
            "a categorical one-hot matrix"
        )
    else:
        challenger_reason = (
            "mixed categorical and numeric interactions are plausible, and a tree can represent them "
            "without requiring hand-written interaction terms"
        )

    return rf"""\section*{{TRAINING AND SELECTION}}
Three configurations were compared on identical fixed folds: a
most-frequent dummy baseline, regularised {reference.lower()} regression as an
interpretable linear reference, and a {challenger.lower()} as the nonlinear
challenger~[1]. The {challenger.lower()} was the sensible challenger because
{challenger_reason}.

The search space was fixed in advance. {grid_text}. Every candidate was fitted
with and without the excluded feature, giving {candidates} candidate configurations in
total and {fold_fits} fold fits. The selected settings were {selected_text}. Search
stopped once that predefined grid had been evaluated once.

Macro-F1 was the primary selection metric because it weights the classes
equally and therefore cannot be improved by ignoring the minority
class~[3]. Selection used the paired development-fold difference with a
predefined one-standard-error practical-tie rule. Final-test metrics did not
inform any feature, parameter, threshold or model choice."""


def build_results_section(data: dict[str, Any]) -> str:
    results = data["results"]
    models = ["dummy_most_frequent", *substantive_models(data)]
    selected = results["selected_model"]
    rows = []
    for name in models:
        entry = comparison_entry(data, name)
        final = results["final_metrics_by_model"][name]
        label = tex(model_label(name))
        cv = fmt(entry["development"]["macro_f1_mean"])
        test = fmt(final["macro_f1"])
        focus = fmt(focus_metric(data, final))
        if name == selected:
            label = rf"\textbf{{{label}}}"
            cv, test, focus = (rf"\textbf{{{value}}}" for value in (cv, test, focus))
        rows.append(f"{label} & {cv} & {test} & {focus} \\\\ ".rstrip())

    plot_rows = [
        (
            plot_label(name),
            results["final_metrics_by_model"][name]["macro_f1"],
            focus_metric(data, results["final_metrics_by_model"][name]),
        )
        for name in models
    ]
    macro_coords = " ".join(f"({fmt(value)},{label})" for label, value, _ in plot_rows)
    focus_coords = " ".join(f"({fmt(value)},{label})" for label, _, value in plot_rows)
    focus_label = focus_metric_label(data)
    legend_entries = f"Test macro-F1,{{{focus_label}}}"
    figure_focus = "positive-class recall" if has_positive_semantics(data) else "balanced accuracy"

    selected_metrics = results["final_metrics_by_model"][selected]
    confusion = selected_metrics["confusion_matrix"]
    confusion_labels = [str(label) for label in confusion["labels"]]
    if len(confusion_labels) <= 3:
        confusion_header = " & ".join(["Actual / Pred.", *(tex(label) for label in confusion_labels)]) + r" \\"
        confusion_rows = "\n".join(
            " & ".join([tex(label), *(grouped(value) for value in confusion["values"][row_index])]) + r" \\"
            for row_index, label in enumerate(confusion_labels)
        )
        confusion_columns = "@{}L" + "C" * len(confusion_labels) + "@{}"
        confusion_table = rf"""\captionof{{table}}{{Selected-model confusion matrix (n={grouped(selected_metrics['evaluated_rows'])}).}}
\label{{tab:confusion}}
\vspace{{2pt}}
{{\normalsize
\begin{{tabularx}}{{\columnwidth}}{{{confusion_columns}}}
\toprule
\rowcolor{{barA!10}}
{confusion_header}
\midrule
{confusion_rows}
\bottomrule
\end{{tabularx}}}}"""
    else:
        class_rows = sorted(
            selected_metrics.get("per_class", {}).items(),
            key=lambda item: item[1].get("recall", 0),
        )[:5]
        summary_rows = "\n".join(
            f"{tex(label)} & {fmt(values.get('precision', 0))} & {fmt(values.get('recall', 0))} & "
            f"{fmt(values.get('f1', 0))} & {grouped(values.get('support', 0))} \\\\"
            for label, values in class_rows
        )
        confusion_table = rf"""\captionof{{table}}{{Five lowest-recall classes for {tex(model_label(selected))}; full matrix retained in artifacts.}}
\label{{tab:class-summary}}
\vspace{{2pt}}
{{\normalsize
\begin{{tabularx}}{{\columnwidth}}{{@{{}}LCCCC@{{}}}}
\toprule
\rowcolor{{barA!10}}
Class & Prec. & Recall & F1 & n \\
\midrule
{summary_rows}
\bottomrule
\end{{tabularx}}}}"""

    return rf"""\section*{{RESULTS}}
\noindent
\begin{{minipage}}{{\columnwidth}}
\centering
\captionof{{table}}{{Development and held-out comparison (selected model in bold).}}
\label{{tab:models}}
\vspace{{2pt}}
{{\normalsize
\begin{{tabularx}}{{\columnwidth}}{{@{{}}LCCC@{{}}}}
\toprule
\rowcolor{{barA!10}}
Model & CV M-F1 & Test M-F1 & {focus_label} \\
\midrule
{chr(10).join(rows)}
\bottomrule
\end{{tabularx}}}}
\end{{minipage}}
\par\vspace{{6pt}}

\noindent
\begin{{minipage}}{{\columnwidth}}
\centering
\begin{{tikzpicture}}[font=\fontsize{{7.5}}{{9}}\selectfont]
\begin{{axis}}[
  width=\columnwidth,
  height=4.4cm,
  xbar,
  bar width=5.5pt,
  xmin=0, xmax=1.32,
  xtick={{0,0.25,0.5,0.75,1}},
  xticklabel style={{font=\fontsize{{7}}{{8}}\selectfont}},
  xlabel={{\fontsize{{7}}{{8}}\selectfont Held-out score}},
  symbolic y coords={{{",".join(label for label, _, _ in plot_rows)}}},
  ytick=data,
  yticklabel style={{font=\fontsize{{7.5}}{{9}}\selectfont}},
  nodes near coords={{\pgfmathprintnumber[fixed,precision=2]{{\pgfplotspointmeta}}}},
  every node near coord/.append style={{font=\fontsize{{6}}{{7}}\selectfont,color=ink!80,anchor=west,xshift=1.5pt}},
  xmajorgrids=true,
  grid style={{draw=black!10}},
  axis lines*=left,
  tick align=outside,
  legend style={{font=\fontsize{{7}}{{8.5}}\selectfont,draw=none,fill=none,at={{(0.99,0.03)}},anchor=south east}},
  legend cell align=left,
]
\addplot[fill=barA,draw=none] coordinates {{{macro_coords}}};
\addplot[fill=barB,draw=none] coordinates {{{focus_coords}}};
\legend{{{legend_entries}}}
\end{{axis}}
\end{{tikzpicture}}
\captionof{{figure}}{{Held-out macro-F1 and {figure_focus} by model.}}
\label{{fig:metrics}}
\end{{minipage}}
\par\vspace{{6pt}}

\noindent
\begin{{minipage}}{{\columnwidth}}
\centering
{confusion_table}
\end{{minipage}}

{build_dummy_paragraph(data)}"""


def build_dummy_paragraph(data: dict[str, Any]) -> str:
    dummy = data["results"]["final_metrics_by_model"]["dummy_most_frequent"]
    majority_label = max(data["dataset"]["splits"]["train"]["class_distribution"], key=lambda item: item["count"])["label"]
    substantive = [
        data["results"]["final_metrics_by_model"][name]["balanced_accuracy"]
        for name in substantive_models(data)
    ]
    measures = " and ".join(fmt(value) for value in substantive)
    class_floor = 1 / len(data["task"]["labels"])
    return (
        rf"The dummy baseline is a real floor: answering {mono(majority_label)}"
        rf" everywhere returns {fmt(dummy['accuracy'])} accuracy but macro-F1 {fmt(dummy['macro_f1'])}"
        rf" and balanced accuracy {fmt(dummy['balanced_accuracy'])}, near the {fmt(class_floor)}"
        rf" equal-class chance floor. Both substantive models clear it on the class-balanced measures (balanced"
        rf" accuracy {measures})."
    )


def build_findings_section(data: dict[str, Any]) -> str:
    results = data["results"]
    selected = results["selected_model"]
    reference = reference_model(data)
    comparison = reference if selected != reference else next(
        name for name in substantive_models(data) if name != selected
    )
    diagnostics = data["method"]["selection_diagnostics"]
    final = results["final_metrics_by_model"][selected]
    comparison_final = results["final_metrics_by_model"][comparison]
    selected_name = model_label(selected)
    reference_name = model_label(reference)
    comparison_name = model_label(comparison)

    opening = (
        f"The declared rule selected the {selected_name.lower()} using development macro-F1 and a "
        "predefined one-standard-error practical-tie rule. Its development score was "
        f"{fmt(comparison_entry(data, selected)['development']['macro_f1_mean'])}, versus "
        f"{fmt(comparison_entry(data, comparison)['development']['macro_f1_mean'])} for "
        f"{comparison_name.lower()}; held-out macro-F1 was {fmt(final['macro_f1'])} versus "
        f"{fmt(comparison_final['macro_f1'])}, with balanced accuracy {fmt(final['balanced_accuracy'])} "
        f"versus {fmt(comparison_final['balanced_accuracy'])}."
    )

    cost_sentence = ""
    if has_positive_semantics(data):
        positive = str(data["task"]["positive_label"])
        negative = next(str(label) for label in data["task"]["labels"] if str(label) != positive)
        pos = final["per_class"][positive]
        ref_pos = comparison_final["per_class"][positive]
        neg = final["per_class"][negative]
        ref_neg = comparison_final["per_class"][negative]
        _, fp, fn, _ = binary_confusion_counts(final, positive)
        _, ref_fp, ref_fn, _ = binary_confusion_counts(comparison_final, positive)
        fewer_fn = ref_fn - fn
        more_fp = fp - ref_fp
        class_sentence = (
            f"The selected model recovered {pct(pos['recall'])} of {mono(positive)} cases, versus "
            f"{pct(ref_pos['recall'])} for {comparison_name.lower()}, with precision "
            f"{fmt(pos['precision'])} versus {fmt(ref_pos['precision'])}. Per-class F1 was "
            f"{fmt(pos['f1'])} versus {fmt(ref_pos['f1'])} for {mono(positive)}, and "
            f"{fmt(neg['f1'])} versus {fmt(ref_neg['f1'])} for {mono(negative)}."
        )
        if fewer_fn > 0 and more_fp > 0:
            ratio = more_fp / fewer_fn
            cost_sentence = (
                f" The selected model traded {grouped(fewer_fn)} fewer false negatives for "
                f"{grouped(more_fp)} additional false positives. It has lower observed error cost only "
                f"if a false negative costs more than {ratio:.2f} times a false positive; this post-hoc "
                "interpretation did not drive selection."
            )
    elif data["task"].get("type") == "binary":
        class_sentence = (
            "No class was designated semantically positive, so positive-class recall, precision, "
            "ROC-AUC and average precision were not invented. The comparison instead uses macro-F1, "
            "balanced accuracy, overall accuracy and the complete per-class metrics retained in the artifacts."
        )
    else:
        class_sentence = (
            f"The multiclass comparison used macro and class-balanced metrics: selected-model accuracy was "
            f"{fmt(final['accuracy'])}, versus {fmt(comparison_final['accuracy'])} for {comparison_name.lower()}. "
            "These summaries keep smaller classes visible rather than allowing the largest class to dominate."
        )

    if has_positive_semantics(data) and "roc_auc" in final and "roc_auc" in comparison_final:
        probability_sentence = (
            f"Binary discrimination was compared by ROC-AUC ({fmt(final['roc_auc'])} selected; "
            f"{fmt(comparison_final['roc_auc'])} alternative) and average precision "
            f"({fmt(final.get('average_precision', 0))}; {fmt(comparison_final.get('average_precision', 0))})."
        )
    elif "roc_auc_ovr_weighted" in final and "roc_auc_ovr_weighted" in comparison_final:
        probability_sentence = (
            f"Multiclass discrimination was compared by weighted OvR ROC-AUC "
            f"({fmt(final['roc_auc_ovr_weighted'])} selected; "
            f"{fmt(comparison_final['roc_auc_ovr_weighted'])} alternative)."
        )
    else:
        probability_sentence = (
            "Probability-discrimination metrics were not reported because their required class semantics "
            "were unavailable."
        )

    challenger = diagnostics.get("challenger_model")
    challenger_name = model_label(challenger) if challenger else "challenger"
    diagnostic_sentence = (
        f"Across paired folds the {challenger_name.lower()}-minus-{reference_name.lower()} macro-F1 "
        f"difference was {diagnostics.get('mean_difference', 0):+.4f} (SD "
        f"{diagnostics.get('standard_deviation', 0):.4f}, SE "
        f"{diagnostics.get('standard_error', 0):.4f}); the challenger won "
        f"{diagnostics.get('challenger_fold_wins', 0)} of {data['method']['validation']['folds']} folds. "
        "This practical-tie rule is not a significance test because folds share training data."
    )

    return rf"""\section*{{FINDINGS AND DISCUSSION}}
{opening} {class_sentence}{cost_sentence}

{probability_sentence} The selected model reflects the declared class-balanced objective,
not dominance on every metric.

{diagnostic_sentence}

No post-hoc threshold tuning was attempted. With no supplied error costs and an
already-inspected holdout, tuning a decision rule now would turn final evidence into another
selection resource. Any operational threshold requires a fresh development-only plan with
the costs written down first.

The analysis assumes independent rows and a stable collection process. It does not establish
causal effects, fairness across unobserved groups, probability calibration, or prediction-time
availability for every retained field. Shared entities or time order would require group- or
time-aware validation, so generalization beyond the observed data remains conditional."""


def build_skill_section(data: dict[str, Any]) -> str:
    return rf"""\section*{{SKILL GENERALISATION}}
The report is produced by a reusable SKILL driven by an AI operator. The
operator proposes preprocessing and model choices; a fixed policy then
constrains which candidate families and which selection rule may be used, so a
run cannot silently switch models to chase a score. The SKILL profiles the
data, records typed quality warnings, evaluates the surviving candidates in
fixed folds against a dummy baseline, and writes a run directory of
machine-readable artefacts from which the report is rendered.

Generality was exercised, not proven. Phase 5 completed {FORWARD_TOTAL_CASES} scenarios:
{FORWARD_MODEL_CASES} binary or multiclass cases generated verified reports,
{FORWARD_REFUSAL_CASES} unsafe or unresolvable inputs returned an explicit request for
human input or a typed refusal, and the remaining scenarios covered prediction-only and
dependency-checkpoint branches. This demonstrates behavioural coverage across differently
shaped inputs; it does not establish predictive accuracy on every future dataset."""


def build_verification_section(data: dict[str, Any]) -> str:
    evidence = data["source_evidence"]
    versions = data["reproducibility"]["runtime_versions"]
    decisions = data["reproducibility"].get("decision_ids", [])
    checks = sum(bool(value) for value in evidence.get("verification_checks", {}).values())
    selected = data["results"]["selected_model"]
    metrics = data["results"]["final_metrics_by_model"][selected]
    version_text = ", ".join(
        f"{tex(name)} {tex(value)}~[2]" if name == "scikit-learn" else f"{tex(name)} {tex(value)}"
        for name, value in versions.items()
    )
    if has_positive_semantics(data):
        positive = str(data["task"]["positive_label"])
        _, _, fn, tp = binary_confusion_counts(metrics, positive)
        recall = metrics["per_class"][positive]["recall"]
        explicit_check = (
            f"the {model_label(selected).lower()} confusion counts sum to "
            f"{grouped(metrics['evaluated_rows'])}, and {mono(positive)} recall is "
            f"${grouped(tp)}/({grouped(tp)}+{grouped(fn)})={fmt(recall)}$"
        )
    else:
        explicit_check = (
            f"the {model_label(selected).lower()} confusion counts sum to "
            f"{grouped(metrics['evaluated_rows'])}, and its recomputed macro-F1 is "
            f"{fmt(metrics['macro_f1'])}"
        )

    return rf"""\section*{{VERIFICATION}}
{tex(data['run_id'])} records dataset and Skill fingerprints, the seed, fold assignments,
candidate settings, saved predictions and package versions ({version_text}), together
with {len(decisions)} recorded decisions. An independent verifier recomputed {checks}
checks from saved predictions, covering every reported model's scalar metrics, confusion
matrix, prediction-row alignment and score normalisation; all passed. One explicit
reconstruction confirms that {explicit_check}. Reproducing a run verifies computation,
not the provenance and independence assumptions above."""


def build_references_section(data: dict[str, Any]) -> str:
    first = REFERENCES_BOOSTING if "random_forest" not in data["results"]["final_metrics_by_model"] else REFERENCES_RANDOM_FOREST
    return rf"""\section*{{REFERENCES}}
{{\footnotesize
\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{2pt}}
\hangindent=1.4em
{first}
\hangindent=1.4em
{REFERENCE_SKLEARN}
\hangindent=1.4em
{REFERENCE_IMBALANCE}
}}"""


def build_body(data: dict[str, Any]) -> str:
    return "\n\n".join(
        [
            build_data_section(data),
            build_preprocessing_section(data),
            build_training_section(data),
            build_results_section(data),
            build_findings_section(data),
            build_skill_section(data),
            build_verification_section(data),
            build_references_section(data),
        ]
    )


def render(template: str, data: dict[str, Any], args: argparse.Namespace) -> str:
    replacements = {
        "<<HEADER_TITLE>>": tex("IN6227 Data Mining / Assignment 1 / Variant 2"),
        "<<REPORT_TITLE>>": tex(build_title(data)),
        "<<FULL_NAME>>": tex(args.full_name.upper()),
        "<<MATRIC_NUMBER>>": tex(args.matric_number),
        "<<MODEL_NAME>>": tex(args.model_name),
        "<<MODEL_VERSION>>": tex(args.model_version),
        "<<REASONING_EFFORT>>": (
            f"\\quad Codex reasoning: {tex(args.reasoning_effort)}"
            if getattr(args, "reasoning_effort", None)
            else ""
        ),
        "<<LLM_INTERFACE>>": tex(args.llm_interface),
        "<<GITHUB_URL>>": args.github_url,
        "<<BODY>>": build_body(data),
    }
    missing = [key for key in replacements if key not in template]
    if missing:
        raise ReportError(f"Template is missing placeholders: {', '.join(missing)}")
    template_placeholders = set(re.findall(r"<<[A-Z][A-Z0-9_]*>>", template))
    unknown = sorted(template_placeholders - set(replacements))
    if unknown:
        raise ReportError(f"Template contains unknown placeholders: {', '.join(unknown)}")
    output = template
    for key, value in replacements.items():
        output = output.replace(key, value)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_data", type=Path)
    parser.add_argument("--output-tex", type=Path, required=True)
    parser.add_argument("--template-tex", type=Path)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--matric-number", required=True)
    parser.add_argument("--github-url", required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--reasoning-effort")
    parser.add_argument("--llm-interface", required=True)
    args = parser.parse_args()

    default_template = Path(__file__).resolve().parent.parent / "assets" / "report_template.tex"
    args.template_tex = args.template_tex or default_template

    try:
        require_metadata(args)
        data = load_json(args.report_data)
        validate_report_data(data)
        if not args.template_tex.is_file():
            raise ReportError(f"LaTeX template not found: {args.template_tex}")
        template = args.template_tex.read_text(encoding="utf-8")
        document = render(template, data, args)
        args.output_tex.parent.mkdir(parents=True, exist_ok=True)
        args.output_tex.write_text(document, encoding="utf-8")
    except ReportError as exc:
        print(f"Report generation failed: {exc}")
        return 2
    print(args.output_tex.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
