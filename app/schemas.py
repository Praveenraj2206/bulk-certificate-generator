"""Pydantic schemas: request validation and response shapes."""

from datetime import date, datetime
from typing import Annotated, Optional

from pydantic import (
    AfterValidator,
    BaseModel,
    EmailStr,
    Field,
    StringConstraints,
)

from app.models import CertificateStatus, JobStatus

MAX_RECIPIENTS = 1000  # sensible cap for a single request
MAX_NAME_LENGTH = 100
MAX_COURSE_NAME_LENGTH = 120


def _reject_control_characters(value: str) -> str:
    """Newlines/tabs would break the single-line layout of the certificate."""
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("must not contain control characters")
    return value


# Strip surrounding whitespace first, then enforce length, then check characters.
RecipientName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=MAX_NAME_LENGTH
    ),
    AfterValidator(_reject_control_characters),
]

CourseName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=MAX_COURSE_NAME_LENGTH
    ),
    AfterValidator(_reject_control_characters),
]


# ----------------------------- Requests -----------------------------


class RecipientIn(BaseModel):
    name: RecipientName
    email: EmailStr


class JobCreateRequest(BaseModel):
    course_name: CourseName
    issue_date: date  # Pydantic rejects impossible dates such as 2026-13-45
    recipients: list[RecipientIn] = Field(min_length=1, max_length=MAX_RECIPIENTS)


# ----------------------------- Responses -----------------------------


class JobCreatedResponse(BaseModel):
    job_id: str
    status: JobStatus
    total: int
    successful: int
    failed: int


class CertificateOut(BaseModel):
    id: str
    recipient_name: str
    email: str
    status: CertificateStatus
    download_url: Optional[str] = None  # only set when status == COMPLETED
    error: Optional[str] = None  # only set when status == FAILED


class JobStatusResponse(BaseModel):
    job_id: str
    course_name: str
    issue_date: date
    status: JobStatus
    total: int
    successful: int
    failed: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    certificates: list[CertificateOut]