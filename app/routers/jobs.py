"""Endpoints for creating generation jobs and checking their progress."""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_generated_dir
from app.database import get_db, get_session_factory
from app.models import (
    Certificate,
    CertificateStatus,
    GenerationJob,
    JobStatus,
    new_id,
)
from app.schemas import (
    CertificateOut,
    JobCreatedResponse,
    JobCreateRequest,
    JobStatusResponse,
)
from app.services.job_processor import process_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post(
    "/",
    response_model=JobCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_job(
    payload: JobCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    session_factory: sessionmaker = Depends(get_session_factory),
    output_dir: Path = Depends(get_generated_dir),
) -> JobCreatedResponse:
    """Validate the request, store the job, and generate PDFs in the background.

    202 Accepted is used because the work is not finished when we respond.
    """
    job = GenerationJob(
        id=new_id(),
        course_name=payload.course_name,
        issue_date=payload.issue_date,
        status=JobStatus.PENDING.value,
        total=len(payload.recipients),
        successful=0,
        failed=0,
    )
    job.certificates = [
        Certificate(
            id=new_id(),
            position=index,
            recipient_name=recipient.name,
            recipient_email=str(recipient.email),
            status=CertificateStatus.PENDING.value,
        )
        for index, recipient in enumerate(payload.recipients)
    ]

    # One commit stores the job and all of its certificates atomically: either
    # the whole job exists or nothing does.
    db.add(job)
    db.commit()

    # Runs after the response has been sent (see README: BackgroundTasks).
    background_tasks.add_task(process_job, job.id, session_factory, output_dir)

    return JobCreatedResponse(
        job_id=job.id,
        status=job.status,
        total=job.total,
        successful=job.successful,
        failed=job.failed,
    )


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobStatusResponse:
    """Return job progress plus one entry per certificate."""
    job = db.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    certificates = [
        CertificateOut(
            id=certificate.id,
            recipient_name=certificate.recipient_name,
            email=certificate.recipient_email,
            status=certificate.status,
            # Only successful certificates can be downloaded.
            download_url=(
                f"/api/certificates/{certificate.id}"
                if certificate.status == CertificateStatus.COMPLETED.value
                else None
            ),
            error=certificate.error_message,
        )
        for certificate in job.certificates
    ]

    return JobStatusResponse(
        job_id=job.id,
        course_name=job.course_name,
        issue_date=job.issue_date,
        status=job.status,
        total=job.total,
        successful=job.successful,
        failed=job.failed,
        created_at=job.created_at,
        completed_at=job.completed_at,
        certificates=certificates,
    )