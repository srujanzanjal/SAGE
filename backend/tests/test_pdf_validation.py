import pytest

from app.services.pdf_extractor import validate_pdf_upload
from app.utils.exceptions import UnsupportedFileError


def test_rejects_unsupported_file_type():
    with pytest.raises(UnsupportedFileError):
        validate_pdf_upload("notes.txt", "text/plain", b"hello")


def test_accepts_pdf_signature_even_octet_stream():
    validate_pdf_upload("upload.bin", "application/octet-stream", b"%PDF-1.7\n...")
