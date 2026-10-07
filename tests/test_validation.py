"""Input validation: bad requests are rejected with 422 and create nothing."""

import pytest

from app.models import GenerationJob
from app.schemas import MAX_RECIPIENTS

MISSING = object()  # sentinel meaning "remove this key from the payload"

GOOD_RECIPIENT = {"name": "Alice", "email": "alice@example.com"}

INVALID_CASES = {
    "empty_recipients": {"recipients": []},
    "missing_recipients": {"recipients": MISSING},
    "too_many_recipients": {
        "recipients": [
            {"name": f"N{i}", "email": f"n{i}@example.com"}
            for i in range(MAX_RECIPIENTS + 1)
        ]
    },
    "empty_name": {"recipients": [{"name": "", "email": "a@example.com"}]},
    "whitespace_name": {"recipients": [{"name": "   ", "email": "a@example.com"}]},
    "name_too_long": {"recipients": [{"name": "A" * 101, "email": "a@example.com"}]},
    "name_with_newline": {
        "recipients": [{"name": "Bad\nName", "email": "a@example.com"}]
    },
    "invalid_email": {"recipients": [{"name": "Alice", "email": "not-an-email"}]},
    "missing_email": {"recipients": [{"name": "Alice"}]},
    "empty_course": {"course_name": ""},
    "whitespace_course": {"course_name": "   "},
    "course_too_long": {"course_name": "C" * 121},
    "missing_course": {"course_name": MISSING},
    "impossible_date": {"issue_date": "2026-13-45"},
    "garbage_date": {"issue_date": "not-a-date"},
    "missing_date": {"issue_date": MISSING},
}


@pytest.mark.parametrize(
    "overrides", INVALID_CASES.values(), ids=INVALID_CASES.keys()
)
def test_invalid_request_is_rejected_and_creates_no_job(
    client, session_factory, make_payload, overrides
):
    payload = make_payload(1)
    for key, value in overrides.items():
        if value is MISSING:
            payload.pop(key)
        else:
            payload[key] = value

    response = client.post("/api/jobs/", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"]
    with session_factory() as db:
        assert db.query(GenerationJob).count() == 0


def test_one_invalid_recipient_rejects_the_whole_request_and_points_to_it(
    client, session_factory, make_payload
):
    payload = make_payload(3)
    payload["recipients"][1]["email"] = "broken-email"

    response = client.post("/api/jobs/", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == [
        "body",
        "recipients",
        1,
        "email",
    ]
    with session_factory() as db:
        assert db.query(GenerationJob).count() == 0


def test_malformed_json_is_rejected(client):
    response = client.post(
        "/api/jobs/",
        content="{not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_names_and_course_are_trimmed(client, make_payload):
    payload = make_payload(1, course_name="  Python Basics  ")
    payload["recipients"] = [{"name": "  Alice  ", "email": "alice@example.com"}]

    job_id = client.post("/api/jobs/", json=payload).json()["job_id"]
    body = client.get(f"/api/jobs/{job_id}").json()

    assert body["course_name"] == "Python Basics"
    assert body["certificates"][0]["recipient_name"] == "Alice"


def test_accented_names_are_accepted_and_generated(client, make_payload):
    payload = make_payload(1)
    payload["recipients"] = [{"name": "José Müller", "email": "jose@example.com"}]

    job_id = client.post("/api/jobs/", json=payload).json()["job_id"]
    body = client.get(f"/api/jobs/{job_id}").json()

    assert body["status"] == "COMPLETED"
    assert body["certificates"][0]["recipient_name"] == "José Müller"