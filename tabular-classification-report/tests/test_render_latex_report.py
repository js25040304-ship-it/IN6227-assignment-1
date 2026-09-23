#!/usr/bin/env python3

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "render_latex_report.py"
TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "report_template.tex"
sys.path.insert(0, str(SCRIPT.parent))

from render_latex_report import tex


def metrics(
    macro_f1: float,
    balanced: float,
    accuracy: float,
    recall: float,
    precision: float,
    matrix,
) -> dict:
    return {
        "evaluated_rows": sum(sum(row) for row in matrix),
        "accuracy": accuracy,
        "balanced_accuracy": balanced,
        "macro_f1": macro_f1,
        "roc_auc": 0.8,
        "average_precision": 0.7,
        "per_class": {
            "no": {"recall": 0.9, "precision": 0.8, "f1": 0.85},
            "yes": {"recall": recall, "precision": precision, "f1": 0.6},
        },
        "confusion_matrix": {"labels": ["no", "yes"], "values": matrix},
    }


def report_data() -> dict:
    dummy = metrics(0.33, 0.5, 0.5, 0.0, 0.0, [[3, 0], [2, 0]])
    logistic = metrics(0.70, 0.70, 0.75, 0.5, 1.0, [[2, 1], [1, 1]])
    forest = metrics(0.73, 0.75, 0.75, 0.5, 1.0, [[3, 0], [1, 1]])
    return {
        "run_id": "RUN-T01",
        "source_evidence": {
            "automatic_verification_passed": True,
            "verification_checks": {"accuracy": True, "confusion_matrix": True},
        },
        "task": {
            "target": "label",
            "type": "binary",
            "labels": ["no", "yes"],
            "positive_label": "yes",
        },
        "dataset": {
            "splits": {
                "train": {
                    "usable_labelled_rows": 12,
                    "missing_target_rows": 2,
                    "rows_with_any_missing": 1,
                    "exact_duplicate_rows": 0,
                    "predictor_type_counts": {"numeric": 2, "categorical": 1},
                    "class_distribution": [
                        {"label": "no", "count": 9, "ratio": 0.75},
                        {"label": "yes", "count": 3, "ratio": 0.25},
                    ],
                    "iqr_outlier_counts": {"a": 6, "b": 2},
                    "iqr_flagged_value_count": 8,
                },
                "test": {
                    "usable_labelled_rows": 5,
                    "missing_target_rows": 0,
                    "rows_with_any_missing": 0,
                    "exact_duplicate_rows": 0,
                    "predictor_type_counts": {"numeric": 2, "categorical": 1},
                    "class_distribution": [
                        {"label": "no", "count": 4, "ratio": 0.8},
                        {"label": "yes", "count": 1, "ratio": 0.2},
                    ],
                    "iqr_outlier_counts": {"a": 2, "b": 1},
                    "iqr_flagged_value_count": 3,
                },
            },
            "cross_split_checks": {
                "unseen_test_categories": [],
                "predictor_overlap": {"test_rows_matching_train_predictors": 0},
            },
        },
        "quality_findings": {
            "warnings": [
                {
                    "code": "HIGH_NUMERIC_CORRELATION",
                    "pairs": [{"left": "a", "right": "b", "correlation": 0.91}],
                }
            ],
            "suspicious_aggregate_sensitivity": [
                {"model": "logistic_regression", "delta_without_minus_full": 0.0002},
                {"model": "random_forest", "delta_without_minus_full": -0.0011},
            ],
        },
        "method": {
            "preprocessing": {
                "encoding_policy": {"min_frequency": 2, "max_categories": 100},
                "selected_features": ["a", "b", "c"],
                "excluded_features": ["rank"],
                "selected_feature_set": "without_suspicious_aggregates",
            },
            "validation": {"folds": 5, "random_seed": 42},
            "tuning": {
                "search": {
                    "logistic_regression": {
                        "feature_sets": {"full": 2, "without_suspicious_aggregates": 2},
                        "parameter_values": {"model__C": [0.1, 1.0]},
                    },
                    "random_forest": {
                        "feature_sets": {"full": 4, "without_suspicious_aggregates": 4},
                        "parameter_values": {
                            "model__class_weight": ["balanced_subsample", None],
                            "model__max_depth": [18, None],
                            "model__max_features": ["sqrt"],
                            "model__min_samples_leaf": [1, 3],
                            "model__n_estimators": [160],
                        },
                    },
                }
            },
            "selected_parameters": {"model__max_depth": None},
            "selection_diagnostics": {
                "reference_model": "logistic_regression",
                "challenger_model": "random_forest",
                "mean_difference": 0.0093,
                "standard_deviation": 0.0111,
                "standard_error": 0.0050,
                "challenger_fold_wins": 4,
            },
        },
        "results": {
            "development_comparison": [
                {
                    "model": "logistic_regression",
                    "feature_set": "full",
                    "development": {"macro_f1_mean": 0.700},
                },
                {
                    "model": "logistic_regression",
                    "feature_set": "without_suspicious_aggregates",
                    "development": {"macro_f1_mean": 0.705},
                },
                {
                    "model": "random_forest",
                    "feature_set": "full",
                    "development": {"macro_f1_mean": 0.720},
                },
                {
                    "model": "random_forest",
                    "feature_set": "without_suspicious_aggregates",
                    "development": {"macro_f1_mean": 0.731},
                },
                {
                    "model": "dummy_most_frequent",
                    "feature_set": "not-applicable",
                    "development": {"macro_f1_mean": 0.330},
                },
            ],
            "final_metrics_by_model": {
                "dummy_most_frequent": dummy,
                "logistic_regression": logistic,
                "random_forest": forest,
            },
            "selected_model": "random_forest",
            "selected_final_metrics": forest,
        },
        "reproducibility": {
            "runtime_versions": {"python": "3.13.4", "scikit-learn": "1.9.1"},
            "decision_ids": ["DPROF-001", "DMOD-001"],
        },
    }


def rename_positive_label(data: dict, new_label: str) -> None:
    old_label = data["task"]["positive_label"]
    data["task"]["positive_label"] = new_label
    data["task"]["labels"] = [
        new_label if label == old_label else label for label in data["task"]["labels"]
    ]
    for split in data["dataset"]["splits"].values():
        for row in split["class_distribution"]:
            if row["label"] == old_label:
                row["label"] = new_label
    for metric in data["results"]["final_metrics_by_model"].values():
        metric["per_class"][new_label] = metric["per_class"].pop(old_label)
        metric["confusion_matrix"]["labels"] = [
            new_label if label == old_label else label
            for label in metric["confusion_matrix"]["labels"]
        ]


def multiclass_metrics(macro_f1: float, accuracy: float, matrix: list[list[int]]) -> dict:
    labels = ["blue", "gold", "red"]
    return {
        "evaluated_rows": sum(sum(row) for row in matrix),
        "accuracy": accuracy,
        "balanced_accuracy": macro_f1,
        "macro_f1": macro_f1,
        "roc_auc_ovr_weighted": min(0.99, macro_f1 + 0.08),
        "per_class": {
            label: {
                "recall": macro_f1 - index * 0.02,
                "precision": macro_f1 - index * 0.01,
                "f1": macro_f1 - index * 0.015,
                "support": sum(matrix[index]),
            }
            for index, label in enumerate(labels)
        },
        "confusion_matrix": {"labels": labels, "values": matrix},
    }


def multiclass_report_data() -> dict:
    data = report_data()
    data["task"] = {
        "target": "label",
        "type": "multiclass",
        "labels": ["blue", "gold", "red"],
        "positive_label": None,
    }
    for split in data["dataset"]["splits"].values():
        split["class_distribution"] = [
            {"label": "blue", "count": 5, "ratio": 5 / 12},
            {"label": "gold", "count": 4, "ratio": 4 / 12},
            {"label": "red", "count": 3, "ratio": 3 / 12},
        ]
    dummy = multiclass_metrics(0.20, 0.42, [[5, 0, 0], [4, 0, 0], [3, 0, 0]])
    logistic = multiclass_metrics(0.70, 0.75, [[4, 1, 0], [1, 3, 0], [0, 1, 2]])
    forest = multiclass_metrics(0.73, 0.75, [[4, 1, 0], [0, 3, 1], [0, 1, 2]])
    data["results"]["final_metrics_by_model"] = {
        "dummy_most_frequent": dummy,
        "logistic_regression": logistic,
        "random_forest": forest,
    }
    data["results"]["selected_model"] = "random_forest"
    data["results"]["selected_final_metrics"] = forest
    return data


def boosting_report_data() -> dict:
    data = report_data()
    results = data["results"]
    results["final_metrics_by_model"]["hist_gradient_boosting"] = (
        results["final_metrics_by_model"].pop("random_forest")
    )
    results["selected_model"] = "hist_gradient_boosting"
    results["selected_final_metrics"] = results["final_metrics_by_model"]["hist_gradient_boosting"]
    for row in results["development_comparison"]:
        if row["model"] == "random_forest":
            row["model"] = "hist_gradient_boosting"
    search = data["method"]["tuning"]["search"]
    search["hist_gradient_boosting"] = search.pop("random_forest")
    data["method"]["selection_diagnostics"]["challenger_model"] = "hist_gradient_boosting"
    for row in data["quality_findings"]["suspicious_aggregate_sensitivity"]:
        if row["model"] == "random_forest":
            row["model"] = "hist_gradient_boosting"
    return data


def render(data: dict, output: Path) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        payload = Path(tmp) / "report_data.json"
        payload.write_text(json.dumps(data), encoding="utf-8")
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(payload),
                "--output-tex",
                str(output),
                "--template-tex",
                str(TEMPLATE),
                "--full-name",
                "Ada Lovelace",
                "--matric-number",
                "G1234567X",
                "--github-url",
                "https://github.com/example/skill",
                "--model-name",
                "gpt-5.6-sol",
                "--model-version",
                "GPT-5.6 Sol",
                "--llm-interface",
                "Codex Desktop 1.2.3",
            ],
            capture_output=True,
            text=True,
        )


class RenderLatexReportTests(unittest.TestCase):
    def test_template_keeps_natural_left_then_right_column_flow(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("a4paper,twocolumn", template)
        self.assertNotIn(r"\usepackage{balance}", template)
        self.assertNotRegex(template, r"(?m)^\\balance\s*$")

    def test_tex_escapes_each_metacharacter_once(self):
        self.assertEqual(
            tex(r"\&%$#_{}~^"),
            r"\textbackslash{}\&\%\$\#\_\{\}\textasciitilde{}\textasciicircum{}",
        )

    def test_renders_verified_report_without_placeholders(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "main.tex"
            result = render(report_data(), output)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            document = output.read_text(encoding="utf-8")

        for section in (
            "DATA AND CLEANING",
            "PREPROCESSING AND FEATURES",
            "TRAINING AND SELECTION",
            "RESULTS",
            "FINDINGS AND DISCUSSION",
            "SKILL GENERALISATION",
            "VERIFICATION",
            "REFERENCES",
        ):
            self.assertIn(section, document)
        self.assertNotIn("<<", document)

    def test_uses_selected_feature_set_scores_and_artifact_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "main.tex"
            render(report_data(), output)
            document = output.read_text(encoding="utf-8")

        # The retained feature set scores, not the discarded full-feature-set scores.
        self.assertIn(r"\textbf{0.731}", document)
        self.assertNotIn("0.720", document)
        # Confusion total must come from the artifact, not from the prose.
        collapsed = " ".join(document.split())
        self.assertIn("confusion counts sum to 5", collapsed)
        # Feature provenance and coupled search structure must remain explicit.
        self.assertIn(r"\texttt{rank}", document)
        self.assertIn("prediction-time availability", document)
        self.assertIn("four coupled settings", document)
        self.assertIn("not a full factorial", document.lower())
        # Every reference in the fixed list must have an in-text citation.
        for citation in ("~[1]", "~[2]", "~[3]"):
            self.assertIn(citation, document)

    def test_figure_axis_uses_single_token_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "main.tex"
            render(report_data(), output)
            document = output.read_text(encoding="utf-8")

        for line in document.splitlines():
            if "symbolic y coords" in line or "coordinates {(" in line:
                labels = line.split("{")[-1].rstrip("},")
                for label in labels.replace(")", "").split("(")[-1].split(","):
                    self.assertNotIn(" ", label.strip())

    def test_no_unescaped_percent_signs(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "main.tex"
            render(report_data(), output)
            document = output.read_text(encoding="utf-8")

        # A bare % starts a LaTeX comment, so a share such as 24.0% must be \%.
        # The template's own "{%%" newline-stripping idiom is allowed.
        for match in re.finditer("%", document):
            index = match.start()
            if index and document[index - 1] in "\\{":
                continue
            line_start = document.rfind("\n", 0, index) + 1
            self.assertEqual(
                document[line_start:index].strip(),
                "",
                f"unescaped percent sign: {document[line_start:index + 40]!r}",
            )

    def test_single_file_uses_internal_holdout_without_fabricating_test_profile(self):
        data = report_data()
        data["dataset"]["splits"].pop("test")
        data["dataset"]["cross_split_checks"] = None
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "main.tex"
            result = render(data, output)
            document = output.read_text(encoding="utf-8") if output.exists() else ""
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("stratified held-out partition", document)
        self.assertNotIn("two supplied splits", document)
        self.assertNotIn("test split contained", document)

    def test_unresolved_binary_positive_semantics_use_balanced_metrics(self):
        data = report_data()
        data["task"]["positive_label"] = None
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "main.tex"
            result = render(data, output)
            document = output.read_text(encoding="utf-8") if output.exists() else ""
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Bal. acc.", document)
        self.assertIn("No class was designated semantically positive", document)
        self.assertNotIn("positive-class recall by model", document)
        self.assertNotIn("Binary discrimination was compared by ROC-AUC", document)
        self.assertNotIn("Model & TN & FP & FN & TP", document)
        self.assertNotIn("None", document)

    def test_multiclass_report_uses_weighted_ovr_and_nonbinary_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "main.tex"
            result = render(multiclass_report_data(), output)
            document = output.read_text(encoding="utf-8") if output.exists() else ""
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("weighted OvR ROC-AUC", document)
        self.assertIn("Selected-model confusion matrix", document)
        self.assertNotIn("average precision", document)
        self.assertNotIn("Model & TN & FP & FN & TP", document)

    def test_boosting_route_uses_friedman_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "main.tex"
            result = render(boosting_report_data(), output)
            document = output.read_text(encoding="utf-8") if output.exists() else ""
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Friedman", document)
        self.assertNotIn("Breiman", document)
        self.assertIn("bounded nonlinear numeric effects", document)

    def test_no_aggregate_warning_does_not_claim_feature_was_dropped(self):
        data = report_data()
        data["quality_findings"]["suspicious_aggregate_sensitivity"] = []
        data["method"]["preprocessing"]["excluded_features"] = []
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "main.tex"
            result = render(data, output)
            document = output.read_text(encoding="utf-8") if output.exists() else ""
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("No report-critical aggregate warning remained unresolved", document)
        self.assertNotIn("The flagged aggregate was dropped", document)

    def test_selected_reference_model_is_compared_with_challenger(self):
        data = boosting_report_data()
        data["results"]["selected_model"] = "logistic_regression"
        data["results"]["selected_final_metrics"] = data["results"]["final_metrics_by_model"]["logistic_regression"]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "main.tex"
            result = render(data, output)
            document = output.read_text(encoding="utf-8") if output.exists() else ""
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("versus 0.731 for hist. gradient boosting", document)
        self.assertNotIn("versus 0.705 for logistic", document)

    def test_hostile_positive_label_is_escaped_in_every_text_sink(self):
        data = report_data()
        hostile = r"yes & \input{x}%_#{}~^$"
        rename_positive_label(data, hostile)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "main.tex"
            result = render(data, output)
            document = output.read_text(encoding="utf-8") if output.exists() else ""
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn(r"\input{x}", document)
        self.assertIn(r"\&", document)
        self.assertIn(r"\textbackslash{}input\{x\}", document)

    def test_label_with_comma_and_double_angle_text_preserves_two_plot_legend_entries(self):
        data = report_data()
        rename_positive_label(data, "yes, maybe<<later")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "main.tex"
            result = render(data, output)
            document = output.read_text(encoding="utf-8") if output.exists() else ""
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(r"\legend{Test macro-F1,{yes, maybe<<later recall}}", document)

    def test_positive_class_at_matrix_index_zero_uses_label_orientation(self):
        data = report_data()
        data["task"]["labels"] = ["yes", "no"]
        for split in data["dataset"]["splits"].values():
            split["class_distribution"].reverse()
        for name, metric in data["results"]["final_metrics_by_model"].items():
            metric["confusion_matrix"]["labels"] = ["yes", "no"]
            metric["confusion_matrix"]["values"] = (
                [[4, 1], [2, 3]] if name == "random_forest" else [[3, 2], [1, 4]]
            )
            metric["evaluated_rows"] = 10
            metric["per_class"]["yes"]["recall"] = 0.8 if name == "random_forest" else 0.6
        data["results"]["selected_final_metrics"] = data["results"]["final_metrics_by_model"]["random_forest"]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "main.tex"
            result = render(data, output)
            document = output.read_text(encoding="utf-8") if output.exists() else ""
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("$4/(4+1)=0.800$", document)

    def test_rejects_positive_label_inconsistent_with_task_and_metrics(self):
        data = report_data()
        data["task"]["positive_label"] = "missing"
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "main.tex"
            result = render(data, output)
        self.assertEqual(result.returncode, 2)
        self.assertIn("positive label", result.stdout.lower())

    def test_rejects_placeholder_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "main.tex"
            payload = Path(tmp) / "report_data.json"
            payload.write_text(json.dumps(report_data()), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(payload),
                    "--output-tex",
                    str(output),
                    "--full-name",
                    "TBD",
                    "--matric-number",
                    "G1234567X",
                    "--github-url",
                    "https://github.com/example/skill",
                    "--model-name",
                    "m",
                    "--model-version",
                    "v",
                    "--llm-interface",
                    "Codex",
                ],
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("placeholders are not allowed", result.stdout)
        self.assertFalse(output.exists())

    def test_rejects_latex_metacharacters_in_github_url_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "main.tex"
            payload = Path(tmp) / "report_data.json"
            payload.write_text(json.dumps(report_data()), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(payload),
                    "--output-tex",
                    str(output),
                    "--full-name",
                    "Ada Lovelace",
                    "--matric-number",
                    "G1234567X",
                    "--github-url",
                    r"https://github.com/example/skill}\input{x}",
                    "--model-name",
                    "m",
                    "--model-version",
                    "v",
                    "--llm-interface",
                    "Codex",
                ],
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("plain https://github.com/owner/repository", result.stdout)
        self.assertFalse(output.exists())

    def test_rejects_unverified_report_data(self):
        data = report_data()
        data["source_evidence"]["automatic_verification_passed"] = False
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "main.tex"
            result = render(data, output)
        self.assertEqual(result.returncode, 2)
        self.assertIn("not independently verified", result.stdout)


if __name__ == "__main__":
    unittest.main()
