#!/usr/bin/env python3
"""Discover and profile tabular classification data without modelling it."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import shutil
import sys
import tempfile
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
import pandas as pd


SCHEMA_VERSION = "1.0"
ALLOWED_SUFFIXES = {".csv", ".tsv", ".xlsx"}
TARGET_NAMES = {"target", "label", "class", "outcome"}


class ProfileError(RuntimeError):
    """Raised for a deterministic input or profiling failure."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_path", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--target")
    parser.add_argument("--sheet")
    parser.add_argument("--positive-label")
    parser.add_argument("--random-seed", type=int, default=42)
    return parser.parse_args()


def resolve_run_destination(args: argparse.Namespace) -> Path:
    """Resolve an immutable run directory while keeping dataset_path the only required input."""
    if args.output_dir:
        destination = args.output_dir.resolve()
        args.run_id = args.run_id or destination.name
        return destination

    runs_root = (Path.cwd() / "runs").resolve()
    if args.run_id:
        return runs_root / args.run_id

    existing_numbers = []
    if runs_root.exists():
        for path in runs_root.iterdir():
            match = re.fullmatch(r"RUN-(\d+)", path.name)
            if path.is_dir() and match:
                existing_numbers.append(int(match.group(1)))
    next_number = max(existing_numbers, default=0) + 1
    args.run_id = f"RUN-{next_number:03d}"
    return runs_root / args.run_id


def sha256_stream(stream: Any) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return sha256_stream(stream)


def is_safe_zip_member(name: str) -> bool:
    posix = PurePosixPath(name)
    return not posix.is_absolute() and ".." not in posix.parts


def role_from_name(name: str) -> str | None:
    stem = Path(name).stem.casefold()
    train = bool(re.search(r"(^|[_\-.])train($|[_\-.])", stem)) or stem == "train"
    test = bool(re.search(r"(^|[_\-.])test($|[_\-.])", stem)) or stem == "test"
    if train and not test:
        return "train"
    if test and not train:
        return "test"
    return None


def select_sources(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not candidates:
        raise ProfileError("No supported tabular file was found.")
    if len(candidates) == 1:
        candidates[0]["role"] = "train"
        return candidates

    train = [item for item in candidates if role_from_name(item["logical_name"]) == "train"]
    test = [item for item in candidates if role_from_name(item["logical_name"]) == "test"]
    if len(train) == 1 and len(test) == 1:
        train[0]["role"] = "train"
        test[0]["role"] = "test"
        return [train[0], test[0]]
    names = ", ".join(sorted(item["logical_name"] for item in candidates))
    raise ProfileError(f"Ambiguous tabular sources; expected one file or one train/test pair: {names}")


def discover_sources(dataset_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = dataset_path.resolve()
    if not path.exists():
        raise ProfileError(f"Dataset path does not exist: {path}")

    if path.is_dir():
        candidates = []
        for item in sorted(path.rglob("*")):
            if item.is_file() and item.suffix.casefold() in ALLOWED_SUFFIXES:
                candidates.append(
                    {
                        "kind": "file",
                        "path": str(item),
                        "logical_name": str(item.relative_to(path)),
                        "suffix": item.suffix.casefold(),
                    }
                )
        sources = select_sources(candidates)
        fingerprint = hashlib.sha256(
            "".join(f"{x['logical_name']}:{sha256_file(Path(x['path']))}" for x in sources).encode()
        ).hexdigest()
        return sources, {"kind": "directory", "path": str(path), "sha256": fingerprint}

    if path.suffix.casefold() == ".zip":
        candidates = []
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if not is_safe_zip_member(info.filename):
                    raise ProfileError(f"Unsafe ZIP member path: {info.filename}")
                suffix = Path(info.filename).suffix.casefold()
                if not info.is_dir() and suffix in ALLOWED_SUFFIXES:
                    with archive.open(info) as stream:
                        member_hash = sha256_stream(stream)
                    candidates.append(
                        {
                            "kind": "zip_member",
                            "archive": str(path),
                            "logical_name": info.filename,
                            "suffix": suffix,
                            "sha256": member_hash,
                        }
                    )
        return select_sources(candidates), {
            "kind": "zip",
            "path": str(path),
            "sha256": sha256_file(path),
        }

    if path.suffix.casefold() not in ALLOWED_SUFFIXES:
        raise ProfileError(f"Unsupported file type: {path.suffix or '(none)'}")
    source = {
        "kind": "file",
        "path": str(path),
        "logical_name": path.name,
        "suffix": path.suffix.casefold(),
        "role": "train",
        "sha256": sha256_file(path),
    }
    return [source], {"kind": "file", "path": str(path), "sha256": source["sha256"]}


def read_excel(source: Any, sheet: str | None) -> tuple[pd.DataFrame, str]:
    book = pd.ExcelFile(source)
    if sheet:
        if sheet not in book.sheet_names:
            raise ProfileError(f"Excel sheet not found: {sheet}")
        return pd.read_excel(book, sheet_name=sheet), sheet
    nonempty = []
    for name in book.sheet_names:
        preview = pd.read_excel(book, sheet_name=name, nrows=1)
        if len(preview.columns) > 0:
            nonempty.append(name)
    if len(nonempty) != 1:
        raise ProfileError(f"Ambiguous Excel sheets; specify --sheet from: {', '.join(nonempty)}")
    return pd.read_excel(book, sheet_name=nonempty[0]), nonempty[0]


def load_source(source: dict[str, Any], sheet: str | None) -> tuple[pd.DataFrame, str | None]:
    suffix = source["suffix"]
    if source["kind"] == "zip_member":
        with zipfile.ZipFile(source["archive"]) as archive, archive.open(source["logical_name"]) as stream:
            if suffix == ".csv":
                return pd.read_csv(stream), None
            if suffix == ".tsv":
                return pd.read_csv(stream, sep="\t"), None
            return read_excel(stream, sheet)
    path = Path(source["path"])
    if "sha256" not in source:
        source["sha256"] = sha256_file(path)
    if suffix == ".csv":
        return pd.read_csv(path), None
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t"), None
    return read_excel(path, sheet)


def resolve_target(columns: list[str], explicit: str | None) -> tuple[str | None, str, list[str]]:
    if explicit:
        if explicit in columns:
            return explicit, "user-specified", [explicit]
        matches = [column for column in columns if column.casefold() == explicit.casefold()]
        if len(matches) == 1:
            return matches[0], "user-specified-case-normalized", matches
        return None, "invalid-explicit-target", matches
    candidates = [column for column in columns if column.casefold() in TARGET_NAMES]
    if len(candidates) == 1:
        return candidates[0], "name-inferred", candidates
    return None, "ambiguous-or-absent", candidates


def scalar(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def parsed_datetime(series: pd.Series) -> tuple[pd.Series, float]:
    nonnull = series.dropna()
    if nonnull.empty or not (
        pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)
    ):
        return pd.Series(dtype="datetime64[ns]"), 0.0
    try:
        parsed = pd.to_datetime(nonnull.astype("string"), errors="coerce", format="mixed")
    except TypeError:
        parsed = pd.to_datetime(nonnull.astype("string"), errors="coerce")
    return parsed, float(parsed.notna().mean())


def type_name(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    parsed, parse_ratio = parsed_datetime(series)
    if len(parsed) and parse_ratio >= 0.95 and parsed.nunique(dropna=True) >= 2:
        return "datetime"
    return "categorical"


def profile_split(df: pd.DataFrame, role: str, target: str | None) -> dict[str, Any]:
    if df.empty:
        raise ProfileError(f"{role} table has no rows.")
    if len(df.columns) < 2:
        raise ProfileError(f"{role} table needs at least two columns.")
    columns = [str(column) for column in df.columns]
    if len(set(columns)) != len(columns):
        raise ProfileError(f"{role} table has duplicate column names.")
    df = df.copy()
    df.columns = columns
    predictors = [column for column in columns if column != target]

    missing = {
        column: {"count": int(df[column].isna().sum()), "ratio": float(df[column].isna().mean())}
        for column in columns
    }
    unique = {column: int(df[column].nunique(dropna=True)) for column in columns}
    constants = [column for column in predictors if unique[column] <= 1]
    near_constants = []
    identifiers = []
    high_cardinality = []
    numeric: dict[str, Any] = {}
    categorical: dict[str, Any] = {}
    datetime_summary: dict[str, Any] = {}
    dependency_candidates: list[dict[str, str]] = []
    inferred_types = {column: type_name(df[column]) for column in columns}

    for column in predictors:
        series = df[column]
        nonnull = series.dropna()
        if len(nonnull):
            top_ratio = float(nonnull.value_counts(normalize=True, dropna=True).iloc[0])
            if top_ratio >= 0.99 and unique[column] > 1:
                near_constants.append({"column": column, "top_ratio": top_ratio})
        uniqueness_ratio = float(unique[column] / max(len(nonnull), 1))
        if uniqueness_ratio >= 0.95 and re.search(r"(^id$|_id$|^id_|uuid|index|row_?num)", column, re.I):
            identifiers.append({"column": column, "uniqueness_ratio": uniqueness_ratio})

        if inferred_types[column] == "numeric":
            finite = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
            q = finite.quantile([0, 0.25, 0.5, 0.75, 1.0])
            q1, q3 = q.loc[0.25], q.loc[0.75]
            iqr = q3 - q1
            outliers = 0 if pd.isna(iqr) else int(((finite < q1 - 1.5 * iqr) | (finite > q3 + 1.5 * iqr)).sum())
            numeric[column] = {
                "count": int(finite.notna().sum()),
                "mean": scalar(finite.mean()),
                "std": scalar(finite.std()),
                "min": scalar(q.loc[0]),
                "q1": scalar(q1),
                "median": scalar(q.loc[0.5]),
                "q3": scalar(q3),
                "max": scalar(q.loc[1.0]),
                "zeros": int((finite == 0).sum()),
                "positive_infinity": int(np.isposinf(pd.to_numeric(series, errors="coerce")).sum()),
                "negative_infinity": int(np.isneginf(pd.to_numeric(series, errors="coerce")).sum()),
                "iqr_outlier_count": outliers,
            }
        elif inferred_types[column] == "datetime":
            if pd.api.types.is_datetime64_any_dtype(series):
                parsed = pd.to_datetime(nonnull, errors="coerce")
                parse_ratio = float(parsed.notna().mean()) if len(parsed) else 0.0
            else:
                parsed, parse_ratio = parsed_datetime(series)
            datetime_summary[column] = {
                "count": int(len(nonnull)),
                "parse_success_ratio": parse_ratio,
                "unique": int(parsed.nunique(dropna=True)),
                "min": scalar(parsed.min()) if parsed.notna().any() else None,
                "max": scalar(parsed.max()) if parsed.notna().any() else None,
            }
            dependency_candidates.append(
                {
                    "column": column,
                    "kind": "time",
                    "reason": "datetime predictor may encode observation order",
                }
            )
        else:
            counts = nonnull.astype(str).value_counts().head(10)
            categorical[column] = {
                "count": int(len(nonnull)),
                "unique": unique[column],
                "top_values": [{"value": key, "count": int(value)} for key, value in counts.items()],
            }
            if unique[column] >= 100 or uniqueness_ratio >= 0.5:
                high_cardinality.append(
                    {"column": column, "unique": unique[column], "uniqueness_ratio": uniqueness_ratio}
                )

        if (
            re.search(
                r"(^|_)(group|entity|subject|patient|customer|account|user|household|case|member)(?:_?id)?($|_)",
                column,
                re.I,
            )
            and 2 <= unique[column] < len(nonnull)
        ):
            dependency_candidates.append(
                {
                    "column": column,
                    "kind": "group",
                    "reason": "repeated entity-like values may link multiple rows",
                }
            )

    exact_duplicates = int(df.duplicated().sum())
    duplicate_predictors = int(df.duplicated(subset=predictors).sum()) if predictors else 0
    conflicting_predictor_groups = 0
    if target and target in df.columns and predictors:
        hashes = pd.util.hash_pandas_object(df[predictors], index=False)
        pairs = pd.DataFrame({"hash": hashes, "target": df[target].astype("string")}).dropna()
        conflicting_predictor_groups = int((pairs.groupby("hash")["target"].nunique() > 1).sum())

    correlations = []
    numeric_frame = df[predictors].select_dtypes(include=np.number)
    if numeric_frame.shape[1] >= 2:
        corr = numeric_frame.replace([np.inf, -np.inf], np.nan).corr()
        for i, left in enumerate(corr.columns):
            for right in corr.columns[i + 1 :]:
                value = corr.loc[left, right]
                if pd.notna(value) and abs(value) >= 0.7:
                    correlations.append({"left": left, "right": right, "correlation": float(value)})
        correlations.sort(key=lambda item: abs(item["correlation"]), reverse=True)

    suspicious_aggregates = []
    for column in predictors:
        if re.search(r"(^|_)(composite|aggregate|rank|total)(_|$)", column, re.I):
            related = [
                item
                for item in correlations
                if item["left"] == column or item["right"] == column
            ]
            suspicious_aggregates.append(
                {
                    "column": column,
                    "reason": "name suggests an aggregate or rank",
                    "high_correlations": related,
                }
            )

    target_profile = None
    if target and target in df.columns:
        observed = df[target].dropna()
        counts = observed.astype(str).value_counts()
        target_profile = {
            "missing": int(df[target].isna().sum()),
            "observed": int(len(observed)),
            "unique": int(observed.nunique()),
            "classes": [{"label": key, "count": int(value), "ratio": float(value / len(observed))} for key, value in counts.items()],
        }

    return {
        "role": role,
        "shape": {"rows": int(len(df)), "columns": int(len(columns))},
        "columns": columns,
        "predictors": predictors,
        "column_types": inferred_types,
        "pandas_dtypes": {column: str(df[column].dtype) for column in columns},
        "missing": missing,
        "unique_non_null": unique,
        "rows_with_any_missing": int(df.isna().any(axis=1).sum()),
        "exact_duplicate_rows": exact_duplicates,
        "duplicate_predictor_rows": duplicate_predictors,
        "conflicting_predictor_groups": conflicting_predictor_groups,
        "constant_predictors": constants,
        "near_constant_predictors": near_constants,
        "identifier_candidates": identifiers,
        "dependency_candidates": dependency_candidates,
        "high_cardinality_categoricals": high_cardinality,
        "numeric_summary": numeric,
        "categorical_summary": categorical,
        "datetime_summary": datetime_summary,
        "high_numeric_correlations": correlations,
        "suspicious_aggregate_candidates": suspicious_aggregates,
        "target": target_profile,
    }


def cross_split_profile(
    train: pd.DataFrame, test: pd.DataFrame, target: str | None
) -> dict[str, Any]:
    train_columns = [str(column) for column in train.columns]
    test_columns = [str(column) for column in test.columns]
    train_predictors = [column for column in train_columns if column != target]
    test_predictors = [column for column in test_columns if column != target]
    missing_in_test = sorted(set(train_predictors) - set(test_predictors))
    extra_in_test = sorted(set(test_predictors) - set(train_predictors))
    common = [column for column in train_predictors if column in test_predictors]
    pandas_dtype_mismatches = [
        {"column": column, "train": str(train[column].dtype), "test": str(test[column].dtype)}
        for column in common
        if str(train[column].dtype) != str(test[column].dtype)
    ]
    semantic_type_mismatches = [
        {
            "column": column,
            "train": type_name(train[column]),
            "test": type_name(test[column]),
        }
        for column in common
        if type_name(train[column]) != type_name(test[column])
    ]
    unseen = []
    for column in common:
        if not pd.api.types.is_numeric_dtype(train[column]):
            train_values = set(train[column].dropna().astype(str))
            test_values = set(test[column].dropna().astype(str))
            values = sorted(test_values - train_values)
            if values:
                unseen.append({"column": column, "count": len(values), "values": values[:50], "truncated": len(values) > 50})

    overlap = None
    if not missing_in_test and not extra_in_test and common:
        train_hashes = set(pd.util.hash_pandas_object(train[common], index=False).astype("uint64").tolist())
        test_hashes = pd.util.hash_pandas_object(test[common], index=False).astype("uint64")
        overlap = {
            "test_rows_matching_train_predictors": int(test_hashes.isin(train_hashes).sum()),
            "shared_unique_predictor_hashes": int(len(set(test_hashes.tolist()) & train_hashes)),
        }
    unseen_test_labels = []
    if target and target in train_columns and target in test_columns:
        train_labels = set(train[target].dropna().astype(str))
        test_labels = set(test[target].dropna().astype(str))
        unseen_test_labels = sorted(test_labels - train_labels)

    return {
        "missing_predictors_in_test": missing_in_test,
        "extra_predictors_in_test": extra_in_test,
        "dtype_mismatches": pandas_dtype_mismatches,
        "semantic_type_mismatches": semantic_type_mismatches,
        "unseen_test_categories": unseen,
        "unseen_test_labels": unseen_test_labels,
        "predictor_overlap": overlap,
        "test_has_target": bool(target and target in test_columns),
    }


def package_versions() -> dict[str, str | None]:
    result: dict[str, str | None] = {"python": platform.python_version()}
    for name in ("pandas", "numpy", "openpyxl", "scikit-learn"):
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = None
    return result


def skill_fingerprint() -> str:
    root = Path(__file__).resolve().parents[1]
    files = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix.casefold() not in {".pyc", ".pyo"}
            and path.name != ".DS_Store"
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def build_run(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    sources, dataset = discover_sources(args.dataset_path)
    frames: dict[str, pd.DataFrame] = {}
    source_records = []
    for source in sources:
        frame, resolved_sheet = load_source(source, args.sheet)
        frames[source["role"]] = frame
        source_records.append(
            {
                "role": source["role"],
                "logical_name": source["logical_name"],
                "kind": source["kind"],
                "sha256": source.get("sha256"),
                "sheet": resolved_sheet,
            }
        )

    train = frames["train"]
    train.columns = [str(column) for column in train.columns]
    target, target_method, candidates = resolve_target(list(train.columns), args.target)
    warnings: list[dict[str, Any]] = []
    status = "profiled"
    task_type = None
    labels: list[str] = []
    positive_label = None
    positive_label_resolution = "not-applicable"

    if target is None:
        status = "needs_input"
        warnings.append(
            {
                "code": "TARGET_UNRESOLVED",
                "severity": "blocking",
                "message": "Specify one target column before modelling.",
                "candidates": candidates,
            }
        )
    else:
        observed = train[target].dropna()
        unique = int(observed.nunique())
        labels = sorted(observed.astype(str).unique().tolist())
        counts = observed.astype(str).value_counts()
        if unique < 2:
            status = "failed"
            warnings.append({"code": "SINGLE_CLASS_TARGET", "severity": "blocking", "message": "The target has fewer than two observed classes."})
        elif unique > 50 or (
            pd.api.types.is_numeric_dtype(observed)
            and unique > 20
            and unique / max(len(observed), 1) > 0.2
        ):
            status = "needs_input"
            warnings.append({"code": "TARGET_LOOKS_CONTINUOUS", "severity": "blocking", "message": "The target has too many distinct values for supported single-label classification."})
        elif int(counts.min()) < 2:
            status = "failed"
            warnings.append({"code": "CLASS_TOO_SMALL", "severity": "blocking", "message": "At least one class has fewer than two usable rows."})
        else:
            task_type = "binary" if unique == 2 else "multiclass"
            ratio = float(counts.max() / counts.min())
            minority_share = float(counts.min() / counts.sum())
            if ratio > 1.5 or minority_share < 0.35:
                warnings.append({"code": "CLASS_IMBALANCE", "severity": "review", "message": "Class proportions are materially uneven; accuracy alone is unsuitable.", "majority_to_minority_ratio": ratio, "minority_share": minority_share})
        if task_type == "binary":
            if args.positive_label:
                if args.positive_label not in set(labels):
                    status = "needs_input"
                    positive_label_resolution = "invalid-user-specified"
                    warnings.append({"code": "INVALID_POSITIVE_LABEL", "severity": "blocking", "message": f"Positive label not found: {args.positive_label}"})
                else:
                    positive_label = args.positive_label
                    positive_label_resolution = "user-specified"
            else:
                semantic_positive = {"yes", "true", "positive", "pos", "1"}
                matches = [label for label in labels if label.casefold() in semantic_positive]
                if len(matches) == 1:
                    positive_label = matches[0]
                    positive_label_resolution = "semantic-name-inferred"
                else:
                    positive_label_resolution = "unresolved-report-per-class"

    split_profiles = {role: profile_split(frame, role, target) for role, frame in frames.items()}
    cross = cross_split_profile(frames["train"], frames["test"], target) if "test" in frames else None

    for role, profile in split_profiles.items():
        if profile["rows_with_any_missing"]:
            warnings.append({"code": "MISSING_VALUES", "severity": "review", "split": role, "message": f"{profile['rows_with_any_missing']} rows contain missing values."})
        if profile["identifier_candidates"]:
            warnings.append({"code": "IDENTIFIER_CANDIDATE", "severity": "review", "split": role, "columns": [item["column"] for item in profile["identifier_candidates"]], "message": "Potential identifier predictors require exclusion or review."})
        if role == "train" and profile["dependency_candidates"]:
            warnings.append({"code": "DEPENDENCY_STRUCTURE_REVIEW", "severity": "review", "split": role, "candidates": profile["dependency_candidates"], "message": "Time- or entity-like predictors require confirmation that rows are independent before shuffled validation."})
        if profile["high_cardinality_categoricals"]:
            warnings.append({"code": "HIGH_CARDINALITY", "severity": "review", "split": role, "columns": [item["column"] for item in profile["high_cardinality_categoricals"]], "message": "High-cardinality categoricals may require constrained encoding."})
        if profile["conflicting_predictor_groups"]:
            warnings.append({"code": "CONFLICTING_DUPLICATES", "severity": "review", "split": role, "message": "Identical predictor groups contain different labels.", "groups": profile["conflicting_predictor_groups"]})
        if role == "train" and profile["high_numeric_correlations"]:
            warnings.append({"code": "HIGH_NUMERIC_CORRELATION", "severity": "review", "split": role, "message": "Highly correlated numeric predictors require model-aware interpretation, not automatic deletion.", "pairs": profile["high_numeric_correlations"]})
        if role == "train" and profile["suspicious_aggregate_candidates"]:
            warnings.append({"code": "SUSPICIOUS_AGGREGATE", "severity": "review", "split": role, "message": "Aggregate- or rank-like predictors require availability review and a with/without sensitivity check.", "candidates": profile["suspicious_aggregate_candidates"]})

    if cross:
        if cross["missing_predictors_in_test"] or cross["extra_predictors_in_test"]:
            status = "failed"
            warnings.append({"code": "SPLIT_SCHEMA_MISMATCH", "severity": "blocking", "message": "Train and test predictor columns do not match."})
        if cross["semantic_type_mismatches"]:
            status = "failed"
            warnings.append({"code": "SPLIT_TYPE_MISMATCH", "severity": "blocking", "message": "Train and test predictors have incompatible inferred types.", "columns": cross["semantic_type_mismatches"]})
        if cross["unseen_test_labels"]:
            status = "failed"
            warnings.append({"code": "UNSEEN_TEST_LABEL", "severity": "blocking", "message": "The labelled test set contains classes absent from training data.", "labels": cross["unseen_test_labels"]})
        if cross["predictor_overlap"] and cross["predictor_overlap"]["test_rows_matching_train_predictors"]:
            warnings.append({"code": "TRAIN_TEST_OVERLAP", "severity": "review", "message": "Some test rows exactly match training predictors.", **cross["predictor_overlap"]})

    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone()
    decisions = [
        {"id": "DPROF-001", "timestamp": now_local.isoformat(), "stage": "input", "decision": "Resolved dataset sources", "reason": "Used deterministic file and train/test name rules.", "evidence": [item["logical_name"] for item in source_records], "mode": "automatic"},
        {"id": "DPROF-002", "timestamp": now_local.isoformat(), "stage": "target", "decision": target or "Target unresolved", "reason": target_method, "evidence": candidates, "mode": "automatic"},
        {"id": "DPROF-003", "timestamp": now_local.isoformat(), "stage": "task", "decision": task_type or status, "reason": "Derived from observed target cardinality and minimum class count.", "evidence": labels, "mode": "automatic"},
    ]
    if task_type == "binary":
        decisions.append({"id": "DPROF-004", "timestamp": now_local.isoformat(), "stage": "class-semantics", "decision": positive_label or "report per class", "reason": positive_label_resolution, "evidence": labels, "mode": "automatic"})
    review_codes = [warning["code"] for warning in warnings if warning["severity"] == "review"]
    if review_codes:
        decisions.append({"id": "DPROF-005", "timestamp": now_local.isoformat(), "stage": "review", "decision": "Preserve findings for modelling decisions", "reason": "Review warnings require an explicit downstream response rather than silent preprocessing.", "evidence": review_codes, "mode": "automatic"})
    profile = {
        "schema_version": SCHEMA_VERSION,
        "run_id": args.run_id,
        "target": target,
        "target_resolution": target_method,
        "task_type": task_type,
        "splits": split_profiles,
        "cross_split": cross,
    }
    artifacts = {"run_manifest": "run_manifest.json", "data_profile": "data_profile.json", "decision_log": "decision_log.json"}
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": args.run_id,
        "status": status,
        "created_at_utc": now_utc.isoformat(),
        "created_at_local": now_local.isoformat(),
        "dataset": dataset,
        "sources": source_records,
        "target": target,
        "target_resolution": target_method,
        "task_type": task_type,
        "labels": labels,
        "positive_label": positive_label,
        "positive_label_resolution": positive_label_resolution,
        "random_seed": args.random_seed,
        "runtime_versions": package_versions(),
        "skill_sha256": skill_fingerprint(),
        "row_reconciliation": {
            role: {
                "source_rows": profile_item["shape"]["rows"],
                "missing_target_rows": profile_item["target"]["missing"] if profile_item["target"] else None,
                "usable_labelled_rows": profile_item["target"]["observed"] if profile_item["target"] else None,
            }
            for role, profile_item in split_profiles.items()
        },
        "warnings": warnings,
        "human_checkpoints": [warning for warning in warnings if warning["severity"] == "blocking" and status == "needs_input"],
        "errors": [warning for warning in warnings if warning["severity"] == "blocking" and status == "failed"],
        "artifacts": artifacts,
    }
    return manifest, profile, decisions


def main() -> int:
    args = parse_args()
    destination = resolve_run_destination(args)
    if destination.exists():
        print(json.dumps({"status": "error", "message": f"Run directory already exists: {destination}"}), file=sys.stderr)
        return 2
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        manifest, profile, decisions = build_run(args)
        write_json(staging / "data_profile.json", profile)
        write_json(staging / "decision_log.json", decisions)
        write_json(staging / "run_manifest.json", manifest)
        os.replace(staging, destination)
        print(json.dumps({"run_id": args.run_id, "status": manifest["status"], "target": manifest["target"], "task_type": manifest["task_type"], "output_dir": str(destination), "warning_count": len(manifest["warnings"])}, ensure_ascii=False))
        return 0 if manifest["status"] == "profiled" else 3
    except Exception as exc:
        shutil.rmtree(staging, ignore_errors=True)
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
