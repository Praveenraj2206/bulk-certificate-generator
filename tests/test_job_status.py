"""Job status and progress reporting."""

from app.models import GenerationJob
from app.services import job_processor
from app.services.job_processor import process_job


def test_unknown_job_returns_404(client):
    response = client.get("/api/jobs/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found"}


def test_pending_job_has_no_results_yet(client, make_job):
    job_id = make_job(["Alice", "Bob"])

    body = client.get(f"/api/jobs/{job_id}").json()

    assert body["status"] == "PENDING"
    assert (body["total"], body["successful"], body["failed"]) == (2, 0, 0)
    assert body["completed_at"] is None
    assert [c["status"] for c in body["certificates"]] == ["PENDING", "PENDING"]
    assert all(c["download_url"] is None for c in body["certificates"])


def test_completed_job_lists_every_certificate_with_download_url(client, make_payload):
    job_id = client.post("/api/jobs/", json=make_payload(3)).json()["job_id"]

    body = client.get(f"/api/jobs/{job_id}").json()

    assert body["job_id"] == job_id
    assert body["course_name"] == "Python Backend Development"
    assert body["issue_date"] == "2026-10-07"
    assert body["status"] == "COMPLETED"
    assert body["successful"] + body["failed"] == body["total"] == 3
    assert body["completed_at"] is not None
    # Same order as the request.
    assert [c["recipient_name"] for c in body["certificates"]] == [
        "Student 1",
        "Student 2",
        "Student 3",
    ]
    for certificate in body["certificates"]:
        assert certificate["status"] == "COMPLETED"
        assert certificate["download_url"] == f"/api/certificates/{certificate['id']}"
        assert certificate["error"] is None


def test_status_moves_through_processing_and_progress_is_visible(
    session_factory, generated_dir, make_job, monkeypatch
):
    job_id = make_job(["Alice", "Bob", "Carol"])
    snapshots = []
    real_generate = job_processor.generate_certificate_pdf

    def spy(**kwargs):
        # Look at the database from a *separate* session, like a polling client.
        with session_factory() as db:
            job = db.get(GenerationJob, job_id)
            snapshots.append((job.status, job.successful, job.failed))
        return real_generate(**kwargs)

    monkeypatch.setattr(job_processor, "generate_certificate_pdf", spy)

    process_job(job_id, session_factory, generated_dir)

    # Before each certificate the job is PROCESSING and the counters have
    # advanced by exactly the certificates finished so far.
    assert snapshots == [
        ("PROCESSING", 0, 0),
        ("PROCESSING", 1, 0),
        ("PROCESSING", 2, 0),
    ]
    with session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert job.status == "COMPLETED"
        assert (job.successful, job.failed) == (3, 0)
        assert job.completed_at is not None