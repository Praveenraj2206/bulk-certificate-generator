"""PDF rendering for the single predefined certificate template.

This module knows nothing about HTTP or the database: give it a name, a course
and a date, and it writes a PDF file and returns its path.
"""

import re
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PAGE_SIZE = landscape(A4)
NAVY = colors.HexColor("#1F3A5F")
GOLD = colors.HexColor("#B8860B")
GREY = colors.HexColor("#555555")

# Certificate ids become file names, so only allow characters that are safe in
# a path. UUIDs always match this pattern.
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class CertificateGenerationError(Exception):
    """A certificate could not be generated; the message is safe to show to clients."""


def format_issue_date(issue_date: date) -> str:
    """e.g. date(2026, 10, 7) -> 'October 7, 2026'."""
    return f"{issue_date:%B} {issue_date.day}, {issue_date.year}"


def _check_text(label: str, value: str) -> None:
    """Fail early, with a clear message, for text we cannot print.

    The built-in PDF fonts (Helvetica) only cover Western European characters
    (cp1252). Anything else would silently render as garbage, so we reject it
    for this one recipient instead of producing a wrong certificate.
    """
    if not value or not value.strip():
        raise CertificateGenerationError(f"{label} must not be empty")
    try:
        value.encode("cp1252")
    except UnicodeEncodeError:
        raise CertificateGenerationError(
            f"{label} contains characters that the certificate font cannot render"
        ) from None


def _fit_font_size(
    text: str, font_name: str, start_size: int, max_width: float, min_size: int = 8
) -> int:
    """Shrink the font until the text fits on the page (long names/courses)."""
    size = start_size
    while size > min_size and stringWidth(text, font_name, size) > max_width:
        size -= 1
    return size


def _draw_certificate(
    path: Path,
    recipient_name: str,
    course_name: str,
    issue_date: date,
    certificate_id: str,
) -> None:
    """Draw the one-page certificate onto `path`."""
    width, height = PAGE_SIZE
    # pageCompression=0 keeps the PDF text readable in the raw bytes, which lets
    # the tests assert that the recipient's name is really in the document.
    pdf = canvas.Canvas(str(path), pagesize=PAGE_SIZE, pageCompression=0)
    pdf.setTitle(f"Certificate of Completion - {recipient_name}")
    pdf.setAuthor("Bulk Certificate Generator")

    # Double border: thick navy outside, thin gold inside.
    pdf.setStrokeColor(NAVY)
    pdf.setLineWidth(6)
    pdf.rect(30, 30, width - 60, height - 60)
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1.5)
    pdf.rect(44, 44, width - 88, height - 88)

    center = width / 2
    text_width = width - 160  # keep text away from the border

    # Title
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 36)
    pdf.drawCentredString(center, height - 125, "CERTIFICATE OF COMPLETION")
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(2)
    pdf.line(center - 140, height - 145, center + 140, height - 145)

    # "presented to" + recipient name
    pdf.setFillColor(GREY)
    pdf.setFont("Helvetica-Oblique", 16)
    pdf.drawCentredString(center, height - 195, "This certificate is proudly presented to")

    name_size = _fit_font_size(recipient_name, "Helvetica-Bold", 40, text_width)
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", name_size)
    pdf.drawCentredString(center, height - 260, recipient_name)
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1)
    pdf.line(center - 250, height - 275, center + 250, height - 275)

    # "for successfully completing" + course name
    pdf.setFillColor(GREY)
    pdf.setFont("Helvetica-Oblique", 16)
    pdf.drawCentredString(center, height - 320, "for successfully completing")

    course_size = _fit_font_size(course_name, "Helvetica-Bold", 26, text_width)
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", course_size)
    pdf.drawCentredString(center, height - 365, course_name)

    # Issue date
    pdf.setFillColor(GREY)
    pdf.setFont("Helvetica", 16)
    pdf.drawCentredString(center, height - 425, f"Issued on: {format_issue_date(issue_date)}")

    # Footer with the id, so a printed certificate can be traced back.
    pdf.setFont("Helvetica", 9)
    pdf.drawCentredString(center, 62, f"Certificate ID: {certificate_id}")

    pdf.showPage()
    pdf.save()


def generate_certificate_pdf(
    *,
    certificate_id: str,
    recipient_name: str,
    course_name: str,
    issue_date: date,
    output_dir: Path,
) -> Path:
    """Create `<output_dir>/<certificate_id>.pdf` and return its path.

    Raises CertificateGenerationError for anything that prevents a valid PDF.
    The file is written to a temporary name and renamed at the end, so a crash
    never leaves a half-written certificate that looks valid.
    """
    if not _SAFE_ID.match(certificate_id):
        raise CertificateGenerationError("Invalid certificate id")
    _check_text("Recipient name", recipient_name)
    _check_text("Course name", course_name)

    output_dir = Path(output_dir)
    final_path = output_dir / f"{certificate_id}.pdf"
    temp_path = output_dir / f"{certificate_id}.pdf.part"

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        _draw_certificate(
            temp_path, recipient_name, course_name, issue_date, certificate_id
        )
        temp_path.replace(final_path)
    except Exception as exc:
        temp_path.unlink(missing_ok=True)
        # Keep the technical detail in the logs/exception chain, but give the
        # client a short message without file paths or stack traces.
        raise CertificateGenerationError(
            f"Could not create the PDF file ({type(exc).__name__})"
        ) from exc

    return final_path.resolve()