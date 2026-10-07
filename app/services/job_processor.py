"""Background worker: generates every certificate of one job.

Rules that matter:
* One bad certificate never stops the others (try/except around each one).
* Progress is committed after every certificate, so clients can poll it.
* An unexpected job-level error marks the job FAILED instead of leaving it
  stuck in PROCESSING forever.
"""

import logging
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import (
    Certificate,
    CertificateStatus,
    GenerationJob,
    JobStatus,
    utcnow,
)
from app.services.certificate_service import (
    CertificateGenerationError,
    generate_certificate_pdf,
)

logger = logging.getLogger(__name__)


def process_job(
    job_id: str, session_factory: Callable[[], Session], output_dir: Path
) -> None:
    """Entry point used by FastAPI BackgroundTasks. Never raises."""
    # The request's session is closed by now, so the worker owns its own session.
    db = session_factory()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            logger.error("Job %s not found; nothing to process", job_id)
            return
        if job.status != JobStatus.PENDING.value:
            # Protects against processing the same job twice.
            logger.warning("Job %s is %s, not PENDING; skipping", job_id, job.status)
            return

        job.status = JobStatus.PROCESSING.value
        db.commit()

        for certificate in list(job.certificates):
            _process_certificate(db, job, certificate, output_dir)

        _finish_job(db, job)
    except Exception:
        # Something outside a single certificate went wrong (e.g. DB error).
        logger.exception("Job %s failed unexpectedly", job_id)
        db.rollback()
        _abort_job(db, job_id)
    finally:
        db.close()


def _process_certificate(
    db: Session, job: GenerationJob, certificate: Certificate, output_dir: Path
) -> None:
    """Generate one PDF. Any failure is recorded on the certificate, not raised."""
    try:
        path = generate_certificate_pdf(
            certificate_id=certificate.id,
            recipient_name=certificate.recipient_name,
            course_name=job.course_name,
            issue_date=job.issue_date,
            output_dir=output_dir,
        )
    except CertificateGenerationError as exc:
        # Expected failure: the message was written to be shown to clients.
        _mark_failed(job, certificate, str(exc))
    except Exception as exc:
        # Unexpected failure: log the details, but store only a generic message
        # so internals never leak through the API.
        logger.exception("Unexpected error for certificate %s", certificate.id)
        _mark_failed(
            job,
            certificate,
            f"Unexpected error while generating certificate ({type(exc).__name__})",
        )
    else:
        certificate.status = CertificateStatus.COMPLETED.value
        certificate.file_path = str(path)
        job.successful += 1

    certificate.completed_at = utcnow()
    db.commit()  # commit per certificate => visible progress + earlier work is kept


def _mark_failed(job: GenerationJob, certificate: Certificate, message: str) -> None:
    certificate.status = CertificateStatus.FAILED.value
    certificate.error_message = message
    job.failed += 1


def _finish_job(db: Session, job: GenerationJob) -> None:
    """Pick the final job status from the per-certificate results."""
    if job.failed == 0:
        job.status = JobStatus.COMPLETED.value
    elif job.successful == 0:
        job.status = JobStatus.FAILED.value
    else:
        job.status = JobStatus.COMPLETED_WITH_ERRORS.value
    job.completed_at = utcnow()
    db.commit()


def _abort_job(db: Session, job_id: str) -> None:
    """Best-effort cleanup after an unexpected error: mark the job FAILED.

    Certificates that were already generated keep their COMPLETED state; the
    ones that never ran are marked FAILED so nothing stays PENDING forever.
    """
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            return
        now = utcnow()
        for certificate in job.certificates:
            if certificate.status == CertificateStatus.PENDING.value:
                certificate.status = CertificateStatus.FAILED.value
                certificate.error_message = (
                    "Job was aborted before this certificate was generated"
                )
                certificate.completed_at = now
        # Recount from the rows so the totals are always consistent.
        job.successful = sum(
            c.status == CertificateStatus.COMPLETED.value for c in job.certificates
        )
        job.failed = sum(
            c.status == CertificateStatus.FAILED.value for c in job.certificates
        )
        job.status = JobStatus.FAILED.value
        job.completed_at = now
        db.commit()
    except Exception:
        logger.exception("Could not mark job %s as failed", job_id)
        db.rollback()