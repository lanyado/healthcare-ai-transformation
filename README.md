# Healthcare call extraction

Open a terminal in this repository for each step below. You need Docker Desktop, Python 3, and Node.js.

## 1. Start the local services

This starts Postgres, Redis, and MinIO in Docker, prepares the Python environment, and loads the sample calls.

```bash
./scripts/dev-services.sh
```

Leave the containers running. Stop them later with `docker compose down`. Saved data stays in the Docker volumes.

## 2. Add your OpenRouter API key

Extractions call OpenRouter. Without a key, the UI shows **Extraction failed**.

Create a key on the OpenRouter keys page: [openrouter.ai/keys](https://openrouter.ai/keys). Sign in, choose **Create Key**, and copy the key. OpenRouter explains the key setup in [API authentication](https://openrouter.ai/docs/api_reference/authentication).

Open `backend/.env` and set:

```bash
OPENROUTER_API_KEY=your-key-here
```

Keep `.env` on this machine only. It is gitignored and must not be committed.

## 3. Start the backend

In a second terminal:

```bash
cd backend
source .venv/bin/activate
python -m app.server
```

Leave this terminal open. The API stays on `http://127.0.0.1:8000` and waits for extraction jobs.

## 4. Start the frontend

In a third terminal:

```bash
cd frontend
npm ci
npm run dev
```

`npm ci` is only needed the first time. The terminal prints a link. Open that link in your browser. The page talks to the backend for you.

## What the services are

| Service | Where | Credentials |
| --- | --- | --- |
| Postgres | `localhost:5432` / database `healthcare` | `healthcare` / `healthcare` |
| Redis | `localhost:6379` | none |
| MinIO (S3) | `http://localhost:9000` (console `:9001`) | `minio` / `minio123` |

Postgres holds call metadata in `calls` and saved extraction fields in `crm_topic_results`. The raw transcript for a call is `s3://healthcare/calls/{call_id}/transcript.json`.

## Project layout

```text
.
├── backend/                 Python extraction API and workers
├── artifacts/audio/         HarborPoint sample recordings
├── data/                    Shared call transcripts
├── frontend/                React app
├── docker-compose.yml       Postgres, Redis, and MinIO
└── scripts/dev-services.sh  Step 1
```
