#!/bin/bash
# Usage: ./deploy.sh [backend|frontend|all]
set -e

PROJECT=mediationmate
REGION=us-central1

deploy_backend() {
  echo "Deploying backend..."
  cd "$(dirname "$0")/backend"
  gcloud run deploy saucer-backend \
    --source . \
    --region "$REGION" \
    --project "$PROJECT" \
    --allow-unauthenticated
  cd - > /dev/null
}

deploy_frontend() {
  echo "Deploying frontend..."
  cd "$(dirname "$0")/frontend"
  gcloud run deploy saucer-frontend \
    --source . \
    --region "$REGION" \
    --project "$PROJECT" \
    --allow-unauthenticated
  cd - > /dev/null
}

case "${1:-all}" in
  backend)  deploy_backend ;;
  frontend) deploy_frontend ;;
  all)      deploy_backend && deploy_frontend ;;
  *)        echo "Usage: $0 [backend|frontend|all]"; exit 1 ;;
esac

echo "Done."
