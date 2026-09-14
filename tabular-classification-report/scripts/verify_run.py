#!/usr/bin/env python3
"""Independently verify saved classification metrics from saved predictions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score


def safe_label(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", label)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def recompute_metrics(predictions: pd.DataFrame, labels: list[str], positive_label: str | None) -> dict[str, Any]:
    valid = predictions.loc[predictions["true_label"].notna()].copy()
    true = valid["true_label"].astype(str)
    predicted = valid["predicted_label"].astype(str)
    matrix = np.array(
        [[int(((true == actual) & (predicted == guessed)).sum()) for guessed in labels] for actual in labels],
        dtype=int,
    )
    support = matrix.sum(axis=1)
    predicted_counts = matrix.sum(axis=0)
    precision = np.divide(
        np.diag(matrix), predicted_counts, out=np.zeros(len(labels), dtype=float), where=predicted_counts != 0
    )
    recall = np.divide(np.diag(matrix), support, out=np.zeros(len(labels), dtype=float), where=support != 0)
    f1 = np.divide(
        2 * precision * recall,
        precision + recall,
        out=np.zeros(len(labels), dtype=float),
        where=(precision + recall) != 0,
    )
    result: dict[str, Any] = {
        "evaluated_rows": int(matrix.sum()),
        "accuracy": float(np.trace(matrix) / matrix.sum()),
        "balanced_accuracy": float(recall.mean()),
        "macro_precision": float(precision.mean()),
        "macro_recall": float(recall.mean()),
        "macro_f1": float(f1.mean()),
        "weighted_precision": float(np.average(precision, weights=support)),
        "weighted_recall": float(np.average(recall, weights=support)),
        "weighted_f1": float(np.average(f1, weights=support)),
        "confusion_matrix": {"labels": labels, "values": matrix.tolist()},
    }
    score_columns = [f"score__{safe_label(label)}" for label in labels]
    if all(column in valid.columns for column in score_columns):
        probabilities = valid[score_columns].to_numpy(dtype=float)
        if len(labels) == 2 and positive_label in labels:
            positive_index = labels.index(positive_label)
            binary_true = (true == positive_label).astype(int)
            result["roc_auc"] = float(roc_auc_score(binary_true, probabilities[:, positive_index]))
            result["average_precision"] = float(
                average_precision_score(binary_true, probabilities[:, positive_index])
            )
        elif len(labels) > 2:
            result["roc_auc_ovr_weighted"] = float(
                roc_auc_score(true, probabilities, labels=labels, multi_class="ovr", average="weighted")
            )
    return result


def verify_run_directory(run_dir: Path, tolerance: float = 1e-12) -> dict[str, Any]:
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    predictions = pd.read_csv(run_dir / "predictions.csv")
    all_predictions = pd.read_csv(run_dir / "predictions_all_models.csv")
    selected_model = manifest["modelling"]["selected_model"]
    expected_models = [str(value) for value in manifest["modelling"]["models"]]
    final_rows = int(manifest["modelling"]["final_rows"])
    labelled_rows = int(manifest["modelling"].get("labelled_final_rows", 0))
    labels = [str(value) for value in manifest.get("labels", [])]
    checks: dict[str, bool] = {}
    recomputed_by_model: dict[str, Any] = {}
    checks["selected_prediction_rows"] = len(predictions) == final_rows
    checks["selected_model_column"] = set(predictions["model"].astype(str)) == {selected_model}
    checks["all_model_set"] = set(all_predictions["model"].astype(str)) == set(expected_models)
    for model in expected_models:
        model_rows = all_predictions.loc[all_predictions["model"].astype(str) == model].copy()
        checks[f"{model}.prediction_rows"] = len(model_rows) == final_rows
        checks[f"{model}.predicted_labels_known"] = set(model_rows["predicted_label"].astype(str)) <= set(labels)
        score_columns = [f"score__{safe_label(label)}" for label in labels]
        if all(column in model_rows.columns for column in score_columns):
            scores = model_rows[score_columns].to_numpy(dtype=float)
            checks[f"{model}.scores_finite"] = bool(np.isfinite(scores).all())
            checks[f"{model}.scores_sum_to_one"] = bool(np.allclose(scores.sum(axis=1), 1.0, atol=tolerance))

    selected_all = all_predictions.loc[all_predictions["model"].astype(str) == selected_model].reset_index(drop=True)
    selected_saved = predictions.reset_index(drop=True)
    shared_columns = [column for column in selected_saved.columns if column in selected_all.columns]
    checks["selected_predictions_match_all_models"] = (
        len(selected_all) == len(selected_saved)
        and selected_saved[shared_columns].fillna("<NA>").astype(str).equals(
            selected_all[shared_columns].fillna("<NA>").astype(str)
        )
    )

    metrics_path = run_dir / "test_metrics.json"
    if metrics_path.is_file():
        saved_document = json.loads(metrics_path.read_text())
        checks["selected_model_matches_metrics"] = saved_document.get("selected_model") == selected_model
        checks["metrics_model_set"] = set(saved_document.get("models", {})) == set(expected_models)
        for model, saved in saved_document.get("models", {}).items():
            model_rows = all_predictions.loc[all_predictions["model"].astype(str) == model]
            model_labels = [str(value) for value in saved["confusion_matrix"]["labels"]]
            recomputed = recompute_metrics(model_rows, model_labels, manifest.get("positive_label"))
            recomputed_by_model[model] = recomputed
            for key, value in recomputed.items():
                check_name = f"{model}.{key}"
                if key == "confusion_matrix":
                    checks[check_name] = value == saved.get(key)
                elif isinstance(value, (int, float)):
                    checks[check_name] = key in saved and abs(float(value) - float(saved[key])) <= tolerance
            checks[f"{model}.evaluated_rows"] = recomputed["evaluated_rows"] == labelled_rows
        mode = "labelled-evaluation"
    else:
        checks["no_labelled_rows_declared"] = labelled_rows == 0
        checks["true_labels_absent"] = bool(
            predictions["true_label"].isna().all() and all_predictions["true_label"].isna().all()
        )
        mode = "predictions-only"

    hashed_files = ["predictions.csv", "predictions_all_models.csv"]
    if metrics_path.is_file():
        hashed_files.append("test_metrics.json")
    return {
        "schema_version": "1.1",
        "run_id": manifest["run_id"],
        "mode": mode,
        "method": "Independent recomputation for every saved model from predictions_all_models.csv; selected predictions are cross-checked separately.",
        "model": selected_model,
        "models": expected_models,
        "tolerance": tolerance,
        "recomputed": recomputed_by_model,
        "input_sha256": {name: sha256_file(run_dir / name) for name in hashed_files},
        "checks": checks,
        "all_checks_passed": bool(checks) and all(checks.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tolerance", type=float, default=1e-12)
    args = parser.parse_args()
    try:
        result = verify_run_directory(args.run_dir.resolve(), args.tolerance)
        if args.output:
            args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["all_checks_passed"] else 3
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
