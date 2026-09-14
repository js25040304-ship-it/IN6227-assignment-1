#!/usr/bin/env python3

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import pandas as pd


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "profile_data.py"


class ProfileDataTests(unittest.TestCase):
    def run_profile(self, source: Path, output: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(source), "--output-dir", str(output), "--run-id", output.name, *extra],
            text=True,
            capture_output=True,
            check=False,
        )

    def run_profile_auto(self, source: Path, working_directory: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(source)],
            cwd=working_directory,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_single_csv_infers_label_and_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "data.csv"
            pd.DataFrame({"x": [1, 2, 3, 4], "kind": ["a", "a", "b", "b"], "label": ["n", "n", "y", "y"]}).to_csv(source, index=False)
            output = root / "RUN-T01"
            result = self.run_profile(source, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output / "run_manifest.json").read_text())
            self.assertEqual(manifest["target"], "label")
            self.assertEqual(manifest["task_type"], "binary")
            self.assertEqual(manifest["status"], "profiled")

    def test_ambiguous_target_creates_needs_input_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "data.csv"
            pd.DataFrame({"x": [1, 2, 3, 4], "target": ["a", "a", "b", "b"], "label": ["u", "v", "u", "v"]}).to_csv(source, index=False)
            output = root / "RUN-T02"
            result = self.run_profile(source, output)
            self.assertEqual(result.returncode, 3, result.stderr)
            manifest = json.loads((output / "run_manifest.json").read_text())
            self.assertEqual(manifest["status"], "needs_input")
            self.assertIn("TARGET_UNRESOLVED", [item["code"] for item in manifest["warnings"]])

    def test_unsafe_zip_is_rejected_without_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "unsafe.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("../train.csv", "x,label\n1,a\n2,b\n")
            output = root / "RUN-T03"
            result = self.run_profile(source, output)
            self.assertEqual(result.returncode, 2)
            self.assertIn("Unsafe ZIP member path", result.stderr)
            self.assertFalse(output.exists())

    def test_train_test_pair_checks_unseen_categories(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "pair.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("train.csv", "x,kind,label\n1,a,n\n2,a,n\n3,b,y\n4,b,y\n")
                archive.writestr("test.csv", "x,kind,label\n5,c,n\n6,a,y\n")
            output = root / "RUN-T04"
            result = self.run_profile(source, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            profile = json.loads((output / "data_profile.json").read_text())
            unseen = profile["cross_split"]["unseen_test_categories"]
            self.assertEqual(unseen[0]["column"], "kind")
            self.assertEqual(unseen[0]["values"], ["c"])

    def test_dataset_path_only_allocates_run_and_infers_datetime_and_positive_label(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "data.csv"
            pd.DataFrame(
                {
                    "event_date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
                    "x": [1, 2, 3, 4],
                    "label": ["no", "no", "yes", "yes"],
                }
            ).to_csv(source, index=False)
            result = self.run_profile_auto(source, root)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = root / "runs" / "RUN-001"
            manifest = json.loads((output / "run_manifest.json").read_text())
            profile = json.loads((output / "data_profile.json").read_text())
            self.assertEqual(manifest["target_resolution"], "name-inferred")
            self.assertEqual(manifest["positive_label"], "yes")
            self.assertEqual(manifest["positive_label_resolution"], "semantic-name-inferred")
            self.assertEqual(profile["splits"]["train"]["column_types"]["event_date"], "datetime")
            candidates = profile["splits"]["train"]["dependency_candidates"]
            self.assertEqual(candidates, [{"column": "event_date", "kind": "time", "reason": "datetime predictor may encode observation order"}])
            self.assertIn("DEPENDENCY_STRUCTURE_REVIEW", [item["code"] for item in manifest["warnings"]])

    def test_repeated_entity_identifier_is_flagged_for_dependency_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "data.csv"
            pd.DataFrame(
                {
                    "subject_id": ["p1", "p1", "p2", "p2", "p3", "p3"],
                    "x": [1, 2, 3, 4, 5, 6],
                    "label": ["no", "yes", "no", "yes", "no", "yes"],
                }
            ).to_csv(source, index=False)
            output = root / "RUN-T08"
            result = self.run_profile(source, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            profile = json.loads((output / "data_profile.json").read_text())
            self.assertEqual(profile["splits"]["train"]["dependency_candidates"][0]["column"], "subject_id")
            self.assertEqual(profile["splits"]["train"]["dependency_candidates"][0]["kind"], "group")

    def test_semantic_type_mismatch_blocks_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "pair.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("train.csv", "x,label\n1,no\n2,no\n3,yes\n4,yes\n")
                archive.writestr("test.csv", "x,label\nbad,no\nworse,yes\n")
            output = root / "RUN-T05"
            result = self.run_profile(source, output)
            self.assertEqual(result.returncode, 3, result.stderr)
            manifest = json.loads((output / "run_manifest.json").read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertIn("SPLIT_TYPE_MISMATCH", [item["code"] for item in manifest["warnings"]])

    def test_unseen_test_label_blocks_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "pair.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("train.csv", "x,label\n1,no\n2,no\n3,yes\n4,yes\n")
                archive.writestr("test.csv", "x,label\n5,no\n6,maybe\n")
            output = root / "RUN-T06"
            result = self.run_profile(source, output)
            self.assertEqual(result.returncode, 3, result.stderr)
            manifest = json.loads((output / "run_manifest.json").read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertIn("UNSEEN_TEST_LABEL", [item["code"] for item in manifest["warnings"]])

    def test_suspicious_aggregate_is_promoted_to_warning_and_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "data.csv"
            pd.DataFrame(
                {
                    "base": [1, 2, 3, 4],
                    "composite_rank": [10, 20, 30, 40],
                    "label": ["no", "no", "yes", "yes"],
                }
            ).to_csv(source, index=False)
            output = root / "RUN-T07"
            result = self.run_profile(source, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output / "run_manifest.json").read_text())
            decisions = json.loads((output / "decision_log.json").read_text())
            self.assertIn("SUSPICIOUS_AGGREGATE", [item["code"] for item in manifest["warnings"]])
            self.assertIn("DPROF-005", [item["id"] for item in decisions])


if __name__ == "__main__":
    unittest.main()
