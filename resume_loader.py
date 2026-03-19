import os
import re

from pypdf import PdfReader


class ResumeLoadError(RuntimeError):
    """Raised when the resume PDF cannot be read into usable text."""


def normalize_resume_text(text: str) -> str:
    """Collapse noisy whitespace from extracted PDF text."""
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_resume_text(pdf_path: str) -> str:
    """Read a PDF resume and return normalized plain text."""
    if not pdf_path:
        raise ResumeLoadError("RESUME_PDF_PATH is not set.")

    expanded_path = os.path.abspath(os.path.expanduser(pdf_path))
    if not os.path.isfile(expanded_path):
        raise ResumeLoadError(f"Resume PDF not found: {expanded_path}")

    try:
        reader = PdfReader(expanded_path)
    except Exception as exc:
        raise ResumeLoadError(f"Could not open resume PDF: {expanded_path}") from exc

    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception as exc:
            raise ResumeLoadError("Failed to extract text from the resume PDF.") from exc

    resume_text = normalize_resume_text("\n\n".join(pages))
    if not resume_text:
        raise ResumeLoadError("Resume PDF did not contain extractable text.")

    return resume_text
