"""Upload validation, malware scanning and text extraction for PDF and DOCX.

Uploaded content is untrusted: we never execute macros or embedded content, never trust the client's
filename or content type, and bound resource usage (size, page count, archive expansion).
"""

from __future__ import annotations

import io
import logging
import re
import socket
import struct
import unicodedata
import zipfile
from dataclasses import dataclass

from careerpilot.config import get_settings
from careerpilot.errors import AppError, ServiceUnavailable

logger = logging.getLogger(__name__)

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_ALLOWED_EXT = {".pdf": PDF_MIME, ".docx": DOCX_MIME}
_MAX_DOCX_UNCOMPRESSED = 50 * 1024 * 1024
_MAX_DOCX_ENTRIES = 2000


class DocumentRejected(AppError):
    status_code = 422
    code = "document_rejected"


class ExtractionFailed(Exception):
    """Raised during async processing; `user_message` is safe to show."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


@dataclass(frozen=True)
class ValidatedUpload:
    mime_type: str
    safe_filename: str


def sanitize_filename(name: str) -> str:
    name = unicodedata.normalize("NFKC", name or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    return (name or "document")[:200]


def validate_upload(filename: str, data: bytes) -> ValidatedUpload:
    s = get_settings()
    if not data:
        raise DocumentRejected("The file is empty.")
    if len(data) > s.max_upload_mb * 1024 * 1024:
        raise DocumentRejected(
            f"The file exceeds the {s.max_upload_mb} MB limit.", code="file_too_large", status_code=413
        )
    safe = sanitize_filename(filename)
    ext = "." + safe.rsplit(".", 1)[-1].lower() if "." in safe else ""
    if ext not in _ALLOWED_EXT:
        raise DocumentRejected("Only PDF and DOCX files are supported.", code="unsupported_file_type")

    if ext == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise DocumentRejected("The file content is not a valid PDF.", code="file_type_mismatch")
        if re.search(rb"/Encrypt\b", data[-4096:]) or re.search(rb"/Encrypt\s", data[:4096]):
            raise DocumentRejected("Password-protected PDFs are not supported.", code="encrypted_document")
        if re.search(rb"/(JavaScript|JS|Launch|EmbeddedFile)\b", data):
            raise DocumentRejected(
                "PDFs with embedded scripts or attachments are not accepted.", code="suspicious_document"
            )
    else:
        if not data.startswith(b"PK\x03\x04"):
            raise DocumentRejected("The file content is not a valid DOCX document.", code="file_type_mismatch")
        _validate_docx_container(data)
    return ValidatedUpload(_ALLOWED_EXT[ext], safe)


def _validate_docx_container(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            if len(infos) > _MAX_DOCX_ENTRIES or sum(i.file_size for i in infos) > _MAX_DOCX_UNCOMPRESSED:
                raise DocumentRejected("The document is too large when expanded.", code="suspicious_document")
            names = {i.filename for i in infos}
            if "word/document.xml" not in names or "[Content_Types].xml" not in names:
                raise DocumentRejected("The file content is not a valid DOCX document.", code="file_type_mismatch")
            if any(n.lower().endswith("vbaproject.bin") for n in names):
                raise DocumentRejected("Macro-enabled documents are not accepted.", code="suspicious_document")
            content_types = zf.read("[Content_Types].xml")
            if b"macroEnabled" in content_types:
                raise DocumentRejected("Macro-enabled documents are not accepted.", code="suspicious_document")
    except zipfile.BadZipFile as exc:
        raise DocumentRejected("The document is corrupt.", code="corrupt_document") from exc


def scan_for_malware(data: bytes) -> str:
    """Returns 'clean', 'not_scanned' (scanner disabled) or raises DocumentRejected if infected."""
    s = get_settings()
    if s.malware_scanner == "none":
        return "not_scanned"
    try:
        with socket.create_connection((s.clamav_host, s.clamav_port), timeout=30) as sock:
            sock.sendall(b"zINSTREAM\0")
            for i in range(0, len(data), 8192):
                chunk = data[i : i + 8192]
                sock.sendall(struct.pack("!L", len(chunk)) + chunk)
            sock.sendall(struct.pack("!L", 0))
            reply = sock.recv(4096).decode(errors="replace")
    except OSError as exc:
        # Fail closed: when scanning is configured, an unavailable scanner blocks the upload.
        raise ServiceUnavailable("File scanning is temporarily unavailable. Please try again later.") from exc
    if "FOUND" in reply:
        logger.warning("malware_detected")
        raise DocumentRejected("The file was rejected by the malware scanner.", code="malware_detected")
    if not reply.strip().endswith("OK"):
        raise ServiceUnavailable("File scanning failed. Please try again later.")
    return "clean"


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL.sub(" ", text).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("•", "•")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    out: list[str] = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()[:200_000]


def extract_pdf(data: bytes) -> tuple[str, int]:
    import pdfplumber

    s = get_settings()
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > s.max_pdf_pages:
                raise ExtractionFailed(f"Resumes longer than {s.max_pdf_pages} pages are not supported.")
            texts = [(page.extract_text() or "") for page in pdf.pages]
            return "\n".join(texts), len(pdf.pages)
    except ExtractionFailed:
        raise
    except Exception as exc:
        raise ExtractionFailed("The PDF could not be read. It may be corrupt or encrypted.") from exc


def extract_docx(data: bytes) -> str:
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise ExtractionFailed("The DOCX file could not be read.") from exc
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells if cell.text.strip()))
    return "\n".join(parts)


def ocr_pdf(data: bytes) -> str:
    s = get_settings()
    if s.ocr_provider == "none":
        raise ExtractionFailed(
            "This looks like a scanned document. OCR is not enabled on this server; "
            "please upload a text-based PDF or DOCX."
        )
    try:
        import pypdfium2 as pdfium
        import pytesseract
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ExtractionFailed("OCR is not available on this server.") from exc
    pdf = pdfium.PdfDocument(data)
    texts = []
    for i in range(min(len(pdf), s.max_pdf_pages)):
        image = pdf[i].render(scale=2).to_pil()
        texts.append(pytesseract.image_to_string(image, timeout=60))
    return "\n".join(texts)


def extract_text(data: bytes, mime_type: str) -> tuple[str, str, int | None]:
    """Returns (normalized_text, method, page_count)."""
    s = get_settings()
    if mime_type == PDF_MIME:
        text, pages = extract_pdf(data)
        method = "native_pdf"
        if len(text.strip()) < s.min_text_chars_before_ocr:
            text, method = ocr_pdf(data), "ocr"
        normalized = normalize_text(text)
        if len(normalized) < 50:
            raise ExtractionFailed("No readable text was found in this document.")
        return normalized, method, pages
    if mime_type == DOCX_MIME:
        normalized = normalize_text(extract_docx(data))
        if len(normalized) < 50:
            raise ExtractionFailed("No readable text was found in this document.")
        return normalized, "docx", None
    raise ExtractionFailed("Unsupported document type.")
