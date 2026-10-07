"""Creating generation jobs."""

import uuid
from datetime import date

from app.models import Certificate, GenerationJob
from app.routers import jobs as jobs_router


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_job_returns_accepted_with_pending_summary(client, make_payload):
    response = client.post("/api/jobs/", json=make_payload(3))

    assert response.status_code == 202
    body = response.json()
    uuid.UUID(body["job_id"])  # raises if it is not a valid UUID
    assert body == {
        "job_id": body["job_id"],
        "status": "PENDING",  # the response is built before the background work runs
        "total": 3,
        "successful": 0,
        "failed": 0,
    }


def test_create_job_stores_job_and_all_recipients(client, session_factory, make_payload):
    job_id = client.post("/api/jobs/", json=make_payload(3)).json()["job_id"]

    with session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert job.course_name == "Python Backend Development"
        assert job.issue_date == date(2026, 10, 7)
        assert job.total == 3
        assert [c.recipient_name for c in job.certificates] == [
            "Student 1",
            "Student 2",
            "Student 3",
        ]
        assert [c.recipient_email for c in job.certificates] == [
            "student1@example.com",
            "student2@example.com",
            "student3@example.com",
        ]


def test_generation_is_scheduled_in_background_not_inline(
    client, session_factory, make_payload, monkeypatch
):
    calls = []
    monkeypatch.setattr(
        jobs_router, "process_job", lambda *args: calls.append(args)
    )

    response = client.post("/api/jobs/", json=make_payload(2))
    job_id = response.json()["job_id"]

    # The endpoint scheduled exactly one background call for this job...
    assert len(calls) == 1
    assert calls[0][0] == job_id
    # ...and did not generate anything itself.
    with session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert job.status == "PENDING"
        assert db.query(Certificate).filter_by(status="PENDING").count() == 2


def test_background_generation_completes_the_job(client, make_payload):
    job_id = client.post("/api/jobs/", json=make_payload(2)).json()["job_id"]

    body = client.get(f"/api/jobs/{job_id}").json()

    assert body["status"] == "COMPLETED"
    assert body["total"] == 2
    assert body["successful"] == 2
    assert body["failed"] == 0
    assert body["completed_at"] is not None