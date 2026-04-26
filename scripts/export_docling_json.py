#!/usr/bin/env python3
"""Export both Income Tax Act PDFs to Docling JSON in backend/data.

Usage:
    python scripts/export_docling_json.py
    python scripts/export_docling_json.py --act 2025
    python scripts/export_docling_json.py --ocr --table-structure
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import fitz
from docling.datamodel.base_models import InputFormat
from docling.datamodel.document import ConversionStatus
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DoclingDocument


ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "pdfs"
DATA_DIR = ROOT / "backend" / "data"

PDFS = {
    "1961": PDF_DIR / "income_tax_act_1961.pdf",
    "2025": PDF_DIR / "income_tax_act_2025.pdf",
}

OUTPUTS = {
    act_year: DATA_DIR / f"docling_{act_year}.json"
    for act_year in PDFS
}


def build_converter(*, use_ocr: bool, use_table_structure: bool) -> DocumentConverter:
    pipeline_options = PdfPipelineOptions(
        do_ocr=use_ocr,
        do_table_structure=use_table_structure,
    )
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )


def get_page_count(pdf_path: Path) -> int:
    with fitz.open(pdf_path) as doc:
        return doc.page_count


def build_chunked_document(
    converter: DocumentConverter,
    *,
    pdf_path: Path,
    chunk_size: int,
) -> DoclingDocument:
    total_pages = get_page_count(pdf_path)
    combined_doc: DoclingDocument | None = None

    for chunk_start in range(1, total_pages + 1, chunk_size):
        chunk_end = min(chunk_start + chunk_size - 1, total_pages)
        print(f"  Converting pages {chunk_start}-{chunk_end} of {total_pages}...")

        result = converter.convert(pdf_path, page_range=(chunk_start, chunk_end))
        if result.status != ConversionStatus.SUCCESS:
            raise RuntimeError(
                "Docling conversion failed for "
                f"{pdf_path.name} pages {chunk_start}-{chunk_end}: {result.status}"
            )

        if combined_doc is None:
            combined_doc = result.document
        else:
            combined_doc = DoclingDocument.concatenate([combined_doc, result.document])

    if combined_doc is None:
        raise RuntimeError(f"No pages were converted for {pdf_path.name}")

    combined_doc.name = pdf_path.stem
    return combined_doc


def export_pdf(
    converter: DocumentConverter,
    *,
    act_year: str,
    pdf_path: Path,
    output_path: Path,
    chunk_size: int,
) -> None:
    print(f"\n{'=' * 72}")
    print(f"Exporting {act_year} Act with Docling")
    print(f"Source : {pdf_path}")
    print(f"Output : {output_path}")
    print(f"{'=' * 72}")

    started_at = time.time()
    document = build_chunked_document(
        converter,
        pdf_path=pdf_path,
        chunk_size=chunk_size,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.save_as_json(output_path, indent=2)

    elapsed = time.time() - started_at
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(
        f"Saved {output_path.name} | "
        f"pages={document.num_pages()} | "
        f"time={elapsed:.1f}s | "
        f"size={size_mb:.1f} MB"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export Income Tax Act PDFs to Docling JSON."
    )
    parser.add_argument(
        "--act",
        choices=sorted(PDFS),
        help="Export only one act year.",
    )
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="Enable OCR. Leave off for text PDFs to keep conversion faster.",
    )
    parser.add_argument(
        "--table-structure",
        action="store_true",
        help="Extract table structure. Leave off for a lighter JSON export.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=100,
        help="Number of PDF pages to convert per Docling pass.",
    )
    args = parser.parse_args()

    acts_to_export = [args.act] if args.act else ["1961", "2025"]

    missing = [str(PDFS[act_year]) for act_year in acts_to_export if not PDFS[act_year].exists()]
    if missing:
        for path in missing:
            print(f"Missing PDF: {path}", file=sys.stderr)
        return 1

    converter = build_converter(
        use_ocr=args.ocr,
        use_table_structure=args.table_structure,
    )

    for act_year in acts_to_export:
        export_pdf(
            converter,
            act_year=act_year,
            pdf_path=PDFS[act_year],
            output_path=OUTPUTS[act_year],
            chunk_size=args.chunk_size,
        )

    print("\nDocling JSON export complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
