#!/usr/bin/env python3
"""Run the complete guarded classification workflow and generate a local PDF."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from docx import Document
from pypdf import PdfReader


SCRIPT_DIR = Path(__file__).resolve().parent


class WorkflowError(RuntimeError):
    """Raised when a workflow stage cannot produce a trustworthy deliverable."""


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
    parser.add_argument("--source-profile-run", type=Path)
    parser.add_argument("--group-column")
    parser.add_argument("--time-column")
    parser.add_argument("--n-jobs", type=int, default=1)
    parser.add_argument("--template-docx", type=Path)
    parser.add_argument("--output-pdf", type=Path)
    parser.add_argument("--soffice")
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--matric-number", required=True)
    parser.add_argument("--github-url", required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--llm-interface", required=True)
    parser.add_argument("--smoke", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def last_json(text: str) -> dict[str, Any]:
    for line in reversed(text.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def run_stage(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def stage_error(label: str, result: subprocess.CompletedProcess[str]) -> WorkflowError:
    details = last_json(result.stderr) or last_json(result.stdout)
    message = details.get("message") if details else None
    if not message:
        message = (result.stderr or result.stdout).strip() or f"exit code {result.returncode}"
    return WorkflowError(f"{label} failed: {message}")


def append_option(command: list[str], flag: str, value: Any) -> None:
    if value is not None:
        command.extend([flag, str(value)])


def resolve_soffice(requested: str | None) -> str:
    if requested:
        candidate = Path(requested).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
        discovered = shutil.which(requested)
        if discovered:
            return discovered
        raise WorkflowError(f"LibreOffice executable not found: {requested}")
    discovered = shutil.which("soffice")
    if not discovered:
        raise WorkflowError(
            "LibreOffice/soffice is required for direct PDF generation; Overleaf is not required."
        )
    return discovered


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"Could not read workflow evidence {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkflowError(f"Workflow evidence is not a JSON object: {path}")
    return value


def training_command(args: argparse.Namespace) -> list[str]:
    command = [sys.executable, str(SCRIPT_DIR / "train_evaluate.py"), str(args.dataset_path.resolve())]
    append_option(command, "--output-dir", args.output_dir.resolve() if args.output_dir else None)
    append_option(command, "--run-id", args.run_id)
    append_option(command, "--target", args.target)
    append_option(command, "--sheet", args.sheet)
    append_option(command, "--positive-label", args.positive_label)
    command.extend(["--random-seed", str(args.random_seed)])
    for column in args.exclude_column:
        command.extend(["--exclude-column", column])
    command.extend(["--aggregate-policy", args.aggregate_policy])
    command.extend(["--dependency-policy", args.dependency_policy])
    append_option(
        command,
        "--source-profile-run",
        args.source_profile_run.resolve() if args.source_profile_run else None,
    )
    append_option(command, "--group-column", args.group_column)
    append_option(command, "--time-column", args.time_column)
    command.extend(["--n-jobs", str(args.n_jobs)])
    if args.smoke:
        command.append("--smoke")
    return command


def checkpoint_summary(run_dir: Path, training: dict[str, Any]) -> dict[str, Any]:
    manifest = read_json(run_dir / "run_manifest.json")
    checkpoints = manifest.get("human_checkpoints", [])
    return {
        "status": "needs_input",
        "run_id": manifest.get("run_id") or training.get("run_id"),
        "run_dir": str(run_dir),
        "checkpoint_codes": [item.get("code") for item in checkpoints if item.get("code")],
        "checkpoints": checkpoints,
        "message": "Human review is required. No final-test metrics or report were generated.",
    }


def main() -> int:
    args = parse_args()
    try:
        if not args.dataset_path.exists():
            raise WorkflowError(f"Dataset path does not exist: {args.dataset_path}")
        if args.template_docx and not args.template_docx.is_file():
            raise WorkflowError(f"DOCX template does not exist: {args.template_docx}")
        soffice = resolve_soffice(args.soffice)

        training_result = run_stage(training_command(args))
        training = last_json(training_result.stdout)
        run_dir_text = training.get("output_dir")
        if not run_dir_text and args.output_dir:
            run_dir_text = str(args.output_dir.resolve())
        if not run_dir_text:
            raise stage_error("Training", training_result)
        run_dir = Path(run_dir_text).resolve()

        if training_result.returncode == 3:
            emit(checkpoint_summary(run_dir, training))
            return 3
        if training_result.returncode != 0:
            raise stage_error("Training", training_result)

        verification = read_json(run_dir / "verification.json")
        if verification.get("all_checks_passed") is not True:
            raise WorkflowError("Independent verification did not pass; report generation was refused.")

        report_dir = run_dir / "report"
        report_data = report_dir / "report_data.json"
        assembly_result = run_stage(
            [
                sys.executable,
                str(SCRIPT_DIR / "assemble_report_data.py"),
                str(run_dir),
                "--output",
                str(report_data),
            ]
        )
        if assembly_result.returncode != 0:
            raise stage_error("Report-data assembly", assembly_result)

        if args.template_docx:
            template = args.template_docx.resolve()
        else:
            template = report_dir / "generated_template.docx"
            template.parent.mkdir(parents=True, exist_ok=True)
            Document().save(template)

        output_docx = report_dir / "report_source.docx"
        output_pdf = args.output_pdf.resolve() if args.output_pdf else report_dir / "main_report.pdf"
        report_command = [
            sys.executable,
            str(SCRIPT_DIR / "generate_report.py"),
            str(report_data),
            "--template-docx",
            str(template),
            "--full-name",
            args.full_name,
            "--matric-number",
            args.matric_number,
            "--github-url",
            args.github_url,
            "--model-name",
            args.model_name,
            "--model-version",
            args.model_version,
            "--llm-interface",
            args.llm_interface,
            "--output-docx",
            str(output_docx),
            "--output-pdf",
            str(output_pdf),
            "--figures-dir",
            str(run_dir / "figures"),
            "--soffice",
            soffice,
        ]
        report_result = run_stage(report_command)
        if report_result.returncode != 0:
            raise stage_error("Report generation", report_result)
        if not output_pdf.is_file():
            raise WorkflowError("Report generator completed without creating the requested PDF.")
        pages = len(PdfReader(output_pdf).pages)
        if pages < 1 or pages > 2:
            raise WorkflowError(f"Generated main report has {pages} pages; expected 1-2 pages.")

        manifest = read_json(run_dir / "run_manifest.json")
        emit(
            {
                "status": "complete",
                "run_id": manifest.get("run_id") or training.get("run_id"),
                "run_dir": str(run_dir),
                "selected_model": manifest.get("modelling", {}).get("selected_model"),
                "verification_passed": True,
                "report_data": str(report_data.resolve()),
                "docx": str(output_docx.resolve()),
                "pdf": str(output_pdf.resolve()),
                "pages": pages,
                "overleaf_required": False,
            }
        )
        return 0
    except WorkflowError as exc:
        emit({"status": "error", "message": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
