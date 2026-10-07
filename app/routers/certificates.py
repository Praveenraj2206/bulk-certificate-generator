"""Endpoint for downloading a generated certificate PDF."""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_generated_dir
from app.database import get_db
from app.models import Certificate, CertificateStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/certificates", tags=["certificates"])


def _resolve_inside(stored_path: Optional[str], root: Path) -> Optional[Path]:
    """Return the file path only if it really lives inside the generated folder.

    Defence in depth against path traversal: the path normally comes from our
    own code (`<uuid>.pdf`), but we never serve a file just because the database
    says so. `resolve()` collapses `..` and symlinks before the check.
    """
    if not stored_path:
        return None
    candidate = Path(stored_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        logger.warning("Refusing to serve file outside generated dir: %s", candidate)
        return None
    return candidate


@router.get(
    "/{certificate_id}",
    response_class=FileResponse,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "The PDF file"},
        404: {"description": "Certificate (or its file) not found"},
        409: {"description": "Certificate is not generated yet"},
        410: {"description": "Certificate generation failed permanently"},
    },
)
def download_certificate(
    certificate_id: str,
    db: Session = Depends(get_db),
    generated_dir: Path = Depends(get_generated_dir),
) -> FileResponse:
    """Download one certificate as a PDF."""
    certificate = db.get(Certificate, certificate_id)
    if certificate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Certificate not found"
        )

    # 410 Gone: this certificate failed and will never exist (a retry would be a
    # new job). The stored error text is already sanitised by the processor.
    if certificate.status == CertificateStatus.FAILED.value:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Certificate generation failed: {certificate.error_message}",
        )

    # 409 Conflict: not in a downloadable state *yet*; the client can poll the job.
    if certificate.status != CertificateStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Certificate is not ready yet. Check the job status and retry.",
        )

    file_path = _resolve_inside(certificate.file_path, generated_dir)
    if file_path is None or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate file not found",
        )

    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=f"certificate_{certificate.id}.pdf",
    )