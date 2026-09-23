#!/usr/bin/env python3

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from pypdf import PdfReader


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_workflow.py"


class RunWorkflowTests(unittest.TestCase):
    def invoke(self, dataset: Path, output: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        soffice = shutil.which("soffice")
        if not soffice:
            self.skipTest("LibreOffice is required for the one-command PDF integration test")
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(dataset),
                "--output-dir",
                str(output),
                "--full-name",
                "Example Student",
                "--matric-number",
                "TEST001",
                "--github-url",
                "https://github.com/example/skill",
                "--model-name",
                "ExampleModel",
                "--model-version",
                "1.0",
                "--llm-interface",
                "Codex test harness",
                "--soffice",
                soffice,
                "--smoke",
                *extra,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_one_command_generates_verified_pdf_without_overleaf_or_supplied_template(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset = root / "numeric.csv"
            values = list(range(90))
            pd.DataFrame(
                {
                    "x": values,
                    "z": [(value % 7) / 7 for value in values],
                    "label": ["yes" if (value % 11) in {0, 1, 5, 8} else "no" for value in values],
                }
            ).to_csv(dataset, index=False)
            run_dir = root / "RUN-ONE"
            result = self.invoke(dataset, run_dir)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            summary = json.loads(result.stdout.strip().splitlines()[-1])
            pdf = run_dir / "report" / "main_report.pdf"
            verification = json.loads((run_dir / "verification.json").read_text())
            self.assertEqual(summary["status"], "complete")
            self.assertEqual(Path(summary["pdf"]).resolve(), pdf.resolve())
            self.assertTrue(verification["all_checks_passed"])
            self.assertTrue(pdf.is_file())
            reader = PdfReader(pdf)
            self.assertLessEqual(len(reader.pages), 2)
            page = reader.pages[0]
            lower_right_text = []

            def collect_lower_right(text, _cm, tm, _font, _size):
                if text.strip() and tm[4] > float(page.mediabox.width) / 2 and 90 < tm[5] < 410:
                    lower_right_text.append((tm[5], text.strip()))

            page.extract_text(visitor_text=collect_lower_right)
            self.assertIn("DISCUSSION", page.extract_text())
            self.assertTrue(
                lower_right_text,
                "Page 1 should use the lower-right column instead of leaving a large blank area",
            )
            self.assertLessEqual(
                min(y for y, _text in lower_right_text),
                205,
                "Page 1 right-column body should extend close to the bottom content margin",
            )
            second_page = reader.pages[1]
            second_page_right_text = []
            second_page_items = []

            def collect_second_page_right(text, _cm, tm, _font, _size):
                if text.strip():
                    second_page_items.append((tm[4], tm[5], text.strip()))
                    if tm[4] > float(second_page.mediabox.width) / 2 and tm[5] > 90:
                        second_page_right_text.append(text.strip())

            second_page.extract_text(visitor_text=collect_second_page_right)
            self.assertTrue(
                second_page_right_text,
                "Page 2 should balance content across both columns",
            )
            reproducibility_x = next(
                x for x, _y, text in second_page_items if "REPRODUCIBILITY AND VERIFICATION" in text
            )
            top_left_text = max(
                (y, text)
                for x, y, text in second_page_items
                if x < float(second_page.mediabox.width) / 2 and 90 < y < 780
            )[1]
            normalized_top_left = " ".join(top_left_text.split())
            top_right_text = max(
                (y, text)
                for x, y, text in second_page_items
                if x > float(second_page.mediabox.width) / 2 and 90 < y < 780
            )[1]
            normalized_top_right = " ".join(top_right_text.split())
            self.assertTrue(
                normalized_top_left.startswith("LIMITATIONS"),
                "Page 2 should begin with Limitations and then follow the report's semantic order; "
                f"got {normalized_top_left!r}",
            )
            self.assertTrue(
                normalized_top_right.startswith("REFERENCES"),
                "The right column should begin with the intact References block; "
                f"got {normalized_top_right!r}",
            )
            self.assertLess(
                reproducibility_x,
                float(second_page.mediabox.width) / 2,
                "Reproducibility should follow Skill generalisation in the left-column reading flow",
            )
            self.assertTrue((run_dir / "report" / "generated_template.docx").is_file())
            self.assertFalse(any(run_dir.rglob("*.tex")))

    def test_human_checkpoint_stops_before_report_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset = root / "aggregate.csv"
            values = list(range(60))
            pd.DataFrame(
                {
                    "x": values,
                    "composite_rank": [value * 2 for value in values],
                    "label": ["no", "yes"] * 30,
                }
            ).to_csv(dataset, index=False)
            run_dir = root / "RUN-CHECKPOINT"
            result = self.invoke(dataset, run_dir)
            self.assertEqual(result.returncode, 3, result.stdout + result.stderr)

            summary = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(summary["status"], "needs_input")
            self.assertIn("AGGREGATE_AVAILABILITY_REVIEW", summary["checkpoint_codes"])
            self.assertFalse((run_dir / "report" / "main_report.pdf").exists())
            self.assertFalse((run_dir / "test_metrics.json").exists())


if __name__ == "__main__":
    unittest.main()
