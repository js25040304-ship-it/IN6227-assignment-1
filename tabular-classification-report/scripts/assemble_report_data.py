#!/usr/bin/env python3

"""Assemble a compact, traceable report-data object from a completed model run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from verify_run import verify_run_directory


SCHEMA_VERSION = "1.0"
REQUIRED_FILES = (
    "run_manifest.json",
    "data_profile.json",
    "decision_log.json",
    "cv_results.csv",
    "model_comparison.csv",
    "test_metrics.json",
    "predictions.csv",
    "predictions_all_models.csv",
    "fold_assignments.csv",
    "verification.json",
)


class AssemblyError(ValueError):
    """Raised when a run cannot support a trustworthy report."""


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssemblyError(f"Could not read valid JSON from {path}: {exc}") from exc


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        raise AssemblyError(f"Could not read {path}: {exc}") from exc


def number(value: Any) -> float | int | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise AssemblyError(f"Invalid numeric value in a run table: {value!r}") from exc
    if not math.isfinite(parsed):
        return None
    return int(parsed) if parsed.is_integer() else parsed


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def json_cell(value: str | None, fallback: str) -> Any:
    try:
        return json.loads(value or fallback)
    except json.JSONDecodeError as exc:
        raise AssemblyError(f"Invalid JSON value in a run table: {value!r}") from exc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def type_counts(split: dict[str, Any], target: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for column, semantic_type in split.get("column_types", {}).items():
        if column == target:
            continue
        counts[semantic_type] = counts.get(semantic_type, 0) + 1
    return dict(sorted(counts.items()))


def split_summary(profile: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    reconciliation = manifest.get("row_reconciliation", {})
    for role, split in profile.get("splits", {}).items():
        target = split.get("target") or {}
        numeric_outliers = {
            column: int(values.get("iqr_outlier_count", 0))
            for column, values in (split.get("numeric_summary") or {}).items()
            if column != manifest["target"] and int(values.get("iqr_outlier_count", 0)) > 0
        }
        summaries[role] = {
            "source_rows": split.get("shape", {}).get("rows"),
            "source_columns": split.get("shape", {}).get("columns"),
            "usable_labelled_rows": reconciliation.get(role, {}).get(
                "usable_labelled_rows", target.get("observed")
            ),
            "missing_target_rows": reconciliation.get(role, {}).get(
                "missing_target_rows", target.get("missing")
            ),
            "rows_with_any_missing": split.get("rows_with_any_missing"),
            "exact_duplicate_rows": split.get("exact_duplicate_rows"),
            "predictor_type_counts": type_counts(split, manifest["target"]),
            "class_distribution": target.get("classes", []),
            "iqr_outlier_counts": numeric_outliers,
            "iqr_flagged_value_count": sum(numeric_outliers.values()),
        }
    return summaries


def metric_subset(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "evaluated_rows",
        "accuracy",
        "balanced_accuracy",
        "macro_precision",
        "macro_recall",
        "macro_f1",
        "weighted_precision",
        "weighted_recall",
        "weighted_f1",
        "roc_auc",
        "roc_auc_ovr_weighted",
        "average_precision",
        "per_class",
        "confusion_matrix",
    )
    return {key: metrics.get(key) for key in keys if key in metrics}


def comparison_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        result.append(
            {
                "feature_set": row.get("feature_set"),
                "model": row.get("model"),
                "selected_parameters": json_cell(row.get("selected_parameters"), "{}"),
                "selected_model": truthy(row.get("selected_model")),
                "development": {
                    "macro_f1_mean": number(row.get("development_macro_f1_mean")),
                    "macro_f1_std": number(row.get("development_macro_f1_std")),
                    "balanced_accuracy_mean": number(row.get("development_balanced_accuracy_mean")),
                    "accuracy_mean": number(row.get("development_accuracy_mean")),
                    "positive_f1_mean": number(row.get("development_positive_f1_mean")),
                    "positive_recall_mean": number(row.get("development_positive_recall_mean")),
                    "roc_auc_mean": number(row.get("development_roc_auc_mean")),
                    "average_precision_mean": number(row.get("development_average_precision_mean")),
                },
            }
        )
    return result


def sensitivity_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for row in read_csv(path):
        rows.append(
            {
                "model": row.get("model"),
                "excluded_columns": json_cell(row.get("excluded_columns"), "[]"),
                "full_macro_f1_mean": number(row.get("full_macro_f1_mean")),
                "without_macro_f1_mean": number(row.get("without_macro_f1_mean")),
                "delta_without_minus_full": number(row.get("delta_without_minus_full")),
            }
        )
    return rows


def search_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    by_model: dict[str, dict[str, Any]] = {}
    for row in rows:
        model = row.get("model")
        if not model or model.startswith("dummy"):
            continue
        entry = by_model.setdefault(model, {"feature_sets": {}, "parameter_values": {}})
        feature_set = row.get("feature_set") or "unspecified"
        entry["feature_sets"][feature_set] = entry["feature_sets"].get(feature_set, 0) + 1
        parameters = json_cell(row.get("parameters"), "{}")
        if not isinstance(parameters, dict):
            raise AssemblyError("Each CV parameters cell must contain a JSON object")
        for key, value in parameters.items():
            values = entry["parameter_values"].setdefault(key, [])
            if value not in values:
                values.append(value)
    for entry in by_model.values():
        for key, values in entry["parameter_values"].items():
            entry["parameter_values"][key] = sorted(values, key=lambda value: json.dumps(value))
    return by_model


def assemble(run_dir: Path) -> dict[str, Any]:
    missing = [name for name in REQUIRED_FILES if not (run_dir / name).is_file()]
    if missing:
        raise AssemblyError(f"Missing required run artifacts: {', '.join(missing)}")

    manifest = read_json(run_dir / "run_manifest.json")
    profile = read_json(run_dir / "data_profile.json")
    decisions = read_json(run_dir / "decision_log.json")
    metrics = read_json(run_dir / "test_metrics.json")
    verification = read_json(run_dir / "verification.json")

    if manifest.get("status") not in {"modelled", "reported", "verified"}:
        raise AssemblyError(f"Run status {manifest.get('status')!r} is not reportable")
    if manifest.get("errors"):
        raise AssemblyError("Run contains unresolved errors")
    if verification.get("all_checks_passed") is not True:
        raise AssemblyError("Independent run verification did not pass")
    checks = verification.get("checks")
    if not isinstance(checks, dict) or not checks or not all(value is True for value in checks.values()):
        raise AssemblyError("Verification summary conflicts with one or more individual checks")
    if manifest.get("run_id") != metrics.get("run_id") or manifest.get("run_id") != profile.get("run_id"):
        raise AssemblyError("Run IDs disagree across source artifacts")

    modelling = manifest.get("modelling") or {}
    if modelling.get("test_labels_used_for_feature_or_model_selection") is not False:
        raise AssemblyError("Final-test isolation is not explicitly confirmed")
    selected_model = modelling.get("selected_model") or metrics.get("selected_model")
    model_metrics = metrics.get("models", {})
    if not selected_model or selected_model not in model_metrics:
        raise AssemblyError("Selected model is missing from final metrics")
    if metrics.get("selected_model") != selected_model:
        raise AssemblyError("Selected model disagrees between manifest and final metrics")
    if verification.get("run_id") not in {None, manifest.get("run_id")}:
        raise AssemblyError("Verification belongs to a different run")
    if verification.get("model") not in {None, selected_model}:
        raise AssemblyError("Verification covers a different model")

    live_verification = verify_run_directory(run_dir)
    if verification.get("input_sha256") != live_verification.get("input_sha256"):
        raise AssemblyError("Run evidence changed after verification")
    if live_verification.get("all_checks_passed") is not True:
        raise AssemblyError("Live independent verification did not pass")
    if set(live_verification.get("models", [])) != set(model_metrics):
        raise AssemblyError("Verification does not cover every reported model")

    comparison = comparison_rows(read_csv(run_dir / "model_comparison.csv"))
    cv_rows = read_csv(run_dir / "cv_results.csv")
    selected_rows = [row for row in comparison if row["selected_model"]]
    if len(selected_rows) != 1 or selected_rows[0]["model"] != selected_model:
        raise AssemblyError("Model comparison must identify exactly the manifest-selected model")

    warnings = manifest.get("warnings", [])
    unresolved = []
    resolutions = modelling.get("warning_resolutions", {})
    for warning in warnings:
        code = warning.get("code")
        if code == "SUSPICIOUS_AGGREGATE" and code not in resolutions:
            unresolved.append(code)
    if unresolved:
        raise AssemblyError(f"Report-critical warnings are unresolved: {', '.join(sorted(set(unresolved)))}")

    now = datetime.now(ZoneInfo("Asia/Singapore")).isoformat()
    selected_final = metric_subset(model_metrics[selected_model])
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": manifest["run_id"],
        "assembled_at": now,
        "source_evidence": {
            "dataset_sha256": manifest.get("dataset", {}).get("sha256"),
            "model_run_skill_sha256": manifest.get("skill_sha256"),
            "assembler_sha256": sha256(Path(__file__).resolve()),
            "artifact_sha256": {
                name: sha256(run_dir / name) for name in REQUIRED_FILES
            }
            | ({"sensitivity_results.csv": sha256(run_dir / "sensitivity_results.csv")} if (run_dir / "sensitivity_results.csv").is_file() else {}),
            "automatic_verification_passed": True,
            "verification_checks": verification.get("checks", {}),
        },
        "task": {
            "target": manifest["target"],
            "target_resolution": manifest.get("target_resolution"),
            "type": manifest.get("task_type"),
            "labels": manifest.get("labels", []),
            "positive_label": manifest.get("positive_label"),
        },
        "dataset": {
            "splits": split_summary(profile, manifest),
            "cross_split_checks": profile.get("cross_split", {}),
        },
        "quality_findings": {
            "warnings": warnings,
            "warning_resolutions": resolutions,
            "suspicious_aggregate_sensitivity": sensitivity_rows(run_dir / "sensitivity_results.csv"),
        },
        "method": {
            "preprocessing": {
                "policy": "Fold-local imputation and categorical encoding; numeric scaling for logistic regression and no scaling for random forest",
                "encoding_policy": modelling.get("encoding_policy", {}),
                "selected_features": modelling.get("selected_features", []),
                "excluded_features": sorted(
                    set(modelling.get("base_exclusions", []))
                    | (
                        set(modelling.get("suspicious_aggregates", []))
                        if modelling.get("aggregate_policy") == "drop"
                        else set()
                    )
                ),
                "selected_feature_set": modelling.get("selected_feature_set"),
            },
            "validation": {
                "split_strategy": modelling.get("split_strategy"),
                "splitter": modelling.get("splitter"),
                "folds": modelling.get("folds"),
                "primary_metric": modelling.get("primary_metric"),
                "random_seed": manifest.get("random_seed"),
                "final_test_used_for_selection": modelling.get("test_labels_used_for_feature_or_model_selection"),
            },
            "models": modelling.get("models", []),
            "model_selection_rationale": modelling.get("model_selection_rationale"),
            "selection_basis": modelling.get("selection_basis"),
            "selection_diagnostics": modelling.get("selection_diagnostics", {}),
            "tuning": {
                "search": search_summary(cv_rows),
                "stopping_rule": "Evaluate the finite predefined grid once with the fixed folds; do not expand it after inspecting final-test results",
            },
            "selected_model": selected_model,
            "selected_parameters": modelling.get("selected_parameters", {}),
        },
        "results": {
            "development_comparison": comparison,
            "final_metrics_by_model": {
                name: metric_subset(values) for name, values in model_metrics.items()
            },
            "selected_model": selected_model,
            "selected_final_metrics": selected_final,
        },
        "reproducibility": {
            "runtime_versions": manifest.get("runtime_versions", {}),
            "decision_ids": [item.get("id") for item in decisions],
            "source_artifacts": {name: name for name in REQUIRED_FILES},
        },
    }


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="Completed immutable RUN-NNN directory")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output path; defaults to <run-dir>/report/report_data.json",
    )
    args = parser.parse_args()
    output = args.output or args.run_dir / "report" / "report_data.json"
    try:
        payload = assemble(args.run_dir.resolve())
        atomic_write_json(output.resolve(), payload)
    except AssemblyError as exc:
        print(f"Report-data assembly failed: {exc}")
        return 2
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
