#!/usr/bin/env bash
# Start local Postgres, Redis, and MinIO, install backend Python deps, then seed sample data.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Install Docker Desktop, then re-run this script."
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose is required. Install Docker Desktop, then re-run this script."
  exit 1
fi

start_service() {
  local service="$1"
  local name="$2"
  if docker inspect "$name" >/dev/null 2>&1; then
    docker start "$name" >/dev/null
    echo "Using existing container $name"
  else
    docker compose up -d --no-recreate "$service"
  fi
}

start_service postgres healthcare-postgres
start_service redis redis
start_service minio minio

wait_url() {
  local url="$1"
  curl -sf "$url" >/dev/null
}

echo "Waiting for Postgres, Redis, and MinIO..."
for _ in $(seq 1 40); do
  if docker exec healthcare-postgres pg_isready -U healthcare -d healthcare >/dev/null 2>&1 \
    && docker exec redis redis-cli ping >/dev/null 2>&1 \
    && wait_url "http://127.0.0.1:9000/minio/health/live"; then
    break
  fi
  sleep 1
done

if ! docker exec healthcare-postgres pg_isready -U healthcare -d healthcare >/dev/null 2>&1; then
  echo "Postgres did not become ready on localhost:5432."
  exit 1
fi
if ! docker exec redis redis-cli ping >/dev/null 2>&1; then
  echo "Redis did not become ready on localhost:6379."
  exit 1
fi
if ! wait_url "http://127.0.0.1:9000/minio/health/live"; then
  echo "MinIO did not become ready on localhost:9000."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required. Install it, then re-run this script."
  exit 1
fi

VENV="$ROOT/backend/.venv"
PYTHON="$VENV/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "Creating backend virtual environment..."
  python3 -m venv "$VENV"
fi

if ! "$PYTHON" -c "import psycopg, boto3, dotenv" >/dev/null 2>&1; then
  echo "Installing backend Python dependencies..."
  "$PYTHON" -m pip install -r "$ROOT/backend/requirements.txt"
fi

ENV_FILE="$ROOT/backend/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" << 'EOF'
# Create a key at https://openrouter.ai/keys
# Setup: https://openrouter.ai/docs/api_reference/authentication
OPENROUTER_API_KEY=
REDIS_URL=redis://localhost:6379
DATABASE_URL=postgresql://healthcare:healthcare@localhost:5432/healthcare
S3_ENDPOINT=http://localhost:9000
S3_BUCKET=healthcare
S3_ACCESS_KEY=minio
S3_SECRET_KEY=minio123
EOF
  echo "Created backend/.env. Add your OpenRouter API key before running extractions."
fi

echo "Creating SQL tables and loading sample calls..."
(
  cd "$ROOT/backend"
  "$PYTHON" -c "
from app.crm_handler import crm
from app.artifacts import seed_recordings

crm.setup()
seed_recordings()
print('Ready: call metadata in Postgres, transcripts and recordings in s3://healthcare')
"
)

echo
echo "Postgres  localhost:5432  user/password/db healthcare"
echo "Redis     localhost:6379"
echo "MinIO     http://localhost:9000  (console :9001)  minio / minio123"
echo
if ! grep -Eq '^OPENROUTER_API_KEY=.+' "$ENV_FILE"; then
  echo "OpenRouter API key is not set. Extractions will fail until you add one."
  echo "  Create a key:  https://openrouter.ai/keys"
  echo "  How to set it: https://openrouter.ai/docs/api_reference/authentication"
  echo "  Then paste it into backend/.env as OPENROUTER_API_KEY=..."
  echo
fi
echo "Next, from this repository:"
echo "  2. Add OPENROUTER_API_KEY to backend/.env  (https://openrouter.ai/keys)"
echo "  3. Backend   cd $ROOT/backend && source .venv/bin/activate && python -m app.server"
echo "  4. Frontend  cd $ROOT/frontend && npm ci && npm run dev"
echo "     The frontend terminal prints the link to open in your browser."
