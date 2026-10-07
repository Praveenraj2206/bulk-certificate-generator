"""Shared fixtures.

Every test gets its own temporary SQLite file and its own temporary output
folder, so the real `certificates.db` and `generated/` are never touched.

Background tasks: Starlette's TestClient waits for them to finish before
`client.post(...)` returns. That makes the tests deterministic with no sleeps.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401  (registers tables on Base)
from app.config import get_generated_dir
from app.database import Base, get_db, get_session_factory
from app.main import app
from app.models import Certificate, CertificateStatus, GenerationJob, JobStatus, new_id


@pytest.fixture()
def session_factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture()
def generated_dir(tmp_path):
    directory = tmp_path / "generated"
    directory.mkdir()
    return directory


@pytest.fixture()
def client(session_factory, generated_dir):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_generated_dir] = lambda: generated_dir
    # No `with` block on purpose: it would run the startup hook on the real DB.
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def make_payload():
    """Build a valid request body with `count` recipients."""

    def _make(
        count: int = 2,
        course_name: str = "Python Backend Development",
        issue_date: str = "2026-10-07",
    ) -> dict:
        return {
            "course_name": course_name,
            "issue_date": issue_date,
            "recipients": [
                {"name": f"Student {i}", "email": f"student{i}@example.com"}
                for i in range(1, count + 1)
            ],
        }

    return _make


@pytest.fixture()
def make_job(session_factory):
    """Insert a PENDING job straight into the DB (no background processing).

    Lets tests call `process_job` themselves and inspect intermediate state.
    """

    def _make(names=("Alice", "Bob", "Carol")) -> str:
        with session_factory() as db:
            job = GenerationJob(
                id=new_id(),
                course_name="Data Engineering",
                issue_date=date(2026, 10, 7),
                status=JobStatus.PENDING.value,
                total=len(names),
                successful=0,
                failed=0,
            )
            job.certificates = [
                Certificate(
                    id=new_id(),
                    position=index,
                    recipient_name=name,
                    recipient_email=f"{name.lower().replace(' ', '.')}@example.com",
                    status=CertificateStatus.PENDING.value,
                )
                for index, name in enumerate(names)
            ]
            db.add(job)
            db.commit()
            return job.id

    return _make