#!/usr/bin/env python3
"""Profile, tune, compare, and evaluate tabular classifiers without test leakage."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.exceptions import ConvergenceWarning
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from profile_data import build_run, discover_sources, load_source, resolve_run_destination, write_json
from verify_run import verify_run_directory


class ModellingError(RuntimeError):
    """Raised when a profiled dataset cannot be modelled safely."""


class DateTimeFeatures(BaseEstimator, TransformerMixin):
    """Convert datetime-like columns into deterministic calendar components."""

    def fit(self, X: Any, y: Any = None) -> "DateTimeFeatures":
        return self

    def transform(self, X: Any) -> np.ndarray:
        frame = X if isinstance(X, pd.DataFrame) else pd.DataFrame(X)
        blocks = []
        for column in frame.columns:
            try:
                parsed = pd.to_datetime(frame[column].astype("string"), errors="coerce", format="mixed")
            except TypeError:
                parsed = pd.to_datetime(frame[column].astype("string"), errors="coerce")
            blocks.extend(
                [
                    parsed.dt.year.to_numpy(dtype=float, na_value=np.nan),
                    parsed.dt.month.to_numpy(dtype=float, na_value=np.nan),
                    parsed.dt.day.to_numpy(dtype=float, na_value=np.nan),
                    parsed.dt.dayofweek.to_numpy(dtype=float, na_value=np.nan),
                ]
            )
        return np.column_stack(blocks) if blocks else np.empty((len(frame), 0), dtype=float)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_path", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--target")
    parser.add_argument("--sheet")
    parser.add_argument("--positive-label")
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--exclude-column", action="append", default=[])
    parser.add_argument("--aggregate-policy", choices=("checkpoint", "keep", "drop"), default="checkpoint")
    parser.add_argument("--dependency-policy", choices=("checkpoint", "independent"), default="checkpoint")
    parser.add_argument("--source-profile-run")
    parser.add_argument("--group-column")
    parser.add_argument("--time-column")
    parser.add_argument("--n-jobs", type=int, default=1)
    parser.add_argument("--smoke", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def load_frames(dataset_path: Path, sheet: str | None) -> dict[str, pd.DataFrame]:
    sources, _ = discover_sources(dataset_path)
    frames = {}
    for source in sources:
        frame, _ = load_source(source, sheet)
        frame.columns = [str(column) for column in frame.columns]
        frames[source["role"]] = frame
    return frames


def resolve_development_and_test(
    frames: dict[str, pd.DataFrame], target: str, seed: int
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series | None, pd.Series, str]:
    train = frames["train"].copy()
    labelled_train = train.loc[train[target].notna()].copy()
    y_all = labelled_train[target].astype(str)
    X_all = labelled_train.drop(columns=[target])

    if "test" in frames:
        test = frames["test"].copy()
        y_test = test[target].astype("string") if target in test.columns else None
        X_test = test.drop(columns=[target], errors="ignore")
        row_refs = pd.Series(test.index.to_numpy(), index=test.index, name="source_row_index")
        return X_all, y_all, X_test, y_test, row_refs, "supplied-test"

    dev_indices, test_indices = train_test_split(
        np.arange(len(X_all)),
        test_size=0.2,
        random_state=seed,
        stratify=y_all,
    )
    X_dev = X_all.iloc[dev_indices].copy()
    y_dev = y_all.iloc[dev_indices].copy()
    X_test = X_all.iloc[test_indices].copy()
    y_test = y_all.iloc[test_indices].astype("string")
    row_refs = pd.Series(labelled_train.index.to_numpy()[test_indices], index=X_test.index, name="source_row_index")
    return X_dev, y_dev, X_test, y_test, row_refs, "stratified-20%-holdout"


def make_preprocessor(column_types: dict[str, str], features: list[str], scale_numeric: bool) -> ColumnTransformer:
    numeric = [column for column in features if column_types.get(column) == "numeric"]
    categorical = [column for column in features if column_types.get(column) in {"categorical", "boolean"}]
    datetimes = [column for column in features if column_types.get(column) == "datetime"]
    transformers = []
    if numeric:
        numeric_steps: list[tuple[str, Any]] = [("impute", SimpleImputer(strategy="median"))]
        if scale_numeric:
            numeric_steps.append(("scale", StandardScaler()))
        transformers.append(("numeric", Pipeline(numeric_steps), numeric))
    if categorical:
        transformers.append(
            (
                "categorical",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        (
                            "encode",
                            OneHotEncoder(
                                handle_unknown="infrequent_if_exist",
                                min_frequency=2,
                                max_categories=100,
                            ),
                        ),
                    ]
                ),
                categorical,
            )
        )
    if datetimes:
        transformers.append(
            (
                "datetime",
                Pipeline(
                    [
                        ("derive", DateTimeFeatures()),
                        ("impute", SimpleImputer(strategy="median")),
                        ("scale", StandardScaler() if scale_numeric else "passthrough"),
                    ]
                ),
                datetimes,
            )
        )
    if not transformers:
        raise ModellingError("No supported predictors remain after exclusions.")
    return ColumnTransformer(transformers=transformers, remainder="drop")


def scorers(task_type: str, positive_label: str | None) -> dict[str, Any]:
    scoring: dict[str, Any] = {
        "macro_f1": "f1_macro",
        "balanced_accuracy": "balanced_accuracy",
        "accuracy": "accuracy",
    }
    if task_type == "binary" and positive_label:
        def positive_f1(estimator: Any, X: Any, y: Any) -> float:
            return float(f1_score(y, estimator.predict(X), pos_label=positive_label, zero_division=0))

        def positive_recall(estimator: Any, X: Any, y: Any) -> float:
            labels = [positive_label]
            return float(precision_recall_fscore_support(y, estimator.predict(X), labels=labels, zero_division=0)[1][0])

        def binary_auc(estimator: Any, X: Any, y: Any) -> float:
            probabilities = estimator.predict_proba(X)
            classes = list(estimator.classes_)
            scores = probabilities[:, classes.index(positive_label)]
            return float(roc_auc_score((pd.Series(y).astype(str) == positive_label).astype(int), scores))

        def average_precision(estimator: Any, X: Any, y: Any) -> float:
            probabilities = estimator.predict_proba(X)
            classes = list(estimator.classes_)
            scores = probabilities[:, classes.index(positive_label)]
            return float(average_precision_score((pd.Series(y).astype(str) == positive_label).astype(int), scores))

        scoring.update(
            {
                "positive_f1": positive_f1,
                "positive_recall": positive_recall,
                "roc_auc": binary_auc,
                "average_precision": average_precision,
            }
        )
    return scoring


def model_spaces(seed: int, smoke: bool) -> dict[str, tuple[Pipeline, list[dict[str, list[Any]]]]]:
    logistic = Pipeline(
        [
            ("preprocess", "passthrough"),
            ("model", LogisticRegression(max_iter=5000, solver="lbfgs", random_state=seed)),
        ]
    )
    forest = Pipeline(
        [
            ("preprocess", "passthrough"),
            ("model", RandomForestClassifier(random_state=seed, n_jobs=1)),
        ]
    )
    boosting = Pipeline(
        [
            ("preprocess", "passthrough"),
            ("model", HistGradientBoostingClassifier(random_state=seed)),
        ]
    )
    if smoke:
        logistic_grid = [{"model__C": [1.0], "model__class_weight": [None]}]
        forest_grid = [
            {
                "model__n_estimators": [10],
                "model__max_depth": [6],
                "model__min_samples_leaf": [1],
                "model__max_features": ["sqrt"],
                "model__class_weight": [None],
            }
        ]
        boosting_grid = [
            {
                "model__learning_rate": [0.1],
                "model__max_iter": [30],
                "model__max_leaf_nodes": [15],
                "model__l2_regularization": [0.0],
            }
        ]
    else:
        logistic_grid = [{"model__C": [0.1, 1.0], "model__class_weight": [None, "balanced"]}]
        forest_grid = [
            {
                "model__n_estimators": [160],
                "model__max_depth": [None],
                "model__min_samples_leaf": [1],
                "model__max_features": ["sqrt"],
                "model__class_weight": [None],
            },
            {
                "model__n_estimators": [160],
                "model__max_depth": [None],
                "model__min_samples_leaf": [3],
                "model__max_features": ["sqrt"],
                "model__class_weight": ["balanced_subsample"],
            },
            {
                "model__n_estimators": [160],
                "model__max_depth": [18],
                "model__min_samples_leaf": [1],
                "model__max_features": ["sqrt"],
                "model__class_weight": [None],
            },
            {
                "model__n_estimators": [160],
                "model__max_depth": [18],
                "model__min_samples_leaf": [3],
                "model__max_features": ["sqrt"],
                "model__class_weight": ["balanced_subsample"],
            },
        ]
        boosting_grid = [
            {
                "model__learning_rate": [0.05, 0.1],
                "model__max_iter": [120],
                "model__max_leaf_nodes": [15, 31],
                "model__l2_regularization": [0.0, 1.0],
            }
        ]
    return {
        "logistic_regression": (logistic, logistic_grid),
        "random_forest": (forest, forest_grid),
        "hist_gradient_boosting": (boosting, boosting_grid),
    }


def serializable_params(params: dict[str, Any]) -> str:
    return json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)


def tune_models(
    X: pd.DataFrame,
    y: pd.Series,
    feature_sets: dict[str, list[str]],
    column_types: dict[str, str],
    folds: list[tuple[np.ndarray, np.ndarray]],
    scoring: dict[str, Any],
    seed: int,
    n_jobs: int,
    smoke: bool,
    candidate_models: list[str],
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]], list[dict[str, str]]]:
    rows: list[dict[str, Any]] = []
    best: dict[tuple[str, str], dict[str, Any]] = {}
    model_warnings: list[dict[str, str]] = []
    for feature_set_name, features in feature_sets.items():
        spaces = model_spaces(seed, smoke)
        for model_name in candidate_models:
            pipeline, grid = spaces[model_name]
            pipeline.set_params(
                preprocess=make_preprocessor(
                    column_types,
                    features,
                    scale_numeric=model_name == "logistic_regression",
                )
            )
            search = GridSearchCV(
                pipeline,
                grid,
                scoring=scoring,
                refit="macro_f1",
                cv=folds,
                n_jobs=n_jobs,
                return_train_score=False,
                error_score="raise",
            )
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                search.fit(X[features], y)
            for warning in caught:
                item = {
                    "feature_set": feature_set_name,
                    "model": model_name,
                    "category": warning.category.__name__,
                    "message": str(warning.message),
                }
                if item not in model_warnings:
                    model_warnings.append(item)
                if issubclass(warning.category, ConvergenceWarning):
                    raise ModellingError(
                        f"{model_name} still failed to converge after the bounded max_iter=5000 retry limit."
                    )
            results = search.cv_results_
            metric_names = list(scoring)
            for index, params in enumerate(results["params"]):
                row: dict[str, Any] = {
                    "feature_set": feature_set_name,
                    "model": model_name,
                    "parameters": serializable_params(params),
                    "rank_macro_f1": int(results["rank_test_macro_f1"][index]),
                }
                for metric in metric_names:
                    row[f"mean_{metric}"] = float(results[f"mean_test_{metric}"][index])
                    row[f"std_{metric}"] = float(results[f"std_test_{metric}"][index])
                row["fold_macro_f1"] = json.dumps(
                    [float(results[f"split{fold}_test_macro_f1"][index]) for fold in range(len(folds))]
                )
                rows.append(row)
            best_index = int(search.best_index_)
            best[(feature_set_name, model_name)] = {
                "estimator": search.best_estimator_,
                "parameters": search.best_params_,
                "mean_macro_f1": float(results["mean_test_macro_f1"][best_index]),
                "std_macro_f1": float(results["std_test_macro_f1"][best_index]),
                "metrics": {
                    metric: {
                        "mean": float(results[f"mean_test_{metric}"][best_index]),
                        "std": float(results[f"std_test_{metric}"][best_index]),
                    }
                    for metric in metric_names
                },
                "fold_macro_f1": [
                    float(results[f"split{fold}_test_macro_f1"][best_index]) for fold in range(len(folds))
                ],
            }
    return rows, best, model_warnings


def evaluate_predictions(
    y_true: pd.Series,
    predicted: np.ndarray,
    probabilities: np.ndarray | None,
    classes: list[str],
    task_type: str,
    positive_label: str | None,
) -> dict[str, Any]:
    y_values = y_true.astype(str).to_numpy()
    precision, recall, f1, support = precision_recall_fscore_support(
        y_values, predicted, labels=classes, zero_division=0
    )
    result: dict[str, Any] = {
        "evaluated_rows": int(len(y_values)),
        "accuracy": float(accuracy_score(y_values, predicted)),
        "balanced_accuracy": float(balanced_accuracy_score(y_values, predicted)),
        "macro_precision": float(np.mean(precision)),
        "macro_recall": float(np.mean(recall)),
        "macro_f1": float(f1_score(y_values, predicted, average="macro", zero_division=0)),
        "weighted_precision": float(np.average(precision, weights=support)),
        "weighted_recall": float(np.average(recall, weights=support)),
        "weighted_f1": float(f1_score(y_values, predicted, average="weighted", zero_division=0)),
        "per_class": {
            label: {
                "precision": float(precision[index]),
                "recall": float(recall[index]),
                "f1": float(f1[index]),
                "support": int(support[index]),
            }
            for index, label in enumerate(classes)
        },
        "confusion_matrix": {
            "labels": classes,
            "values": confusion_matrix(y_values, predicted, labels=classes).astype(int).tolist(),
        },
    }
    if probabilities is not None:
        try:
            if task_type == "binary" and positive_label:
                positive_index = classes.index(positive_label)
                binary_true = (y_values == positive_label).astype(int)
                result["roc_auc"] = float(roc_auc_score(binary_true, probabilities[:, positive_index]))
                result["average_precision"] = float(
                    average_precision_score(binary_true, probabilities[:, positive_index])
                )
            elif task_type == "multiclass":
                result["roc_auc_ovr_weighted"] = float(
                    roc_auc_score(y_values, probabilities, labels=classes, multi_class="ovr", average="weighted")
                )
        except ValueError as exc:
            result["probability_metric_warning"] = str(exc)
    return result


def select_candidate_models(column_types: dict[str, str], features: list[str]) -> tuple[list[str], str]:
    categorical = sum(column_types.get(column) in {"categorical", "boolean"} for column in features)
    if categorical == 0:
        candidates = ["logistic_regression", "hist_gradient_boosting"]
        rationale = (
            "The usable predictors are numeric or datetime-derived, so hist_gradient_boosting is the nonlinear "
            "challenger to logistic_regression; this avoids sparse one-hot constraints while testing thresholds and interactions."
        )
    else:
        candidates = ["logistic_regression", "random_forest"]
        rationale = (
            "The usable predictors include categorical variables, so random_forest is the nonlinear challenger to "
            "logistic_regression and can test interactions after bounded one-hot encoding."
        )
    return candidates, rationale


def model_rationale(profile: dict[str, Any], candidates: list[str], selection_reason: str) -> str:
    train = profile["splits"]["train"]
    types = [train["column_types"][column] for column in train["predictors"]]
    numeric = sum(value == "numeric" for value in types)
    categorical = sum(value in {"categorical", "boolean"} for value in types)
    return (
        f"The development data contain {numeric} numeric and {categorical} categorical predictors. "
        f"{selection_reason} The controlled candidates are {', '.join(candidates)} and are compared with a dummy baseline."
    )


def choose_model(candidates: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    reference_name = "logistic_regression"
    challenger_name = next(name for name in candidates if name != reference_name)
    reference = candidates[reference_name]
    challenger = candidates[challenger_name]
    differences = np.asarray(challenger["fold_macro_f1"]) - np.asarray(reference["fold_macro_f1"])
    mean_difference = float(differences.mean())
    standard_deviation = float(differences.std(ddof=1)) if len(differences) > 1 else 0.0
    standard_error = float(standard_deviation / np.sqrt(len(differences))) if len(differences) else 0.0
    practical_tie = abs(mean_difference) <= standard_error
    if practical_tie:
        selected = min(
            candidates,
            key=lambda name: (
                candidates[name]["std_macro_f1"],
                name != reference_name,
            ),
        )
        rule = "paired difference within one standard error; prefer stability, then logistic simplicity"
    else:
        selected = challenger_name if mean_difference > 0 else reference_name
        rule = "paired mean difference exceeded one standard error"
    return selected, {
        "reference_model": reference_name,
        "challenger_model": challenger_name,
        "paired_fold_macro_f1_difference_challenger_minus_reference": differences.tolist(),
        "mean_difference": mean_difference,
        "standard_deviation": standard_deviation,
        "standard_error": standard_error,
        "challenger_fold_wins": int((differences > 0).sum()),
        "practical_tie": practical_tie,
        "rule": rule,
    }


def validate_parent_run(parent: str | None, runs_root: Path, dataset_sha256: str) -> dict[str, Any] | None:
    if not parent:
        return None
    parent_path = Path(parent)
    if not parent_path.is_absolute():
        parent_path = runs_root / parent
    manifest_path = parent_path / "run_manifest.json"
    if not manifest_path.is_file():
        raise ModellingError(f"Parent run manifest was not found: {manifest_path}")
    parent_manifest = json.loads(manifest_path.read_text())
    parent_sha = parent_manifest.get("dataset", {}).get("sha256")
    if parent_sha != dataset_sha256:
        raise ModellingError("Parent run dataset fingerprint does not match the current dataset.")
    return {
        "run_id": parent_manifest.get("run_id"),
        "status": parent_manifest.get("status"),
        "dataset_sha256": parent_sha,
        "skill_sha256": parent_manifest.get("skill_sha256"),
    }


def write_failed_run(destination: Path, args: argparse.Namespace, error: Exception) -> None:
    if destination.exists():
        return
    manifest, profile, decisions = build_run(args)
    manifest["status"] = "failed"
    failure = {
        "code": "MODELLING_STAGE_FAILED",
        "severity": "blocking",
        "message": str(error),
    }
    manifest["errors"].append(failure)
    manifest["artifacts"]["failure"] = "failure.json"
    decisions.append(
        {
            "id": "DMOD-FAIL",
            "timestamp": datetime.now().astimezone().isoformat(),
            "stage": "modelling",
            "decision": "Stop and retain diagnostics",
            "reason": str(error),
            "evidence": [failure],
            "mode": "automatic",
        }
    )
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        write_partial_run(staging, manifest, profile, decisions)
        write_json(staging / "failure.json", failure)
        os.replace(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def write_partial_run(
    staging: Path,
    manifest: dict[str, Any],
    profile: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> None:
    write_json(staging / "data_profile.json", profile)
    write_json(staging / "decision_log.json", decisions)
    write_json(staging / "run_manifest.json", manifest)


def run(args: argparse.Namespace, destination: Path) -> int:
    started_clock = time.perf_counter()
    manifest, profile, decisions = build_run(args)
    if manifest["status"] != "profiled":
        staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
        try:
            write_partial_run(staging, manifest, profile, decisions)
            os.replace(staging, destination)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return 3

    if args.group_column or args.time_column:
        raise ModellingError(
            "Grouped or ordered validation is outside v1; random stratification was refused for the supplied dependency control."
        )
    parent_evidence = validate_parent_run(
        args.source_profile_run,
        destination.parent,
        manifest["dataset"]["sha256"],
    )
    dependency_candidates = profile["splits"]["train"].get("dependency_candidates", [])
    if dependency_candidates and args.dependency_policy == "checkpoint":
        checkpoint = {
            "code": "DEPENDENCY_STRUCTURE_CONFIRMATION",
            "severity": "blocking",
            "message": (
                "Confirm that rows are independent before shuffled stratified cross-validation. "
                "If they are not, supply --group-column or --time-column; this v1 workflow will refuse unsafe random validation."
            ),
            "candidates": dependency_candidates,
        }
        manifest["status"] = "needs_input"
        manifest["human_checkpoints"].append(checkpoint)
        manifest["parent_profile_run"] = args.source_profile_run
        manifest["parent_run_evidence"] = parent_evidence
        manifest["modelling"] = {
            "status": "awaiting-dependency-decision",
            "dependency_policy": args.dependency_policy,
            "dependency_candidates": dependency_candidates,
            "test_labels_used_for_feature_or_model_selection": False,
        }
        decisions.append(
            {
                "id": "DMOD-DEP-001",
                "timestamp": datetime.now().astimezone().isoformat(),
                "stage": "validation",
                "decision": "Pause before cross-validation",
                "reason": "Candidate time or group structure makes shuffled-fold independence uncertain.",
                "evidence": dependency_candidates,
                "mode": "automatic-checkpoint",
            }
        )
        staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
        try:
            write_partial_run(staging, manifest, profile, decisions)
            os.replace(staging, destination)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return 3
    frames = load_frames(args.dataset_path, args.sheet)
    target = manifest["target"]
    X_dev, y_dev, X_test, y_test, row_refs, split_strategy = resolve_development_and_test(
        frames, target, args.random_seed
    )
    train_profile = profile["splits"]["train"]
    base_exclusions = sorted(
        set(args.exclude_column)
        | set(train_profile["constant_predictors"])
        | {item["column"] for item in train_profile["identifier_candidates"]}
    )
    unknown_exclusions = sorted(set(base_exclusions) - set(X_dev.columns))
    if unknown_exclusions:
        raise ModellingError(f"Excluded columns were not found: {', '.join(unknown_exclusions)}")
    suspicious = [
        item["column"]
        for item in train_profile["suspicious_aggregate_candidates"]
        if item["column"] not in base_exclusions
    ]
    full_features = [column for column in X_dev.columns if column not in base_exclusions]
    feature_sets = {"full": full_features}
    if suspicious:
        feature_sets["without_suspicious_aggregates"] = [
            column for column in full_features if column not in suspicious
        ]
    candidate_models, candidate_selection_rationale = select_candidate_models(
        train_profile["column_types"], full_features
    )

    class_counts = y_dev.value_counts()
    fold_count = min(5, int(class_counts.min()))
    if args.smoke:
        fold_count = 2
    if fold_count < 2:
        raise ModellingError("At least one development class has fewer than two rows.")
    splitter = StratifiedKFold(n_splits=fold_count, shuffle=True, random_state=args.random_seed)
    folds = list(splitter.split(X_dev, y_dev))
    scoring = scorers(manifest["task_type"], manifest["positive_label"])

    dummy = DummyClassifier(strategy="most_frequent", random_state=args.random_seed)
    dummy_scores = cross_validate(dummy, X_dev, y_dev, cv=folds, scoring=scoring, n_jobs=args.n_jobs)
    cv_rows, best, model_warnings = tune_models(
        X_dev,
        y_dev,
        feature_sets,
        train_profile["column_types"],
        folds,
        scoring,
        args.random_seed,
        args.n_jobs,
        args.smoke,
        candidate_models,
    )
    for item in model_warnings:
        manifest["warnings"].append(
            {
                "code": "MODEL_WARNING",
                "severity": "review",
                **item,
            }
        )
    cv_rows.insert(
        0,
        {
            "feature_set": "not-applicable",
            "model": "dummy_most_frequent",
            "parameters": serializable_params({"strategy": "most_frequent"}),
            "rank_macro_f1": None,
            **{
                f"mean_{metric}": float(np.mean(dummy_scores[f"test_{metric}"]))
                for metric in scoring
            },
            **{
                f"std_{metric}": float(np.std(dummy_scores[f"test_{metric}"], ddof=0))
                for metric in scoring
            },
            "fold_macro_f1": json.dumps([float(value) for value in dummy_scores["test_macro_f1"]]),
        },
    )

    comparison_rows: list[dict[str, Any]] = [
        {
            "feature_set": "not-applicable",
            "model": "dummy_most_frequent",
            "selected_parameters": serializable_params({"strategy": "most_frequent"}),
            **{
                f"development_{metric}_{suffix}": float(np.mean(dummy_scores[f"test_{metric}"]))
                if suffix == "mean"
                else float(np.std(dummy_scores[f"test_{metric}"], ddof=0))
                for metric in scoring
                for suffix in ("mean", "std")
            },
            "selected_model": False,
        }
    ]
    for (feature_set_name, model_name), item in best.items():
        comparison_rows.append(
            {
                "feature_set": feature_set_name,
                "model": model_name,
                "selected_parameters": serializable_params(item["parameters"]),
                **{
                    f"development_{metric}_{suffix}": values[suffix]
                    for metric, values in item["metrics"].items()
                    for suffix in ("mean", "std")
                },
                "selected_model": False,
            }
        )

    sensitivity_rows = []
    if suspicious:
        for model_name in candidate_models:
            full = best[("full", model_name)]
            without = best[("without_suspicious_aggregates", model_name)]
            sensitivity_rows.append(
                {
                    "model": model_name,
                    "excluded_columns": json.dumps(suspicious),
                    "full_macro_f1_mean": full["mean_macro_f1"],
                    "full_macro_f1_std": full["std_macro_f1"],
                    "without_macro_f1_mean": without["mean_macro_f1"],
                    "without_macro_f1_std": without["std_macro_f1"],
                    "delta_without_minus_full": without["mean_macro_f1"] - full["mean_macro_f1"],
                }
            )

    now = datetime.now().astimezone().isoformat()
    manifest["parent_profile_run"] = args.source_profile_run
    manifest["parent_run_evidence"] = parent_evidence
    manifest["modelling"] = {
        "status": "development-complete",
        "split_strategy": split_strategy,
        "development_rows": int(len(X_dev)),
        "final_rows": int(len(X_test)),
        "folds": fold_count,
        "splitter": "StratifiedKFold(shuffle=True)",
        "primary_metric": "macro_f1",
        "models": ["dummy_most_frequent", *candidate_models],
        "candidate_models": candidate_models,
        "candidate_selection_rationale": candidate_selection_rationale,
        "model_selection_rationale": model_rationale(profile, candidate_models, candidate_selection_rationale),
        "base_exclusions": base_exclusions,
        "suspicious_aggregates": suspicious,
        "aggregate_policy": args.aggregate_policy,
        "dependency_policy": args.dependency_policy,
        "dependency_candidates": dependency_candidates,
        "test_labels_used_for_feature_or_model_selection": False,
        "encoding_policy": {"handle_unknown": "infrequent_if_exist", "min_frequency": 2, "max_categories": 100},
    }
    decisions.extend(
        [
            {
                "id": "DMOD-001",
                "timestamp": now,
                "stage": "validation",
                "decision": f"{fold_count}-fold shuffled stratified cross-validation",
                "reason": "All development classes support the fold count and rows are treated as independent.",
                "evidence": class_counts.astype(int).to_dict(),
                "mode": "automatic",
            },
            {
                "id": "DMOD-002",
                "timestamp": now,
                "stage": "models",
                "decision": f"Dummy baseline plus {', '.join(candidate_models)}",
                "reason": model_rationale(profile, candidate_models, candidate_selection_rationale),
                "evidence": {"candidate_models": candidate_models, "selection_rationale": candidate_selection_rationale},
                "mode": "automatic",
            },
            {
                "id": "DMOD-003",
                "timestamp": now,
                "stage": "preprocessing",
                "decision": "Fold-local imputation, encoding, scaling, and datetime derivation",
                "reason": "All learned preprocessing is contained inside each estimator pipeline.",
                "evidence": train_profile["column_types"],
                "mode": "automatic",
            },
        ]
    )
    if dependency_candidates:
        decisions.append(
            {
                "id": "DMOD-DEP-002",
                "timestamp": now,
                "stage": "validation",
                "decision": "Treat rows as independent for shuffled stratified validation",
                "reason": "Explicit --dependency-policy independent confirmation was supplied before cross-validation.",
                "evidence": dependency_candidates,
                "mode": "human-confirmed",
            }
        )

    if suspicious and args.aggregate_policy == "checkpoint":
        checkpoint = {
            "code": "AGGREGATE_AVAILABILITY_REVIEW",
            "severity": "blocking",
            "message": "Confirm whether the suspicious aggregate is available at prediction time before final-test evaluation.",
            "columns": suspicious,
            "sensitivity": sensitivity_rows,
        }
        manifest["status"] = "needs_input"
        manifest["human_checkpoints"].append(checkpoint)
        manifest["modelling"]["status"] = "awaiting-aggregate-decision"
        decisions.append(
            {
                "id": "DMOD-004",
                "timestamp": now,
                "stage": "leakage-review",
                "decision": "Pause before final-test evaluation",
                "reason": "Data alone cannot establish whether the aggregate is available at prediction time.",
                "evidence": sensitivity_rows,
                "mode": "automatic-checkpoint",
            }
        )
    else:
        selected_feature_set = "without_suspicious_aggregates" if suspicious and args.aggregate_policy == "drop" else "full"
        candidates = {
            model_name: best[(selected_feature_set, model_name)]
            for model_name in candidate_models
        }
        selected_model, selection_diagnostics = choose_model(candidates)
        selected_features = feature_sets[selected_feature_set]
        fitted: dict[str, Any] = {}
        for model_name, item in candidates.items():
            estimator = item["estimator"]
            estimator.fit(X_dev[selected_features], y_dev)
            fitted[model_name] = estimator
        dummy.fit(X_dev[selected_features], y_dev)
        fitted["dummy_most_frequent"] = dummy

        labelled_mask = y_test.notna() if y_test is not None else None
        final_metrics: dict[str, Any] = {}
        if y_test is not None and bool(labelled_mask.any()):
            for model_name, estimator in fitted.items():
                predicted = estimator.predict(X_test.loc[labelled_mask, selected_features])
                probabilities = estimator.predict_proba(X_test.loc[labelled_mask, selected_features]) if hasattr(estimator, "predict_proba") else None
                classes = [str(value) for value in estimator.classes_]
                final_metrics[model_name] = evaluate_predictions(
                    y_test.loc[labelled_mask], predicted, probabilities, classes, manifest["task_type"], manifest["positive_label"]
                )
        selected_estimator = fitted[selected_model]
        all_predictions = selected_estimator.predict(X_test[selected_features])
        all_probabilities = selected_estimator.predict_proba(X_test[selected_features]) if hasattr(selected_estimator, "predict_proba") else None
        selected_classes = [str(value) for value in selected_estimator.classes_]
        predictions = pd.DataFrame(
            {
                "source_row_index": row_refs.to_numpy(),
                "true_label": y_test.astype("string").where(y_test.notna(), None).to_numpy() if y_test is not None else [None] * len(X_test),
                "predicted_label": all_predictions,
                "model": selected_model,
            }
        )
        if all_probabilities is not None:
            for index, label in enumerate(selected_classes):
                safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", label)
                predictions[f"score__{safe_label}"] = all_probabilities[:, index]

        all_model_prediction_frames = []
        for model_name, estimator in fitted.items():
            model_predictions = estimator.predict(X_test[selected_features])
            model_probabilities = estimator.predict_proba(X_test[selected_features]) if hasattr(estimator, "predict_proba") else None
            model_classes = [str(value) for value in estimator.classes_]
            frame = pd.DataFrame(
                {
                    "source_row_index": row_refs.to_numpy(),
                    "true_label": y_test.astype("string").where(y_test.notna(), None).to_numpy() if y_test is not None else [None] * len(X_test),
                    "predicted_label": model_predictions,
                    "model": model_name,
                }
            )
            if model_probabilities is not None:
                for index, label in enumerate(model_classes):
                    safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", label)
                    frame[f"score__{safe_label}"] = model_probabilities[:, index]
            all_model_prediction_frames.append(frame)
        predictions_all_models = pd.concat(all_model_prediction_frames, ignore_index=True)

        for row in comparison_rows:
            is_selected_feature_model = row["feature_set"] == selected_feature_set and row["model"] in candidates
            is_dummy = row["model"] == "dummy_most_frequent"
            if is_selected_feature_model:
                row["selected_model"] = row["model"] == selected_model
            if is_selected_feature_model or is_dummy:
                for metric, value in final_metrics.get(row["model"], {}).items():
                    if isinstance(value, (int, float)):
                        row[f"final_{metric}"] = value
        manifest["status"] = "modelled"
        manifest["modelling"].update(
            {
                "status": "complete",
                "selected_feature_set": selected_feature_set,
                "selected_features": selected_features,
                "selected_model": selected_model,
                "selected_parameters": candidates[selected_model]["parameters"],
                "selection_basis": "paired development-fold macro-F1 with the documented practical-tie rule; final test metrics were not used for selection",
                "selection_diagnostics": selection_diagnostics,
                "labelled_final_rows": int(labelled_mask.sum()) if labelled_mask is not None else 0,
                "warning_resolutions": {
                    "SUSPICIOUS_AGGREGATE": args.aggregate_policy,
                    "DEPENDENCY_STRUCTURE_REVIEW": (
                        "independent-rows-confirmed" if dependency_candidates else "not-triggered"
                    ),
                },
            }
        )
        decisions.extend(
            [
                {
                    "id": "DMOD-004",
                    "timestamp": now,
                    "stage": "leakage-review",
                    "decision": f"{args.aggregate_policy} suspicious aggregate predictors",
                    "reason": "Explicit aggregate policy supplied before final-test evaluation.",
                    "evidence": sensitivity_rows,
                    "mode": "human-confirmed" if suspicious else "automatic",
                },
                {
                    "id": "DMOD-005",
                    "timestamp": now,
                    "stage": "model-selection",
                    "decision": selected_model,
                    "reason": "Selected from paired development-fold macro-F1 using the practical-tie rule before final-test evaluation.",
                    "evidence": {"models": {name: values["metrics"] for name, values in candidates.items()}, "selection_diagnostics": selection_diagnostics},
                    "mode": "automatic",
                },
            ]
        )
        manifest["artifacts"].update(
            {
                "test_metrics": "test_metrics.json" if final_metrics else None,
                "predictions": "predictions.csv",
                "predictions_all_models": "predictions_all_models.csv",
                "verification": "verification.json",
            }
        )

    manifest["artifacts"].update(
        {
            "cv_results": "cv_results.csv",
            "model_comparison": "model_comparison.csv",
            "sensitivity_results": "sensitivity_results.csv" if sensitivity_rows else None,
            "fold_assignments": "fold_assignments.csv",
        }
    )
    manifest["modelling"]["completed_at"] = datetime.now().astimezone().isoformat()
    manifest["modelling"]["elapsed_seconds"] = float(time.perf_counter() - started_clock)
    fold_assignment = pd.DataFrame(
        {
            "source_row_index": X_dev.index.to_numpy(),
            "fold": np.full(len(X_dev), -1, dtype=int),
        }
    )
    for fold_number, (_, validation_positions) in enumerate(folds):
        fold_assignment.loc[validation_positions, "fold"] = fold_number
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        write_partial_run(staging, manifest, profile, decisions)
        pd.DataFrame(cv_rows).to_csv(staging / "cv_results.csv", index=False)
        pd.DataFrame(comparison_rows).to_csv(staging / "model_comparison.csv", index=False)
        fold_assignment.to_csv(staging / "fold_assignments.csv", index=False)
        if sensitivity_rows:
            pd.DataFrame(sensitivity_rows).to_csv(staging / "sensitivity_results.csv", index=False)
        if manifest["status"] == "modelled":
            if final_metrics:
                write_json(
                    staging / "test_metrics.json",
                    {
                        "schema_version": "1.0",
                        "run_id": args.run_id,
                        "selected_model": manifest["modelling"]["selected_model"],
                        "models": final_metrics,
                    },
                )
            predictions.to_csv(staging / "predictions.csv", index=False)
            predictions_all_models.to_csv(staging / "predictions_all_models.csv", index=False)
            verification = verify_run_directory(staging)
            if not verification["all_checks_passed"]:
                raise ModellingError("Independent saved-prediction verification failed.")
            write_json(staging / "verification.json", verification)
            manifest["modelling"]["automatic_verification_passed"] = True
            write_json(staging / "run_manifest.json", manifest)
        os.replace(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return 0 if manifest["status"] == "modelled" else 3


def main() -> int:
    args = parse_args()
    destination = resolve_run_destination(args)
    if destination.exists():
        print(json.dumps({"status": "error", "message": f"Run directory already exists: {destination}"}), file=sys.stderr)
        return 2
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = run(args, destination)
        manifest = json.loads((destination / "run_manifest.json").read_text())
        print(
            json.dumps(
                {
                    "run_id": args.run_id,
                    "status": manifest["status"],
                    "selected_model": manifest.get("modelling", {}).get("selected_model"),
                    "output_dir": str(destination),
                    "human_checkpoint_count": len(manifest["human_checkpoints"]),
                },
                ensure_ascii=False,
            )
        )
        return result
    except Exception as exc:
        try:
            write_failed_run(destination, args, exc)
        except Exception:
            pass
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
