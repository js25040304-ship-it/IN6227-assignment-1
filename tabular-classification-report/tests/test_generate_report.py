#!/usr/bin/env python3

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_report.py"


def model_metrics(macro_f1: float, balanced: float, accuracy: float, recall: float, precision: float):
    return {
        "evaluated_rows": 4,
        "accuracy": accuracy,
        "balanced_accuracy": balanced,
        "macro_f1": macro_f1,
        "roc_auc": 0.8,
        "average_precision": 0.7,
        "per_class": {"no": {"recall": 1.0, "precision": 0.8}, "yes": {"recall": recall, "precision": precision}},
        "confusion_matrix": {"labels": ["no", "yes"], "values": [[2, 0], [1, 1]]},
    }


def report_data() -> dict:
    dummy = model_metrics(0.33, 0.5, 0.5, 0.0, 0.0)
    logistic = model_metrics(0.70, 0.70, 0.75, 0.5, 1.0)
    forest = model_metrics(0.73, 0.75, 0.75, 0.5, 1.0)
    return {
        "run_id": "RUN-T01",
        "source_evidence": {"automatic_verification_passed": True, "verification_checks": {"accuracy": True, "confusion_matrix": True}},
        "task": {"target": "label", "type": "binary", "positive_label": "yes"},
        "dataset": {
            "splits": {
                "train": {
                    "usable_labelled_rows": 8,
                    "missing_target_rows": 0,
                    "rows_with_any_missing": 1,
                    "exact_duplicate_rows": 0,
                    "predictor_type_counts": {"numeric": 1, "categorical": 1},
                    "class_distribution": [{"label": "no", "count": 4, "ratio": 0.5}, {"label": "yes", "count": 4, "ratio": 0.5}],
                    "iqr_outlier_counts": {"x": 2},
                    "iqr_flagged_value_count": 2,
                },
                "test": {"usable_labelled_rows": 4, "rows_with_any_missing": 0},
            },
            "cross_split_checks": {"predictor_overlap": {"test_rows_matching_train_predictors": 0}},
        },
        "quality_findings": {
            "warnings": [{"code": "CLASS_IMBALANCE", "majority_to_minority_ratio": 1.0}],
            "suspicious_aggregate_sensitivity": [
                {"model": "logistic_regression", "delta_without_minus_full": 0.001},
                {"model": "random_forest", "delta_without_minus_full": -0.001},
            ],
        },
        "method": {
            "models": ["dummy_most_frequent", "logistic_regression", "random_forest"],
            "preprocessing": {"excluded_features": ["composite_rank"], "selected_feature_set": "without_suspicious_aggregates"},
            "validation": {"folds": 2, "random_seed": 42},
            "tuning": {"search": {
                "logistic_regression": {"feature_sets": {"without_suspicious_aggregates": 2}, "parameter_values": {"model__C": [0.1, 1.0]}},
                "random_forest": {"feature_sets": {"without_suspicious_aggregates": 2}, "parameter_values": {"model__n_estimators": [100, 300]}},
            }},
            "selected_parameters": {"model__n_estimators": 300},
            "selection_diagnostics": {"mean_difference": 0.03, "random_forest_fold_wins": 2, "standard_error": 0.01},
        },
        "results": {
            "selected_model": "random_forest",
            "selected_final_metrics": forest,
            "final_metrics_by_model": {"dummy_most_frequent": dummy, "logistic_regression": logistic, "random_forest": forest},
            "development_comparison": [
                {"model": "dummy_most_frequent", "feature_set": "not-applicable", "development": {"macro_f1_mean": 0.33}},
                {"model": "logistic_regression", "feature_set": "without_suspicious_aggregates", "development": {"macro_f1_mean": 0.69}},
                {"model": "random_forest", "feature_set": "without_suspicious_aggregates", "development": {"macro_f1_mean": 0.72}},
            ],
        },
        "reproducibility": {"runtime_versions": {"python": "3.12", "scikit-learn": "1.9"}},
    }


class GenerateReportTests(unittest.TestCase):
    def invoke(
        self,
        root: Path,
        full_name: str = "Example Student",
        selected_model: str = "random_forest",
        cross_split_none: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        data = root / "report_data.json"
        payload = report_data()
        if selected_model == "logistic_regression":
            payload["results"]["selected_model"] = selected_model
            payload["results"]["selected_final_metrics"] = payload["results"]["final_metrics_by_model"][selected_model]
        if cross_split_none:
            payload["dataset"]["cross_split_checks"] = None
        data.write_text(json.dumps(payload), encoding="utf-8")
        template = root / "template.docx"
        Document().save(template)
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(data),
                "--template-docx", str(template),
                "--full-name", full_name,
                "--matric-number", "TEST001",
                "--github-url", "https://github.com/example/skill",
                "--model-name", "ExampleModel",
                "--model-version", "1.0",
                "--llm-interface", "Example interface",
                "--output-docx", str(root / "report" / "report_source.docx"),
                "--figures-dir", str(root / "figures"),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_generates_two_column_source_with_required_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = self.invoke(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            output = root / "report" / "report_source.docx"
            self.assertTrue(output.is_file())
            self.assertTrue((root / "figures" / "model_performance.png").is_file())
            document = Document(output)
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
            self.assertIn("Example Student, TEST001", text)
            self.assertIn("IN6227-Assignment-1", text)
            self.assertIn("Variant-2", text)
            self.assertIn("Random forest*", text + "\n".join(cell.text for table in document.tables for row in table.rows for cell in row.cells))
            self.assertEqual(len(document.sections), 3)
            self.assertEqual(document.sections[-1]._sectPr.find(qn("w:cols")).get(qn("w:num")), "2")
            hyperlinks = [
                relationship.target_ref
                for relationship in document.part.rels.values()
                if relationship.reltype.endswith("/hyperlink")
            ]
            self.assertIn("https://github.com/example/skill", hyperlinks)

    def test_narrative_follows_logistic_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = self.invoke(root, selected_model="logistic_regression")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            document = Document(root / "report" / "report_source.docx")
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
            self.assertIn("Logistic was selected on development evidence", text)
            self.assertNotIn("Random forest was selected on development evidence", text)

    def test_single_file_report_accepts_null_cross_split_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = self.invoke(root, cross_split_none=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((root / "report" / "report_source.docx").is_file())

    def test_rejects_placeholder_identity_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = self.invoke(root, full_name="TBD")
            self.assertEqual(result.returncode, 2)
            self.assertIn("placeholders are not allowed", result.stdout)
            self.assertFalse((root / "report" / "report_source.docx").exists())

    def test_full_feature_set_uses_real_development_scores(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = report_data()
            payload["method"]["preprocessing"]["selected_feature_set"] = "full"
            for row in payload["results"]["development_comparison"]:
                if not row["model"].startswith("dummy"):
                    row["feature_set"] = "full"
            data = root / "report_data.json"
            data.write_text(json.dumps(payload), encoding="utf-8")
            template = root / "template.docx"
            Document().save(template)
            result = self.invoke_existing_data(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            cells = "\n".join(cell.text for table in Document(root / "report" / "report_source.docx").tables for row in table.rows for cell in row.cells)
            self.assertIn("0.690", cells)
            self.assertIn("0.720", cells)

    def test_multiclass_uses_weighted_ovr_auc_without_fake_average_precision(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = report_data()
            payload["task"].update({"type": "multiclass", "positive_label": None, "labels": ["a", "b", "c", "d"]})
            for metrics in payload["results"]["final_metrics_by_model"].values():
                metrics.pop("roc_auc", None)
                metrics.pop("average_precision", None)
                metrics["roc_auc_ovr_weighted"] = 0.812
                metrics["confusion_matrix"] = {"labels": ["a", "b", "c", "d"], "values": [[1, 0, 0, 0]] * 4}
                metrics["per_class"] = {label: {"precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 1} for label in "abcd"}
            payload["results"]["selected_final_metrics"] = payload["results"]["final_metrics_by_model"]["random_forest"]
            (root / "report_data.json").write_text(json.dumps(payload), encoding="utf-8")
            Document().save(root / "template.docx")
            result = self.invoke_existing_data(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            text = "\n".join(p.text for p in Document(root / "report" / "report_source.docx").paragraphs)
            self.assertIn("weighted OvR ROC-AUC", text)
            self.assertIn("0.812", text)
            self.assertNotIn("average precision", text.lower())

    def test_unresolved_binary_positive_label_uses_balanced_accuracy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = report_data()
            payload["task"]["positive_label"] = None
            for metrics in payload["results"]["final_metrics_by_model"].values():
                metrics.pop("roc_auc", None)
                metrics.pop("average_precision", None)
            payload["results"]["selected_final_metrics"] = payload["results"]["final_metrics_by_model"]["random_forest"]
            (root / "report_data.json").write_text(json.dumps(payload), encoding="utf-8")
            Document().save(root / "template.docx")
            result = self.invoke_existing_data(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            document = Document(root / "report" / "report_source.docx")
            text = "\n".join(p.text for p in document.paragraphs) + "\n" + "\n".join(cell.text for table in document.tables for row in table.rows for cell in row.cells)
            self.assertNotIn("None recall", text)
            self.assertNotIn("positive recall", text.lower())
            self.assertIn("Bal. acc.", text)

    def test_report_records_outlier_policy_and_exact_tuning_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = self.invoke(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            text = "\n".join(p.text for p in Document(root / "report" / "report_source.docx").paragraphs)
            self.assertIn("2 IQR-flagged", text)
            self.assertNotIn("model__", text)
            self.assertIn("C=0.1/1.0", text)
            self.assertIn("0.1", text)
            self.assertIn("trees=100/300", text)
            self.assertIn("trees=300", text)
            self.assertIn("300", text)

    def test_report_supports_adaptive_boosting_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = report_data()
            forest = payload["results"]["final_metrics_by_model"].pop("random_forest")
            payload["results"]["final_metrics_by_model"]["hist_gradient_boosting"] = forest
            payload["results"]["selected_model"] = "hist_gradient_boosting"
            payload["results"]["selected_final_metrics"] = forest
            payload["method"]["models"] = ["dummy_most_frequent", "logistic_regression", "hist_gradient_boosting"]
            payload["method"]["tuning"]["search"].pop("random_forest")
            payload["method"]["tuning"]["search"]["hist_gradient_boosting"] = {
                "feature_sets": {"without_suspicious_aggregates": 2},
                "parameter_values": {"model__max_leaf_nodes": [15, 31]},
            }
            payload["method"]["selection_diagnostics"] = {
                "reference_model": "logistic_regression",
                "challenger_model": "hist_gradient_boosting",
                "mean_difference": 0.03,
                "challenger_fold_wins": 2,
                "standard_error": 0.01,
            }
            for row in payload["results"]["development_comparison"]:
                if row["model"] == "random_forest":
                    row["model"] = "hist_gradient_boosting"
            (root / "report_data.json").write_text(json.dumps(payload), encoding="utf-8")
            Document().save(root / "template.docx")
            result = self.invoke_existing_data(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            document = Document(root / "report" / "report_source.docx")
            text = "\n".join(p.text for p in document.paragraphs)
            cells = "\n".join(cell.text for table in document.tables for row in table.rows for cell in row.cells)
            self.assertIn("Hist. gradient boosting was selected on development evidence", text)
            self.assertIn("Hist. gradient boosting*", cells)

    def invoke_existing_data(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(root / "report_data.json"), "--template-docx", str(root / "template.docx"),
             "--full-name", "Example Student", "--matric-number", "TEST001", "--github-url", "https://github.com/example/skill",
             "--model-name", "ExampleModel", "--model-version", "1.0", "--llm-interface", "Example interface",
             "--output-docx", str(root / "report" / "report_source.docx"), "--figures-dir", str(root / "figures")],
            text=True, capture_output=True, check=False,
        )


if __name__ == "__main__":
    unittest.main()
