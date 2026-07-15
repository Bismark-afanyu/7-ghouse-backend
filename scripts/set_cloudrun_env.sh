#!/usr/bin/env bash
set -euo pipefail

ENV_FILE=".env"
PROJECT="g-house-d458c"
REGION="europe-west1"
SERVICE="g-house-backend"

if [ ! -f "$ENV_FILE" ]; then
  echo "Error: $ENV_FILE not found"
  exit 1
fi

TMPFILE=$(mktemp /tmp/cloudrun_env.XXXXXX.yaml)
trap 'rm -f "$TMPFILE"' EXIT

echo "# Cloud Run env vars (auto-generated from .env)" > "$TMPFILE"

while IFS= read -r line || [[ -n "$line" ]]; do
  [[ "$line" =~ ^#.*$ ]] && continue
  [[ -z "$line" ]] && continue
  key="${line%%=*}"
  value="${line#*=}"
  printf '%s: "%s"\n' "$key" "$value" >> "$TMPFILE"
done < "$ENV_FILE"

echo "Setting env vars on Cloud Run service $SERVICE..."
gcloud run services update "$SERVICE" \
  --region "$REGION" \
  --project "$PROJECT" \
  --env-vars-file "$TMPFILE"

echo "Done. Env vars updated for $SERVICE"
