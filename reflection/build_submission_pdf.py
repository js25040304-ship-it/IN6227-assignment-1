#!/usr/bin/env python3

"""Render the approved Reflection and append it after the two-page main report."""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def inline_markup(text: str) -> str:
    escaped = html.escape(text)
    return re.sub(
        r"`([^`]+)`",
        lambda match: f'<font name="Courier">{match.group(1)}</font>',
        escaped,
    )


def render_reflection(source: Path, output: Path, full_name: str, matric: str) -> None:
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "ReflectionTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=20,
        textColor=colors.HexColor("#1F2A37"),
        alignment=TA_CENTER,
        spaceAfter=4 * mm,
    )
    identity = ParagraphStyle(
        "Identity",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#5C6773"),
        alignment=TA_CENTER,
        spaceAfter=5 * mm,
    )
    heading = ParagraphStyle(
        "ReflectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=13,
        textColor=colors.HexColor("#1F2A37"),
        spaceBefore=2.5 * mm,
        spaceAfter=1.2 * mm,
        keepWithNext=True,
    )
    body = ParagraphStyle(
        "ReflectionBody",
        parent=styles["BodyText"],
        fontName="Times-Roman",
        fontSize=9.2,
        leading=11.4,
        alignment=TA_JUSTIFY,
        firstLineIndent=4.5 * mm,
        spaceAfter=2.1 * mm,
        textColor=colors.HexColor("#202833"),
    )

    lines = source.read_text(encoding="utf-8").splitlines()
    story = [
        Paragraph("Reflection", title),
        Paragraph(
            f"{html.escape(full_name)} &nbsp;&nbsp; {html.escape(matric)} &nbsp;&nbsp; IN6227-Assignment-1 &nbsp;&nbsp; Variant-2",
            identity,
        ),
    ]
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            story.append(Paragraph(inline_markup(" ".join(paragraph)), body))
            paragraph.clear()

    for raw in lines:
        line = raw.strip()
        if not line:
            flush()
        elif line == "# Reflection":
            continue
        elif line.startswith("## "):
            flush()
            story.append(Paragraph(html.escape(line[3:]), heading))
        else:
            paragraph.append(line)
    flush()

    output.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=17 * mm,
        leftMargin=17 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title="IN6227 Assignment 1 Reflection",
        author=full_name,
    )

    def footer(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#5C6773"))
        canvas.drawString(17 * mm, 8 * mm, "Reflection - outside the two-page main-report limit")
        canvas.drawRightString(A4[0] - 17 * mm, 8 * mm, f"Reflection {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)


def merge(main_report: Path, reflection: Path, output: Path) -> None:
    main_reader = PdfReader(main_report)
    reflection_reader = PdfReader(reflection)
    if len(main_reader.pages) != 2:
        raise ValueError(f"Main report must be exactly 2 pages, found {len(main_reader.pages)}")
    if not reflection_reader.pages:
        raise ValueError("Reflection PDF is empty")
    writer = PdfWriter()
    writer.append(main_reader)
    writer.append(reflection_reader)
    writer.add_metadata(
        {
            "/Title": "IN6227 Assignment 1 - Variant 2",
            "/Author": "HU YINGXIN",
            "/Subject": "Main report and Reflection",
        }
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as stream:
        writer.write(stream)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-report", type=Path, required=True)
    parser.add_argument("--reflection-md", type=Path, required=True)
    parser.add_argument("--reflection-pdf", type=Path, required=True)
    parser.add_argument("--output-pdf", type=Path, required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--matric-number", required=True)
    args = parser.parse_args()

    render_reflection(args.reflection_md, args.reflection_pdf, args.full_name, args.matric_number)
    merge(args.main_report, args.reflection_pdf, args.output_pdf)
    print(args.output_pdf.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
