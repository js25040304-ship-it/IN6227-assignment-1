#!/usr/bin/env python3

"""Run immutable Phase 5 forward tests against the packaged skill."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from pypdf import PdfReader
from docx import Document


PROJECT = Path(__file__).resolve().parents[1]
SKILL = PROJECT / "tabular-classification-report"
PROFILE = SKILL / "scripts" / "profile_data.py"
TRAIN = SKILL / "scripts" / "train_evaluate.py"
ASSEMBLE = SKILL / "scripts" / "assemble_report_data.py"
REPORT = SKILL / "scripts" / "generate_report.py"


def next_root(parent: Path) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    for number in range(1, 1000):
        candidate = parent / f"PHASE5-RUN-{number:03d}"
        if not candidate.exists():
            candidate.mkdir()
            return candidate
    raise RuntimeError("No Phase 5 run ID available")


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def write_zip(path: Path, train: pd.DataFrame, test: pd.DataFrame) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("train.csv", train.to_csv(index=False))
        archive.writestr("test.csv", test.to_csv(index=False))


def model_case(
    phase_root: Path,
    case_id: str,
    source: Path,
    template: Path,
    soffice: str,
    checks,
) -> dict:
    run_dir = phase_root / "runs" / case_id
    command = [sys.executable, str(TRAIN), str(source), "--output-dir", str(run_dir), "--run-id", case_id]
    result = run(command)
    record = {"case_id": case_id, "command": command, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    if result.returncode != 0:
        record.update({"passed": False, "failure": "modelling command failed"})
        return record
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    metrics = json.loads((run_dir / "test_metrics.json").read_text())
    verification = json.loads((run_dir / "verification.json").read_text())
    observations = checks(manifest, metrics, verification)
    observations["assertions"].extend(
        [
            set(verification.get("models", [])) == set(metrics["models"]),
            all(verification["checks"].get(f"{model}.accuracy") is True for model in metrics["models"]),
            all(verification["checks"].get(f"{model}.confusion_matrix") is True for model in metrics["models"]),
        ]
    )

    assembled = run([sys.executable, str(ASSEMBLE), str(run_dir)])
    if assembled.returncode != 0:
        record.update({"passed": False, "failure": "report-data assembly failed", "assembly_stdout": assembled.stdout, "assembly_stderr": assembled.stderr})
        return record
    report_dir = run_dir / "report"
    rendered = run(
        [
            sys.executable,
            str(REPORT),
            str(report_dir / "report_data.json"),
            "--template-docx", str(template),
            "--full-name", "Phase Five Test",
            "--matric-number", "TEST005",
            "--github-url", "https://github.com/example/phase-five-test",
            "--model-name", "TestModel",
            "--model-version", "5.0",
            "--llm-interface", "Automated forward test",
            "--output-docx", str(report_dir / "report_source.docx"),
            "--output-pdf", str(report_dir / "main_report.pdf"),
            "--figures-dir", str(run_dir / "figures"),
            "--soffice", soffice,
        ]
    )
    if rendered.returncode != 0:
        record.update({"passed": False, "failure": "report generation failed", "report_stdout": rendered.stdout, "report_stderr": rendered.stderr})
        return record
    pages = len(PdfReader(report_dir / "main_report.pdf").pages)
    report_data = json.loads((report_dir / "report_data.json").read_text())
    table_cells = "\n".join(
        cell.text for table in Document(report_dir / "report_source.docx").tables for row in table.rows for cell in row.cells
    )
    selected_feature_set = manifest["modelling"]["selected_feature_set"]
    expected_cv = [
        row["development"]["macro_f1_mean"]
        for row in report_data["results"]["development_comparison"]
        if row["model"] != "dummy_most_frequent" and row["feature_set"] == selected_feature_set
    ]
    observations["assertions"].extend(f"{value:.3f}" in table_cells for value in expected_cv)
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(report_dir / "main_report.pdf").pages)
    normalized_pdf_text = " ".join(pdf_text.split())
    if manifest["task_type"] == "multiclass":
        observations["assertions"].extend(
            ["weighted OvR ROC-AUC" in normalized_pdf_text, "average precision" not in normalized_pdf_text.lower()]
        )
    observations.update(
        {
            "status": manifest["status"],
            "selected_model": metrics["selected_model"],
            "automatic_verification": verification["all_checks_passed"],
            "report_pages": pages,
        }
    )
    passed = manifest["status"] == "modelled" and verification["all_checks_passed"] is True and pages <= 2 and all(observations.pop("assertions"))
    record.update({"passed": passed, "observations": observations, "run_dir": str(run_dir.relative_to(PROJECT))})
    return record


def predictions_only_case(phase_root: Path, case_id: str, source: Path) -> dict:
    run_dir = phase_root / "runs" / case_id
    command = [sys.executable, str(TRAIN), str(source), "--output-dir", str(run_dir), "--run-id", case_id]
    result = run(command)
    manifest = json.loads((run_dir / "run_manifest.json").read_text()) if (run_dir / "run_manifest.json").exists() else {}
    verification = json.loads((run_dir / "verification.json").read_text()) if (run_dir / "verification.json").exists() else {}
    selected_rows = len(pd.read_csv(run_dir / "predictions.csv")) if (run_dir / "predictions.csv").exists() else 0
    all_rows = len(pd.read_csv(run_dir / "predictions_all_models.csv")) if (run_dir / "predictions_all_models.csv").exists() else 0
    passed = (
        result.returncode == 0
        and manifest.get("status") == "modelled"
        and manifest.get("modelling", {}).get("labelled_final_rows") == 0
        and not (run_dir / "test_metrics.json").exists()
        and verification.get("mode") == "predictions-only"
        and verification.get("all_checks_passed") is True
        and all_rows == selected_rows * 3
    )
    return {
        "case_id": case_id, "command": command, "returncode": result.returncode,
        "stdout": result.stdout, "stderr": result.stderr, "passed": passed,
        "observations": {"status": manifest.get("status"), "verification_mode": verification.get("mode"), "selected_rows": selected_rows, "all_model_rows": all_rows},
        "run_dir": str(run_dir.relative_to(PROJECT)),
    }


def profile_case(phase_root: Path, case_id: str, source: Path, expected_status: str, expected_code: str) -> dict:
    run_dir = phase_root / "runs" / case_id
    command = [sys.executable, str(PROFILE), str(source), "--output-dir", str(run_dir), "--run-id", case_id]
    result = run(command)
    manifest = json.loads((run_dir / "run_manifest.json").read_text()) if (run_dir / "run_manifest.json").exists() else {}
    codes = [warning.get("code") for warning in manifest.get("warnings", [])]
    # Profiling uses exit code 3 for every intentional non-profiled outcome;
    # the manifest status distinguishes needs_input from a terminal failure.
    expected_return = 3
    passed = result.returncode == expected_return and manifest.get("status") == expected_status and expected_code in codes
    return {
        "case_id": case_id,
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "passed": passed,
        "observations": {"status": manifest.get("status"), "warning_codes": codes},
        "run_dir": str(run_dir.relative_to(PROJECT)),
    }


def dependency_checkpoint_case(phase_root: Path, case_id: str, source: Path, expected_kind: str) -> dict:
    run_dir = phase_root / "runs" / case_id
    command = [sys.executable, str(TRAIN), str(source), "--output-dir", str(run_dir), "--run-id", case_id]
    result = run(command)
    manifest = json.loads((run_dir / "run_manifest.json").read_text()) if (run_dir / "run_manifest.json").exists() else {}
    candidates = manifest.get("modelling", {}).get("dependency_candidates", [])
    passed = (
        result.returncode == 3
        and manifest.get("status") == "needs_input"
        and manifest.get("modelling", {}).get("status") == "awaiting-dependency-decision"
        and expected_kind in {item.get("kind") for item in candidates}
        and not (run_dir / "cv_results.csv").exists()
        and not (run_dir / "test_metrics.json").exists()
    )
    return {
        "case_id": case_id,
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "passed": passed,
        "observations": {
            "status": manifest.get("status"),
            "modelling_status": manifest.get("modelling", {}).get("status"),
            "dependency_candidates": candidates,
            "cv_started": (run_dir / "cv_results.csv").exists(),
        },
        "run_dir": str(run_dir.relative_to(PROJECT)),
    }


def make_cases(root: Path) -> dict[str, Path]:
    data_dir = root / "datasets"
    data_dir.mkdir()
    rng = np.random.default_rng(20260914)

    n = 120
    x1, x2, x3 = rng.normal(size=n), rng.normal(size=n), rng.uniform(-1, 1, size=n)
    numeric = pd.DataFrame({"x1": x1, "x2": x2, "x3": x3, "label": np.where(x1 + 0.6 * x2 + 0.2 * rng.normal(size=n) > 0, "yes", "no")})
    numeric_path = data_dir / "numeric_binary.tsv"
    numeric.to_csv(numeric_path, index=False, sep="\t")

    classes = np.array(["red", "blue", "green", "gold", "violet"] * 30)
    class_index = pd.Series(classes).map({"red": 0, "blue": 1, "green": 2, "gold": 3, "violet": 4}).to_numpy()
    mixed = pd.DataFrame(
        {
            "score": class_index + rng.normal(0, 0.35, len(classes)),
            "amount": rng.normal(10 + class_index * 2, 1.0),
            "kind": pd.Series(class_index).map({0: "alpha", 1: "beta", 2: "gamma", 3: "delta", 4: "epsilon"}),
            "channel": np.resize(["web", "store", "partner", "web", "store"], len(classes)),
            "label": classes,
        }
    ).sample(frac=1, random_state=42).reset_index(drop=True)
    mixed_path = data_dir / "mixed_multiclass.xlsx"
    mixed.to_excel(mixed_path, index=False)

    train_n, test_n = 120, 45
    train_x, test_x = rng.normal(size=train_n), rng.normal(size=test_n)
    train_kind = np.resize(["north", "south", "west"], train_n).astype(object)
    test_kind = np.resize(["north", "east", "south"], test_n).astype(object)
    train_missing = pd.DataFrame({"value": train_x, "kind": train_kind, "label": np.where(train_x > 0, "yes", "no")})
    test_missing = pd.DataFrame({"value": test_x, "kind": test_kind, "label": np.where(test_x > 0, "yes", "no")})
    train_missing.loc[[3, 17, 41], "value"] = np.nan
    train_missing.loc[[8, 55], "kind"] = None
    test_missing.loc[[2, 19], "value"] = np.nan
    test_missing.loc[[11], "kind"] = None
    missing_path = data_dir / "missing_unseen.zip"
    write_zip(missing_path, train_missing, test_missing)

    majority, minority = 135, 15
    imbalanced = pd.DataFrame(
        {
            "signal": np.concatenate([rng.normal(0, 1, majority), rng.normal(2.0, 1, minority)]),
            "noise": rng.normal(size=majority + minority),
            "segment": np.resize(["a", "b", "c"], majority + minority),
            "label": ["no"] * majority + ["yes"] * minority,
        }
    ).sample(frac=1, random_state=42).reset_index(drop=True)
    imbalance_path = data_dir / "imbalanced.csv"
    imbalanced.to_csv(imbalance_path, index=False)

    ambiguous = pd.DataFrame({"x": range(30), "target": ["a", "b"] * 15, "label": ["yes", "no"] * 15})
    ambiguous_path = data_dir / "ambiguous_target.csv"
    ambiguous.to_csv(ambiguous_path, index=False)
    absent = pd.DataFrame({"feature_a": range(30), "feature_b": rng.normal(size=30)})
    absent_path = data_dir / "absent_target.csv"
    absent.to_csv(absent_path, index=False)

    too_small = pd.DataFrame({"x": [0, 1, 2], "label": ["no", "no", "yes"]})
    too_small_path = data_dir / "too_small.csv"
    too_small.to_csv(too_small_path, index=False)
    single = pd.DataFrame({"x": range(12), "label": ["no"] * 12})
    single_path = data_dir / "single_class.csv"
    single.to_csv(single_path, index=False)

    ab = pd.DataFrame({"signal": rng.normal(size=120), "kind": np.resize(["x", "y", "z"], 120)})
    ab["label"] = np.where(ab["signal"] > 0, "A", "B")
    ab_path = data_dir / "unresolved_positive.tsv"
    ab.to_csv(ab_path, index=False, sep="\t")

    directory_pair = data_dir / "directory_pair"
    directory_pair.mkdir()
    numeric.iloc[:90].to_csv(directory_pair / "train.csv", index=False)
    numeric.iloc[90:].to_csv(directory_pair / "test.csv", index=False)

    unlabelled_path = data_dir / "unlabelled_test.zip"
    write_zip(unlabelled_path, train_missing, test_missing.drop(columns=["label"]))

    temporal = numeric.copy()
    temporal.insert(0, "event_date", pd.date_range("2026-01-01", periods=len(temporal)).astype(str))
    temporal_path = data_dir / "temporal.csv"
    temporal.to_csv(temporal_path, index=False)

    grouped = numeric.copy()
    grouped.insert(0, "subject_id", np.resize([f"p{number:02d}" for number in range(30)], len(grouped)))
    grouped_path = data_dir / "grouped.csv"
    grouped.to_csv(grouped_path, index=False)

    return {
        "numeric": numeric_path,
        "mixed": mixed_path,
        "missing": missing_path,
        "imbalanced": imbalance_path,
        "ambiguous": ambiguous_path,
        "absent": absent_path,
        "too_small": too_small_path,
        "single": single_path,
        "ab": ab_path,
        "directory": directory_pair,
        "unlabelled": unlabelled_path,
        "temporal": temporal_path,
        "grouped": grouped_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template-docx", type=Path, required=True)
    parser.add_argument("--soffice", required=True)
    args = parser.parse_args()
    phase_root = next_root(PROJECT / "forward-tests" / "artifacts")
    cases = make_cases(phase_root)
    results = []

    results.append(
        model_case(
            phase_root,
            "FT-001",
            cases["numeric"],
            args.template_docx,
            args.soffice,
            lambda manifest, metrics, verification: {
                "assertions": [
                    manifest["task_type"] == "binary",
                    manifest["target"] == "label",
                    manifest["modelling"]["labelled_final_rows"] > 0,
                    manifest["modelling"]["candidate_models"] == ["logistic_regression", "hist_gradient_boosting"],
                ],
                "task_type": manifest["task_type"],
                "predictor_types": json.loads((phase_root / "runs" / "FT-001" / "data_profile.json").read_text())["splits"]["train"]["column_types"],
            },
        )
    )
    results.append(
        model_case(
            phase_root,
            "FT-002",
            cases["mixed"],
            args.template_docx,
            args.soffice,
            lambda manifest, metrics, verification: {
                "assertions": [
                    manifest["task_type"] == "multiclass",
                    len(manifest["labels"]) == 5,
                    manifest["modelling"]["candidate_models"] == ["logistic_regression", "random_forest"],
                ],
                "task_type": manifest["task_type"],
                "labels": manifest["labels"],
            },
        )
    )
    results.append(
        model_case(
            phase_root,
            "FT-003",
            cases["missing"],
            args.template_docx,
            args.soffice,
            lambda manifest, metrics, verification: {
                "assertions": [
                    "MISSING_VALUES" in [item["code"] for item in manifest["warnings"]],
                    bool(json.loads((phase_root / "runs" / "FT-003" / "data_profile.json").read_text())["cross_split"]["unseen_test_categories"]),
                ],
                "warning_codes": sorted(set(item["code"] for item in manifest["warnings"])),
                "unseen_test_categories": json.loads((phase_root / "runs" / "FT-003" / "data_profile.json").read_text())["cross_split"]["unseen_test_categories"],
            },
        )
    )
    results.append(
        model_case(
            phase_root,
            "FT-004",
            cases["imbalanced"],
            args.template_docx,
            args.soffice,
            lambda manifest, metrics, verification: {
                "assertions": [
                    "CLASS_IMBALANCE" in [item["code"] for item in manifest["warnings"]],
                    manifest["modelling"]["primary_metric"] == "macro_f1",
                    metrics["models"]["dummy_most_frequent"]["per_class"]["yes"]["recall"] == 0,
                ],
                "primary_metric": manifest["modelling"]["primary_metric"],
                "warning_codes": sorted(set(item["code"] for item in manifest["warnings"])),
                "dummy_positive_recall": metrics["models"]["dummy_most_frequent"]["per_class"]["yes"]["recall"],
            },
        )
    )
    results.extend(
        [
            profile_case(phase_root, "FT-005A", cases["ambiguous"], "needs_input", "TARGET_UNRESOLVED"),
            profile_case(phase_root, "FT-005B", cases["absent"], "needs_input", "TARGET_UNRESOLVED"),
            profile_case(phase_root, "FT-006A", cases["too_small"], "failed", "CLASS_TOO_SMALL"),
            profile_case(phase_root, "FT-006B", cases["single"], "failed", "SINGLE_CLASS_TARGET"),
        ]
    )
    results.append(
        model_case(
            phase_root, "FT-007", cases["ab"], args.template_docx, args.soffice,
            lambda manifest, metrics, verification: {
                "assertions": [manifest["task_type"] == "binary", manifest["positive_label"] is None],
                "positive_label": manifest["positive_label"],
            },
        )
    )
    results.append(
        model_case(
            phase_root, "FT-008", cases["directory"], args.template_docx, args.soffice,
            lambda manifest, metrics, verification: {
                "assertions": [
                    manifest["dataset"]["kind"] == "directory",
                    manifest["modelling"]["split_strategy"] == "supplied-test",
                    manifest["modelling"]["candidate_models"] == ["logistic_regression", "hist_gradient_boosting"],
                ],
                "dataset_kind": manifest["dataset"]["kind"],
            },
        )
    )
    results.append(predictions_only_case(phase_root, "FT-009", cases["unlabelled"]))
    results.append(dependency_checkpoint_case(phase_root, "FT-010A", cases["temporal"], "time"))
    results.append(dependency_checkpoint_case(phase_root, "FT-010B", cases["grouped"], "group"))

    payload = {
        "schema_version": "1.0",
        "phase_run_id": phase_root.name,
        "created_at": datetime.now(ZoneInfo("Asia/Singapore")).isoformat(),
        "python": sys.version,
        "skill_path": str(SKILL),
        "all_passed": all(item["passed"] for item in results),
        "results": results,
    }
    (phase_root / "results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(phase_root)
    print(json.dumps({"all_passed": payload["all_passed"], "cases": {item["case_id"]: item["passed"] for item in results}}, indent=2))
    return 0 if payload["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
