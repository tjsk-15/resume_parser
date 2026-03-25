"""
PDF text extraction service.

Uses PyMuPDF (fitz) for high-quality text extraction from resume PDFs.
Falls back to pdfminer if fitz is unavailable.
"""

import frappe
import os


def extract_text_from_pdf(file_url: str) -> str:
    """
    Extract text content from a PDF file attached to a Frappe document.

    Args:
        file_url: The Frappe file URL (e.g., /files/resume.pdf or /private/files/resume.pdf)

    Returns:
        Extracted text string

    Raises:
        frappe.ValidationError: If the file cannot be found or read
    """
    file_path = _resolve_file_path(file_url)

    if not os.path.exists(file_path):
        frappe.throw(f"Resume file not found: {file_url}")

    text = ""

    # Try PyMuPDF first (best quality)
    try:
        text = _extract_with_fitz(file_path)
    except ImportError:
        frappe.logger("resume_parser").warning("PyMuPDF not installed, trying pdfminer")
        try:
            text = _extract_with_pdfminer(file_path)
        except ImportError:
            frappe.throw(
                "No PDF library available. Install PyMuPDF: pip install PyMuPDF"
            )

    if not text or len(text.strip()) < 20:
        frappe.logger("resume_parser").warning(
            f"Very little text extracted from {file_url} ({len(text.strip())} chars). "
            "The PDF may be image-based. OCR is not currently supported."
        )

    return text.strip()


def _resolve_file_path(file_url: str) -> str:
    """Convert a Frappe file URL to an absolute filesystem path."""
    if file_url.startswith("/private/files/"):
        return frappe.get_site_path("private", "files", file_url.split("/private/files/")[-1])
    elif file_url.startswith("/files/"):
        return frappe.get_site_path("public", "files", file_url.split("/files/")[-1])
    else:
        # Try as absolute path
        return file_url


def _extract_with_fitz(file_path: str) -> str:
    """Extract text using PyMuPDF (fitz)."""
    import fitz  # PyMuPDF

    text_parts = []
    with fitz.open(file_path) as doc:
        for page in doc:
            text_parts.append(page.get_text())

    return "\n".join(text_parts)


def _extract_with_pdfminer(file_path: str) -> str:
    """Extract text using pdfminer.six as fallback."""
    from pdfminer.high_level import extract_text

    return extract_text(file_path)
