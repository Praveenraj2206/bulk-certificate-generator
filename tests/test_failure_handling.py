"""One failing certificate must not stop the rest of the job."""

from app.models import Certificate, GenerationJob
from app.services import job_processor
from app.services.job_processor import process_job


def _install_flaky_generator(monkeypatch, bad_name="Bad User"):
    """Make PDF generation blow up for one recipient and work for the others."""
    real_generate = job_processor.generate_certificate_pdf

    def flaky(**kwargs):
        if kwargs["recipient_name"] == bad_name:
            raise RuntimeError("boom: secret internal detail")
        return real_generate(**kwargs)

    monkeypatch.setattr(job_processor, "generate_certificate_pdf", flaky)


def test_single_failure_does_not_stop_other_certificates(
    client, generated_dir, make_payload, monkeypatch
):
    _install_flaky_generator(monkeypatch)
    payload = make_payload(5)
    payload["recipients"][2]["name"] = "Bad User"  # certificate #3 of 5

    job_id = client.post("/api/jobs/", json=payload).json()["job_id"]
    body = client.get(f"/api/jobs/{job_id}").json()

    assert body["status"] == "COMPLETED_WITH_ERRORS"
    assert (body["total"], body["successful"], body["failed"]) == (5, 4, 1)
    statuses = [c["status"] for c in body["certificates"]]
    assert statuses == ["COMPLETED", "COMPLETED", "FAILED", "COMPLETED", "COMPLETED"]

    failed = body["certificates"][2]
    assert failed["recipient_name"] == "Bad User"
    assert failed["download_url"] is None
    assert "RuntimeError" in failed["error"]
    assert "boom" not in failed["error"]  # internal details are not exposed
    assert "secret" not in failed["error"]

    # Certificates after the failure were still generated.
    assert len(list(generated_dir.glob("*.pdf"))) == 4


def test_failed_certificates_cannot_be_downloaded(client, make_payload, monkeypatch):
    _install_flaky_generator(monkeypatch)
    payload = make_payload(2)
    payload["recipients"][0]["name"] = "Bad User"

    job_id = client.post("/api/jobs/", json=payload).json()["job_id"]
    body = client.get(f"/api/jobs/{job_id}").json()
    failed_id = body["certificates"][0]["id"]
    ok_id = body["certificates"][1]["id"]

    assert client.get(f"/api/certificates/{failed_id}").status_code == 410
    assert client.get(f"/api/certificates/{ok_id}").status_code == 200


def test_job_fails_when_every_certificate_fails(client, make_payload, monkeypatch):
    def always_fail(**kwargs):
        raise RuntimeError("nothing works")

    monkeypatch.setattr(job_processor, "generate_certificate_pdf", always_fail)

    job_id = client.post("/api/jobs/", json=make_payload(3)).json()["job_id"]
    body = client.get(f"/api/jobs/{job_id}").json()

    assert body["status"] == "FAILED"
    assert (body["successful"], body["failed"]) == (0, 3)
    assert all(c["status"] == "FAILED" for c in body["certificates"])


def test_name_the_font_cannot_render_fails_only_that_certificate(client, make_payload):
    # No mocking: a real, expected failure path of the PDF service.
    payload = make_payload(3)
    payload["recipients"][1]["name"] = "Ravi कुमार"

    job_id = client.post("/api/jobs/", json=payload).json()["job_id"]
    body = client.get(f"/api/jobs/{job_id}").json()

    assert body["status"] == "COMPLETED_WITH_ERRORS"
    assert [c["status"] for c in body["certificates"]] == [
        "COMPLETED",
        "FAILED",
        "COMPLETED",
    ]
    assert "cannot render" in body["certificates"][1]["error"]


def test_unexpected_job_level_error_marks_job_failed_and_keeps_finished_work(
    session_factory, generated_dir, make_job, monkeypatch
):
    job_id = make_job(["Alice", "Bob", "Carol"])
    real_process_certificate = job_processor._process_certificate
    calls = {"count": 0}

    def explode_on_second(db, job, certificate, output_dir):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("database exploded")  # not a per-certificate error
        real_process_certificate(db, job, certificate, output_dir)

    monkeypatch.setattr(job_processor, "_process_certificate", explode_on_second)

    process_job(job_id, session_factory, generated_dir)  # must not raise

    with session_factory() as db:
        job = db.get(GenerationJob, job_id)
        certificates = job.certificates
        assert job.status == "FAILED"
        assert job.completed_at is not None
        assert (job.successful, job.failed) == (1, 2)
        assert certificates[0].status == "COMPLETED"  # finished work is kept
        assert [c.status for c in certificates[1:]] == ["FAILED", "FAILED"]
        assert "aborted" in certificates[1].error_message
        assert not any(c.status == "PENDING" for c in certificates)


def test_processing_an_unknown_job_does_not_raise(session_factory, generated_dir):
    process_job("no-such-job", session_factory, generated_dir)


def test_processing_the_same_job_twice_does_not_duplicate_work(
    session_factory, generated_dir, make_job
):
    job_id = make_job(["Alice", "Bob", "Carol"])

    process_job(job_id, session_factory, generated_dir)
    process_job(job_id, session_factory, generated_dir)  # second call is a no-op

    with session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert (job.status, job.successful, job.failed) == ("COMPLETED", 3, 0)
        assert db.query(Certificate).count() == 3
    assert len(list(generated_dir.glob("*.pdf"))) == 3