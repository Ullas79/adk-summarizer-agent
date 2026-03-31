# ADK Summarizer Agent v2 🤖☁️

A production-grade AI agent built with **Google ADK** and **Gemini 2.0 Flash on Vertex AI**,
fully hosted on Google Cloud (Artifact Registry → Cloud Build → Cloud Run).

No API keys — authentication uses **Application Default Credentials** and a
**dedicated service account** with least-privilege IAM roles.

---

## Architecture

```
GitHub (push to main)
    │
    ▼
Cloud Build (cloudbuild.yaml)
    │  build → push
    ▼
Artifact Registry
    │  image pull
    ▼
Cloud Run  ←── HTTPS ──── caller
    │
    ▼
FastAPI (main.py)
    │  ADK Runner
    ▼
ADK Agent (agent.py)
    │  Vertex AI
    ▼
Gemini 2.0 Flash
```

| File | Purpose |
|---|---|
| `config.py` | Pydantic settings — all config from env vars |
| `logger.py` | JSON structured logging for Cloud Logging |
| `agent.py` | ADK `Agent` — Vertex AI routing + system instruction |
| `main.py` | FastAPI app — middleware, probes, `/run` endpoint |
| `Dockerfile` | Two-stage build, non-root, gunicorn + uvicorn workers |
| `cloudbuild.yaml` | CI/CD: build → push → deploy → smoke test |
| `service.yaml` | Declarative Cloud Run service (scaling, probes, SA) |
| `setup.sh` | One-time GCP bootstrap (APIs, IAM, Artifact Registry) |
| `Makefile` | Developer shortcuts |

---

## API Reference

### `GET /health` — liveness probe
```
200 OK  {"status": "ok"}
```

### `GET /ready` — readiness probe
```
200 OK  {"status": "ready"}
503     {"detail": "Not ready yet."}
```

### `POST /run` — summarise text

**Request**
```json
{
  "text": "...your text here (max 50,000 chars)...",
  "user_id": "optional-identifier"
}
```

**Response**
```json
{
  "status": "ok",
  "session_id": "3f9a1b2c-4d5e-...",
  "user_id": "demo",
  "input_chars": 612,
  "latency_ms": 843,
  "result": {
    "summary": "The James Webb Space Telescope, launched in December 2021, is the largest optical space telescope ever built...",
    "key_points": [
      "JWST operates in infrared, enabling it to observe objects too distant or faint for Hubble.",
      "It reached its operational position at the Sun-Earth L2 point in January 2022.",
      "Its improved sensitivity makes it ideal for studying the early universe."
    ],
    "word_count_estimate": 98,
    "language": "en"
  }
}
```

**curl example**
```bash
curl -X POST https://YOUR_CLOUD_RUN_URL/run \
  -H "Content-Type: application/json" \
  -d '{
    "text": "The James Webb Space Telescope is a space telescope designed to conduct infrared astronomy. It was launched in December 2021 and reached the Sun-Earth L2 point in January 2022. Its high-resolution instruments allow it to view objects too old, distant, or faint for the Hubble Space Telescope.",
    "user_id": "demo"
  }'
```

---

## Quick Start

### Prerequisites

- Google Cloud project with billing enabled
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) authenticated
- Python 3.12+ (local dev only)

### 1. Bootstrap GCP (once per project)

```bash
chmod +x setup.sh
./setup.sh YOUR_PROJECT_ID us-central1
```

This enables APIs, creates the Artifact Registry repo, service account, and
sets up least-privilege IAM bindings.

### 2. First deploy

```bash
make deploy PROJECT_ID=YOUR_PROJECT_ID
```

This triggers `cloudbuild.yaml` which: builds the image, pushes it to
Artifact Registry, deploys to Cloud Run, and runs a `/health` smoke test.

### 3. Get your URL

```bash
make url PROJECT_ID=YOUR_PROJECT_ID
# → https://adk-summarizer-agent-xxxxxxxxxx-uc.a.run.app
```

### 4. Test it

```bash
make test PROJECT_ID=YOUR_PROJECT_ID
```
