# Bulk Certificate Generator API

A FastAPI-based REST API for generating and retrieving certificates in bulk.

The application accepts a list of recipients for a course, processes certificate generation in the background, stores job and certificate information in SQLite, and generates downloadable PDF certificates using ReportLab.

---

## Features

- Bulk certificate generation for up to 1000 recipients
- REST API built with FastAPI
- Background job processing using FastAPI `BackgroundTasks`
- SQLite database using SQLAlchemy
- PDF certificate generation using ReportLab
- Individual certificate status tracking
- Job-level status tracking
- Per-certificate failure isolation
- Certificate download endpoint
- Input validation using Pydantic
- Protection against path traversal
- Temporary PDF files with atomic rename after successful generation
- Comprehensive automated test suite

---

## Project Structure

```text
bulk-certificate-generator/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── config.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── jobs.py
│   │   └── certificates.py
│   └── services/
│       ├── __init__.py
│       ├── certificate_service.py
│       └── job_processor.py
├── generated/
│   └── .gitkeep
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_jobs.py
│   ├── test_validation.py
│   ├── test_certificate_generation.py
│   ├── test_job_status.py
│   ├── test_failure_handling.py
│   └── test_certificate_download.py
├── .env.example
├── .gitignore
├── pytest.ini
├── requirements.txt
├── run_tests.bat
└── README.md
```

---

## Requirements

- Python 3.10+
- pip
- Git

The project uses:

- FastAPI
- Uvicorn
- SQLAlchemy
- Pydantic
- ReportLab
- pytest
- HTTPX

---

## 1. Project Setup

Clone the repository:

```bash
git clone https://github.com/Praveenraj2206/bulk-certificate-generator.git
cd bulk-certificate-generator
```

Create a virtual environment (Windows / Git Bash):

```bash
python -m venv .venv
source .venv/Scripts/activate
```

If the virtual environment already exists:

```bash
source .venv/Scripts/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### Environment Configuration

The application has default values, but an `.env` file can be created when custom configuration is required.

Copy the example file:

```bash
cp .env.example .env
```

Default configuration:

```env
DATABASE_URL=sqlite:///./certificates.db
GENERATED_FILES_DIR=./generated
```

### Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | SQLAlchemy database connection URL | `sqlite:///./certificates.db` |
| `GENERATED_FILES_DIR` | Directory where generated PDF certificates are stored | `./generated` |

The real `.env` file is ignored by Git and should not contain credentials or sensitive information that should be committed.

---

## 2. Run the Application

Start the FastAPI application with Uvicorn:

```bash
python -m uvicorn app.main:app --reload
```

The API will be available at:

```text
http://127.0.0.1:8000
```

API documentation (Swagger UI):

```text
http://127.0.0.1:8000/docs
```

Alternative ReDoc documentation:

```text
http://127.0.0.1:8000/redoc
```

Health check:

```text
GET /api/health
```

Example:

```bash
curl http://127.0.0.1:8000/api/health
```

Expected response:

```json
{
  "status": "ok"
}
```

---

## 3. Run Tests

Make sure the virtual environment is activated.

Run the complete test suite:

```bash
pytest -q
```

The test suite covers:

- Job creation
- Request validation
- Certificate generation
- Job status tracking
- Failure handling
- Certificate download
- API behavior

The project is designed so that individual certificate failures do not stop the processing of other certificates in the same bulk request.

---

## 4. Submit a Certificate Generation Request

The bulk certificate generation endpoint is:

```text
POST /api/jobs
```

The request accepts:

- Course name
- Issue date
- Recipient list
  - Recipient name
  - Recipient email

Example request:

```bash
curl -X POST "http://127.0.0.1:8000/api/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "course_name": "Python Backend Development",
    "issue_date": "2026-10-07",
    "recipients": [
      {
        "name": "John Doe",
        "email": "john@example.com"
      },
      {
        "name": "Jane Smith",
        "email": "jane@example.com"
      }
    ]
  }'
```

The API creates a background job and returns a job ID.

Example response:

```json
{
  "job_id": "c964d269-71ee-488a-8af5-b813eda8e9d0",
  "status": "PENDING",
  "total": 2,
  "successful": 0,
  "failed": 0
}
```

The job is processed in the background, so certificate generation does not block the initial request.

---

## 5. Retrieve Job Status

Use the job ID returned by the certificate generation request.

Endpoint:

```text
GET /api/jobs/{job_id}
```

Example:

```bash
curl http://127.0.0.1:8000/api/jobs/<JOB_ID>
```

Example completed response:

```json
{
  "job_id": "f8a2a057-06f3-4c4a-9f51-74bc5d1c443b",
  "course_name": "Python Backend Development",
  "issue_date": "2026-10-07",
  "status": "COMPLETED",
  "total": 2,
  "successful": 2,
  "failed": 0,
  "created_at": "2026-10-07T13:14:48.474243",
  "completed_at": "2026-10-07T13:14:48.487363",
  "certificates": [
    {
      "id": "02e0307f-88a2-40c5-9629-efb3278c6b65",
      "recipient_name": "John Doe",
      "email": "john@example.com",
      "status": "COMPLETED",
      "download_url": "/api/certificates/02e0307f-88a2-40c5-9629-efb3278c6b65",
      "error": null
    },
    {
      "id": "ffc84521-1483-42d4-a7e9-20ab6e44e166",
      "recipient_name": "Jane Smith",
      "email": "jane@example.com",
      "status": "COMPLETED",
      "download_url": "/api/certificates/ffc84521-1483-42d4-a7e9-20ab6e44e166",
      "error": null
    }
  ]
}
```

### Job Statuses

```text
PENDING
PROCESSING
COMPLETED
COMPLETED_WITH_ERRORS
FAILED
```

---

## 6. Retrieve Generated Certificates

Each successfully generated certificate has a certificate ID and download URL.

Endpoint:

```text
GET /api/certificates/{certificate_id}
```

Example:

```bash
curl -o certificate.pdf \
  http://127.0.0.1:8000/api/certificates/<CERTIFICATE_ID>
```

The response contains the generated PDF file.

The generated files are stored in the configured `generated/` directory. Generated certificate files are intentionally excluded from Git.

---

## 7. Certificate Status

Each certificate is tracked independently.

Possible certificate statuses:

```text
PENDING
COMPLETED
FAILED
```

If one certificate fails during a bulk operation, the remaining certificates continue to be processed.

The overall job can therefore finish with `COMPLETED` or `COMPLETED_WITH_ERRORS`, depending on the individual certificate results.

---

## 8. Important Implementation and Design Decisions

### Background Processing

Certificate generation is performed using FastAPI `BackgroundTasks`.

This allows the API to return the job ID immediately instead of keeping the HTTP request open while every certificate is generated.

### Job-Based Processing

Bulk requests are represented as jobs.

A job stores:

- Job ID
- Course name
- Issue date
- Total recipients
- Successful certificates
- Failed certificates
- Job status
- Creation time
- Completion time

This allows clients to submit a request and later check its progress.

### Per-Certificate Failure Isolation

Each recipient is processed independently.

If generating one certificate fails:

```text
Recipient A → SUCCESS
Recipient B → FAILURE
Recipient C → SUCCESS
```

The failure of Recipient B does not stop the processing of A or C. This makes bulk processing more resilient.

### Database Design

SQLite is used for persistence, and SQLAlchemy is used as the database ORM.

The database stores job and certificate metadata rather than storing the PDF binary data directly. Generated PDF files are stored separately in the configured output directory.

### PDF Generation

ReportLab is used to generate PDF certificates.

A temporary `.pdf.part` file is created during generation. After successful generation, the temporary file is renamed to the final `.pdf` file. This prevents partially generated PDF files from being treated as completed certificates.

### Unique Certificate Filenames

Certificate files use UUID-based identifiers. This prevents filename collisions when multiple recipients have the same name.

### Path Traversal Protection

Certificate file access is validated so that a requested certificate cannot escape the configured generated-files directory. This prevents unsafe filesystem access through manipulated certificate paths.

### Input Validation

Pydantic schemas validate incoming API requests.

The application also validates certificate text to prevent unsupported characters from causing PDF generation failures with the built-in ReportLab font. Control characters and unsupported CP1252 characters are rejected.

### Bulk Request Limit

A bulk request supports up to **1000 recipients**. This prevents excessively large requests from being submitted to a single job.

### Security and Git Hygiene

The following local files are intentionally excluded from Git:

```text
.env
*.db
*.sqlite
*.sqlite3
generated/*
.venv/
__pycache__/
.pytest_cache/
```

The repository contains `.env.example` so that the required configuration can be understood without exposing local configuration.

---

## API Summary

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/health` | Check API health |
| POST | `/api/jobs` | Submit bulk certificate generation job |
| GET | `/api/jobs/{job_id}` | Retrieve job status and certificate information |
| GET | `/api/certificates/{certificate_id}` | Download a generated certificate |

---

## Typical Workflow

```text
Client
   |
   | POST /api/jobs
   v
FastAPI API
   |
   | Create Job
   v
Background Processor
   |
   +----> Generate Certificate 1
   |
   +----> Generate Certificate 2
   |
   +----> Generate Certificate N
   |
   v
Update Job Status
   |
   | GET /api/jobs/{job_id}
   v
Client receives certificate IDs
   |
   | GET /api/certificates/{certificate_id}
   v
PDF Certificate Download
```

---

## Development Verification

The application should be verified with:

```bash
pytest -q
```

A successful test run confirms the automated test suite passes.

The API can also be manually verified by running:

```bash
python -m uvicorn app.main:app --reload
```

and then opening:

```text
http://127.0.0.1:8000/docs
```

---

## 9. Quick Start

For a quick setup on Windows / Git Bash:

```bash
git clone https://github.com/Praveenraj2206/bulk-certificate-generator.git
cd bulk-certificate-generator
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
pytest -q
python -m uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000/docs
```