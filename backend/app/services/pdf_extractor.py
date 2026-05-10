from dataclasses import dataclass

import fitz  # PyMuPDF

from app.core.config import get_settings
from app.services.text_utils import clean_whitespace
from app.utils.exceptions import SourceExtractionError, UnsupportedFileError


@dataclass
class PdfExtractionResult:
    title: str
    pages: list[tuple[int, str]]
    page_count: int
    text: str
    warnings: list[str]


def validate_pdf_upload(filename: str, content_type: str | None, raw: bytes) -> None:
    settings = get_settings()
    if len(raw) > settings.max_upload_bytes:
        raise UnsupportedFileError(f"PDF is too large. Max allowed size is {settings.max_upload_mb} MB.")

    lowered = filename.lower()
    looks_like_pdf = lowered.endswith(".pdf") or raw.startswith(b"%PDF")
    if not looks_like_pdf:
        raise UnsupportedFileError("Unsupported file type. Please upload a PDF file.")

    if content_type and content_type not in {"application/pdf", "application/octet-stream"}:
        # Browser uploads sometimes send octet-stream. Keep this as a warning-level validation.
        if not raw.startswith(b"%PDF"):
            raise UnsupportedFileError(f"Unsupported content type: {content_type}")


def extract_pdf_text(filename: str, raw: bytes) -> PdfExtractionResult:
    try:
        doc = fitz.open(stream=raw, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises different exception types by version.
        raise SourceExtractionError(f"Could not read PDF: {exc}") from exc

    pages: list[tuple[int, str]] = []
    all_text_parts: list[str] = []
    for index, page in enumerate(doc, start=1):
        page_text = clean_whitespace(page.get_text("text"))
        if page_text:
            pages.append((index, page_text))
            all_text_parts.append(page_text)

    page_count = doc.page_count
    doc.close()

    full_text = clean_whitespace("\n\n".join(all_text_parts))
    if not full_text:
        raise SourceExtractionError(
            "No selectable text found in this PDF. It may be scanned/image-only. OCR is not implemented in this MVP."
        )

    settings = get_settings()
    if len(full_text) < settings.min_source_text_chars:
        raise SourceExtractionError("PDF has too little extractable text to build a useful knowledgebase.")

    warnings: list[str] = []
    return PdfExtractionResult(
        title=filename or "PDF Document",
        pages=pages,
        page_count=page_count,
        text=full_text,
        warnings=warnings,
    )
