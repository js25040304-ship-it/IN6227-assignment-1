#!/usr/bin/env python3

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import pandas as pd


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "train_evaluate.py"


class TrainEvaluateTests(unittest.TestCase):
    def run_model(self, source: Path, output: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(source),
                "--output-dir",
                str(output),
                "--run-id",
                output.name,
                "--smoke",
                *extra,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def write_binary_pair(self, root: Path) -> Path:
        train = pd.DataFrame(
            {
                "x": list(range(30)),
                "kind": ["a", "b", "c"] * 10,
                "composite_rank": [value * 2 for value in range(30)],
                "label": ["no", "yes"] * 15,
            }
        )
        test = pd.DataFrame(
            {
                "x": list(range(30, 42)),
                "kind": ["a", "b", "c"] * 4,
                "composite_rank": [value * 2 for value in range(30, 42)],
                "label": ["no", "yes"] * 6,
            }
        )
        source = root / "pair.zip"
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("train.csv", train.to_csv(index=False))
            archive.writestr("test.csv", test.to_csv(index=False))
        return source

    def test_suspicious_aggregate_pauses_before_test_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.write_binary_pair(root)
            output = root / "RUN-M01"
            result = self.run_model(source, output)
            self.assertEqual(result.returncode, 3, result.stderr)
            manifest = json.loads((output / "run_manifest.json").read_text())
            self.assertEqual(manifest["status"], "needs_input")
            self.assertEqual(manifest["modelling"]["status"], "awaiting-aggregate-decision")
            self.assertFalse((output / "test_metrics.json").exists())
            self.assertTrue((output / "sensitivity_results.csv").exists())

    def test_human_keep_policy_completes_final_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.write_binary_pair(root)
            output = root / "RUN-M02"
            result = self.run_model(source, output, "--aggregate-policy", "keep")
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output / "run_manifest.json").read_text())
            metrics = json.loads((output / "test_metrics.json").read_text())
            verification = json.loads((output / "verification.json").read_text())
            predictions = pd.read_csv(output / "predictions.csv")
            all_predictions = pd.read_csv(output / "predictions_all_models.csv")
            folds = pd.read_csv(output / "fold_assignments.csv")
            self.assertEqual(manifest["status"], "modelled")
            self.assertIn(manifest["modelling"]["selected_model"], {"logistic_regression", "random_forest"})
            self.assertIn("selection_diagnostics", manifest["modelling"])
            self.assertEqual(len(predictions), 12)
            self.assertEqual(len(all_predictions), 36)
            self.assertEqual(set(all_predictions["model"]), set(metrics["models"]))
            self.assertEqual(len(folds), 30)
            self.assertTrue(verification["all_checks_passed"])
            self.assertEqual(set(verification["models"]), set(metrics["models"]))
            for model in metrics["models"]:
                self.assertTrue(verification["checks"][f"{model}.accuracy"])
                self.assertTrue(verification["checks"][f"{model}.confusion_matrix"])
            for model_metrics in metrics["models"].values():
                matrix_total = sum(sum(row) for row in model_metrics["confusion_matrix"]["values"])
                self.assertEqual(matrix_total, model_metrics["evaluated_rows"])
                self.assertIn("macro_precision", model_metrics)
                self.assertIn("weighted_recall", model_metrics)

    def test_single_multiclass_file_creates_holdout_and_models(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "multiclass.csv"
            pd.DataFrame(
                {
                    "x": list(range(60)),
                    "kind": ["a", "b", "c", "d"] * 15,
                    "event_date": pd.date_range("2026-01-01", periods=60).astype(str),
                    "label": ["red", "blue", "green"] * 20,
                }
            ).to_csv(source, index=False)
            output = root / "RUN-M03"
            result = self.run_model(source, output, "--dependency-policy", "independent")
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output / "run_manifest.json").read_text())
            metrics = json.loads((output / "test_metrics.json").read_text())
            self.assertEqual(manifest["task_type"], "multiclass")
            self.assertEqual(manifest["modelling"]["split_strategy"], "stratified-20%-holdout")
            self.assertEqual(manifest["modelling"]["labelled_final_rows"], 12)
            selected = metrics["models"][metrics["selected_model"]]
            self.assertIn("macro_precision", selected)
            self.assertIn("weighted_precision", selected)
            self.assertIn("macro_recall", selected)
            self.assertIn("weighted_recall", selected)

    def test_datetime_candidate_pauses_before_cross_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "temporal.csv"
            pd.DataFrame(
                {
                    "event_date": pd.date_range("2026-01-01", periods=60).astype(str),
                    "x": list(range(60)),
                    "label": ["no", "yes"] * 30,
                }
            ).to_csv(source, index=False)
            output = root / "RUN-M07"
            result = self.run_model(source, output)
            self.assertEqual(result.returncode, 3, result.stderr)
            manifest = json.loads((output / "run_manifest.json").read_text())
            self.assertEqual(manifest["status"], "needs_input")
            self.assertEqual(manifest["modelling"]["status"], "awaiting-dependency-decision")
            self.assertFalse((output / "cv_results.csv").exists())
            self.assertFalse((output / "test_metrics.json").exists())
            self.assertIn("DEPENDENCY_STRUCTURE_CONFIRMATION", [item["code"] for item in manifest["human_checkpoints"]])

    def test_numeric_only_data_uses_nonlinear_boosting_challenger(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "numeric.csv"
            values = list(range(90))
            pd.DataFrame(
                {
                    "x": values,
                    "z": [(value % 7) / 7 for value in values],
                    "label": ["yes" if (value % 11) in {0, 1, 5, 8} else "no" for value in values],
                }
            ).to_csv(source, index=False)
            output = root / "RUN-M08"
            result = self.run_model(source, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output / "run_manifest.json").read_text())
            metrics = json.loads((output / "test_metrics.json").read_text())
            self.assertEqual(
                manifest["modelling"]["candidate_models"],
                ["logistic_regression", "hist_gradient_boosting"],
            )
            self.assertIn("hist_gradient_boosting", manifest["modelling"]["candidate_selection_rationale"])
            self.assertEqual(
                set(metrics["models"]),
                {"dummy_most_frequent", "logistic_regression", "hist_gradient_boosting"},
            )

    def test_unlabelled_supplied_test_completes_predictions_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.write_binary_pair(root)
            with zipfile.ZipFile(source, "r") as archive:
                train = pd.read_csv(archive.open("train.csv"))
                test = pd.read_csv(archive.open("test.csv")).drop(columns=["label"])
            source = root / "unlabelled.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("train.csv", train.to_csv(index=False))
                archive.writestr("test.csv", test.to_csv(index=False))
            output = root / "RUN-M06"
            result = self.run_model(source, output, "--aggregate-policy", "keep")
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output / "run_manifest.json").read_text())
            verification = json.loads((output / "verification.json").read_text())
            self.assertEqual(manifest["status"], "modelled")
            self.assertEqual(manifest["modelling"]["labelled_final_rows"], 0)
            self.assertFalse((output / "test_metrics.json").exists())
            self.assertEqual(len(pd.read_csv(output / "predictions.csv")), 12)
            self.assertEqual(len(pd.read_csv(output / "predictions_all_models.csv")), 36)
            self.assertEqual(verification["mode"], "predictions-only")
            self.assertTrue(verification["all_checks_passed"])

    def test_parent_fingerprint_mismatch_retains_failed_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.write_binary_pair(root)
            parent = root / "RUN-PARENT"
            parent.mkdir()
            (parent / "run_manifest.json").write_text(
                json.dumps({"run_id": "RUN-PARENT", "status": "profiled", "dataset": {"sha256": "wrong"}})
            )
            output = root / "RUN-M04"
            result = self.run_model(source, output, "--source-profile-run", "RUN-PARENT")
            self.assertEqual(result.returncode, 2)
            manifest = json.loads((output / "run_manifest.json").read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertTrue((output / "failure.json").exists())
            self.assertIn("fingerprint", manifest["errors"][-1]["message"])

    def test_dependency_control_refuses_random_cv_and_retains_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.write_binary_pair(root)
            output = root / "RUN-M05"
            result = self.run_model(source, output, "--group-column", "entity")
            self.assertEqual(result.returncode, 2)
            manifest = json.loads((output / "run_manifest.json").read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertIn("random stratification was refused", manifest["errors"][-1]["message"])


if __name__ == "__main__":
    unittest.main()
