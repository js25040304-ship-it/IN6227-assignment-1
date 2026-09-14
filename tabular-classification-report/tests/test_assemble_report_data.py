#!/usr/bin/env python3

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "assemble_report_data.py"
VERIFY = Path(__file__).resolve().parents[1] / "scripts" / "verify_run.py"


class AssembleReportDataTests(unittest.TestCase):
    def make_run(self, root: Path, *, verified: bool = True, status: str = "modelled") -> Path:
        run = root / "RUN-T01"
        run.mkdir()
        manifest = {
            "run_id": "RUN-T01",
            "status": status,
            "dataset": {"sha256": "data-hash"},
            "skill_sha256": "skill-hash",
            "target": "label",
            "target_resolution": "name-inferred",
            "task_type": "binary",
            "labels": ["no", "yes"],
            "positive_label": "yes",
            "random_seed": 42,
            "runtime_versions": {"python": "3.12"},
            "row_reconciliation": {
                "train": {"usable_labelled_rows": 8, "missing_target_rows": 0},
                "test": {"usable_labelled_rows": 4, "missing_target_rows": 0},
            },
            "warnings": [{"code": "SUSPICIOUS_AGGREGATE", "severity": "review"}],
            "errors": [],
            "modelling": {
                "selected_model": "random_forest",
                "final_rows": 4,
                "labelled_final_rows": 4,
                "selected_parameters": {"trees": 10},
                "models": ["dummy_most_frequent", "logistic_regression", "random_forest"],
                "selected_features": ["x", "kind"],
                "selected_feature_set": "without_suspicious_aggregates",
                "suspicious_aggregates": ["composite_rank"],
                "aggregate_policy": "drop",
                "warning_resolutions": {"SUSPICIOUS_AGGREGATE": "drop"},
                "split_strategy": "supplied-test",
                "splitter": "StratifiedKFold(shuffle=True)",
                "folds": 2,
                "primary_metric": "macro_f1",
                "test_labels_used_for_feature_or_model_selection": False,
            },
        }
        profile = {
            "run_id": "RUN-T01",
            "splits": {
                "train": {
                    "shape": {"rows": 8, "columns": 4},
                    "column_types": {"x": "numeric", "kind": "categorical", "composite_rank": "numeric", "label": "categorical"},
                    "rows_with_any_missing": 1,
                    "exact_duplicate_rows": 0,
                    "target": {"observed": 8, "missing": 0, "classes": [{"label": "no", "count": 4, "ratio": 0.5}, {"label": "yes", "count": 4, "ratio": 0.5}]},
                    "numeric_summary": {"x": {"iqr_outlier_count": 2}, "composite_rank": {"iqr_outlier_count": 1}},
                },
                "test": {
                    "shape": {"rows": 4, "columns": 4},
                    "column_types": {"x": "numeric", "kind": "categorical", "composite_rank": "numeric", "label": "categorical"},
                    "rows_with_any_missing": 0,
                    "exact_duplicate_rows": 0,
                    "target": {"observed": 4, "missing": 0, "classes": [{"label": "no", "count": 2, "ratio": 0.5}, {"label": "yes", "count": 2, "ratio": 0.5}]},
                },
            },
            "cross_split": {"unseen_test_categories": []},
        }
        selected_metrics = {
            "evaluated_rows": 4,
            "accuracy": 0.75,
            "balanced_accuracy": 0.75,
            "macro_precision": 0.8333333333333333,
            "macro_recall": 0.75,
            "macro_f1": 0.7333333333333334,
            "weighted_precision": 0.8333333333333333,
            "weighted_recall": 0.75,
            "weighted_f1": 0.7333333333333334,
            "roc_auc": 1.0,
            "average_precision": 1.0,
            "per_class": {"no": {"precision": 0.6666666666666666, "recall": 1.0, "f1": 0.8, "support": 2}, "yes": {"precision": 1.0, "recall": 0.5, "f1": 0.6666666666666666, "support": 2}},
            "confusion_matrix": {"labels": ["no", "yes"], "values": [[2, 0], [1, 1]]},
        }
        metrics = {
            "run_id": "RUN-T01",
            "selected_model": "random_forest",
            "models": {"random_forest": selected_metrics, "logistic_regression": selected_metrics, "dummy_most_frequent": selected_metrics},
        }
        for name, payload in {
            "run_manifest.json": manifest,
            "data_profile.json": profile,
            "decision_log.json": [{"id": "D001"}],
            "test_metrics.json": metrics,
        }.items():
            (run / name).write_text(json.dumps(payload), encoding="utf-8")
        with (run / "model_comparison.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["feature_set", "model", "selected_parameters", "development_macro_f1_mean", "development_macro_f1_std", "selected_model"])
            writer.writeheader()
            writer.writerow({"feature_set": "without_suspicious_aggregates", "model": "random_forest", "selected_parameters": "{}", "development_macro_f1_mean": "0.72", "development_macro_f1_std": "0.02", "selected_model": "True"})
            writer.writerow({"feature_set": "without_suspicious_aggregates", "model": "logistic_regression", "selected_parameters": "{}", "development_macro_f1_mean": "0.70", "development_macro_f1_std": "0.03", "selected_model": "False"})
        with (run / "cv_results.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["feature_set", "model", "parameters"])
            writer.writeheader()
            writer.writerow({"feature_set": "without_suspicious_aggregates", "model": "random_forest", "parameters": '{"trees": 10}'})
            writer.writerow({"feature_set": "without_suspicious_aggregates", "model": "random_forest", "parameters": '{"trees": 20}'})
            writer.writerow({"feature_set": "without_suspicious_aggregates", "model": "logistic_regression", "parameters": '{"C": 1.0}'})
        prediction_rows = [
            {"source_row_index": 0, "true_label": "no", "predicted_label": "no", "score__no": 0.9, "score__yes": 0.1},
            {"source_row_index": 1, "true_label": "no", "predicted_label": "no", "score__no": 0.8, "score__yes": 0.2},
            {"source_row_index": 2, "true_label": "yes", "predicted_label": "no", "score__no": 0.6, "score__yes": 0.4},
            {"source_row_index": 3, "true_label": "yes", "predicted_label": "yes", "score__no": 0.2, "score__yes": 0.8},
        ]
        with (run / "predictions.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["source_row_index", "true_label", "predicted_label", "model", "score__no", "score__yes"])
            writer.writeheader()
            writer.writerows({**row, "model": "random_forest"} for row in prediction_rows)
        with (run / "predictions_all_models.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["source_row_index", "true_label", "predicted_label", "model", "score__no", "score__yes"])
            writer.writeheader()
            for model in metrics["models"]:
                writer.writerows({**row, "model": model} for row in prediction_rows)
        with (run / "fold_assignments.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["source_row_index", "fold"])
            writer.writeheader()
            writer.writerows({"source_row_index": index, "fold": index % 2} for index in range(8))
        verified_result = subprocess.run(
            [sys.executable, str(VERIFY), str(run), "--output", str(run / "verification.json")],
            text=True, capture_output=True, check=False,
        )
        if verified_result.returncode != 0:
            raise AssertionError(verified_result.stdout + verified_result.stderr)
        if not verified:
            verification = json.loads((run / "verification.json").read_text())
            verification["all_checks_passed"] = False
            (run / "verification.json").write_text(json.dumps(verification), encoding="utf-8")
        return run

    def run_assembler(self, run: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(SCRIPT), str(run)], text=True, capture_output=True, check=False)

    def test_assembles_traceable_report_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run = self.make_run(Path(temp))
            result = self.run_assembler(run)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads((run / "report" / "report_data.json").read_text())
            self.assertEqual(payload["results"]["selected_model"], "random_forest")
            self.assertEqual(payload["results"]["selected_final_metrics"]["evaluated_rows"], 4)
            self.assertEqual(payload["dataset"]["splits"]["train"]["predictor_type_counts"], {"categorical": 1, "numeric": 2})
            self.assertEqual(payload["method"]["preprocessing"]["excluded_features"], ["composite_rank"])
            self.assertEqual(payload["method"]["tuning"]["search"]["random_forest"]["parameter_values"]["trees"], [10, 20])
            self.assertEqual(payload["method"]["preprocessing"]["selected_feature_set"], "without_suspicious_aggregates")
            self.assertEqual(payload["dataset"]["splits"]["train"]["iqr_flagged_value_count"], 3)
            self.assertTrue(payload["source_evidence"]["automatic_verification_passed"])

    def test_refuses_unverified_run_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run = self.make_run(Path(temp), verified=False)
            result = self.run_assembler(run)
            self.assertEqual(result.returncode, 2)
            self.assertIn("verification did not pass", result.stdout)
            self.assertFalse((run / "report" / "report_data.json").exists())

    def test_refuses_conflicting_verification_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run = self.make_run(Path(temp))
            path = run / "verification.json"
            verification = json.loads(path.read_text())
            verification["checks"]["accuracy"] = False
            path.write_text(json.dumps(verification))
            result = self.run_assembler(run)
            self.assertEqual(result.returncode, 2)
            self.assertIn("individual checks", result.stdout)

    def test_refuses_unconfirmed_final_test_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run = self.make_run(Path(temp))
            path = run / "run_manifest.json"
            manifest = json.loads(path.read_text())
            manifest["modelling"]["test_labels_used_for_feature_or_model_selection"] = True
            path.write_text(json.dumps(manifest))
            result = self.run_assembler(run)
            self.assertEqual(result.returncode, 2)
            self.assertIn("Final-test isolation", result.stdout)

    def test_refuses_non_reportable_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run = self.make_run(Path(temp), status="needs_input")
            result = self.run_assembler(run)
            self.assertEqual(result.returncode, 2)
            self.assertIn("not reportable", result.stdout)

    def test_refuses_selected_model_disagreement(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run = self.make_run(Path(temp))
            path = run / "test_metrics.json"
            metrics = json.loads(path.read_text())
            del metrics["models"]["random_forest"]
            path.write_text(json.dumps(metrics))
            result = self.run_assembler(run)
            self.assertEqual(result.returncode, 2)
            self.assertIn("Selected model is missing", result.stdout)

    def test_refuses_manifest_metrics_selection_disagreement(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run = self.make_run(Path(temp))
            path = run / "test_metrics.json"
            metrics = json.loads(path.read_text())
            metrics["selected_model"] = "logistic_regression"
            path.write_text(json.dumps(metrics))
            result = self.run_assembler(run)
            self.assertEqual(result.returncode, 2)
            self.assertIn("disagrees", result.stdout)

    def test_refuses_predictions_changed_after_saved_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run = self.make_run(Path(temp))
            path = run / "predictions_all_models.csv"
            with path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            rows[0]["predicted_label"] = "yes"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            result = self.run_assembler(run)
            self.assertEqual(result.returncode, 2)
            self.assertIn("changed after verification", result.stdout)

    def test_preserves_multiclass_weighted_ovr_auc(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run = self.make_run(Path(temp))
            metrics_path = run / "test_metrics.json"
            metrics = json.loads(metrics_path.read_text())
            metrics["models"]["random_forest"]["roc_auc_ovr_weighted"] = 0.812
            metrics_path.write_text(json.dumps(metrics), encoding="utf-8")
            subprocess.run([sys.executable, str(VERIFY), str(run), "--output", str(run / "verification.json")], check=True, capture_output=True, text=True)
            result = self.run_assembler(run)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads((run / "report" / "report_data.json").read_text())
            self.assertEqual(payload["results"]["selected_final_metrics"]["roc_auc_ovr_weighted"], 0.812)


if __name__ == "__main__":
    unittest.main()
