"""Downloading certificates, including error cases and path traversal."""

import pytest

from app.models import Certificate


def _create_completed_job(client, make_payload, count=1):
    job_id = client.post("/api/jobs/", json=make_payload(count)).json()["job_id"]
    return client.get(f"/api/jobs/{job_id}").json()


def test_download_returns_the_pdf(client, make_payload):
    job = _create_completed_job(client, make_payload, count=2)
    certificate = job["certificates"][0]

    response = client.get(certificate["download_url"])

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert certificate["id"] in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")
    assert b"Student 1" in response.content


def test_each_certificate_downloads_its_own_recipient(client, make_payload):
    job = _create_completed_job(client, make_payload, count=2)

    first = client.get(job["certificates"][0]["download_url"]).content
    second = client.get(job["certificates"][1]["download_url"]).content

    assert b"Student 1" in first and b"Student 2" not in first
    assert b"Student 2" in second and b"Student 1" not in second


def test_unknown_certificate_returns_404(client):
    response = client.get("/api/certificates/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Certificate not found"}


def test_pending_certificate_returns_409(client, session_factory, make_job):
    make_job(["Alice"])
    with session_factory() as db:
        certificate_id = db.query(Certificate).one().id

    response = client.get(f"/api/certificates/{certificate_id}")

    assert response.status_code == 409
    assert "not ready" in response.json()["detail"]


def test_failed_certificate_returns_410_with_reason(client, make_payload):
    payload = make_payload(1)
    payload["recipients"][0]["name"] = "Ravi कुमार"
    job_id = client.post("/api/jobs/", json=payload).json()["job_id"]
    certificate = client.get(f"/api/jobs/{job_id}").json()["certificates"][0]

    response = client.get(f"/api/certificates/{certificate['id']}")

    assert response.status_code == 410
    assert "generation failed" in response.json()["detail"]
    assert "cannot render" in response.json()["detail"]


def test_missing_file_on_disk_returns_404(client, generated_dir, make_payload):
    job = _create_completed_job(client, make_payload)
    for pdf in generated_dir.glob("*.pdf"):
        pdf.unlink()

    response = client.get(job["certificates"][0]["download_url"])

    assert response.status_code == 404
    assert response.json() == {"detail": "Certificate file not found"}


@pytest.mark.parametrize("style", ["absolute", "dotdot"])
def test_files_outside_generated_dir_are_never_served(
    client, session_factory, generated_dir, make_payload, style
):
    secret = generated_dir.parent / "secret.txt"
    secret.write_text("top secret")
    job = _create_completed_job(client, make_payload)
    certificate_id = job["certificates"][0]["id"]

    # Simulate a tampered/corrupted database row pointing outside the folder.
    tampered = str(secret) if style == "absolute" else str(generated_dir / ".." / "secret.txt")
    with session_factory() as db:
        db.get(Certificate, certificate_id).file_path = tampered
        db.commit()

    response = client.get(f"/api/certificates/{certificate_id}")

    assert response.status_code == 404
    assert b"top secret" not in response.content