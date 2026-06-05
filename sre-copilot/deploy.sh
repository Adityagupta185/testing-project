#!/bin/bash
set -e

PROJECT_ID="sre-agent-497311"
REGION="us-central1"

echo "==> Setting GCP project"
gcloud config set project $PROJECT_ID

echo "==> Enabling required APIs"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  containerregistry.googleapis.com \
  --project=$PROJECT_ID

echo "==> Deploying payment-service (v2.3.1 — bad deploy)"
gcloud run deploy payment-service \
  --source ../payment-service \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars APP_VERSION=2.3.1 \
  --memory 512Mi \
  --project $PROJECT_ID

echo "==> Getting payment-service URL"
PAYMENT_URL=$(gcloud run services describe payment-service \
  --region $REGION --format "value(status.url)" --project $PROJECT_ID)
echo "payment-service: $PAYMENT_URL"

echo "==> Deploying approval-backend"
gcloud run deploy approval-backend \
  --source ./frontend \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --memory 256Mi \
  --project $PROJECT_ID

echo "==> Getting approval-backend URL"
APPROVAL_URL=$(gcloud run services describe approval-backend \
  --region $REGION --format "value(status.url)" --project $PROJECT_ID)
echo "approval-backend: $APPROVAL_URL"

echo ""
echo "=============================="
echo "DEPLOYED SERVICES:"
echo "  payment-service : $PAYMENT_URL"
echo "  approval-backend: $APPROVAL_URL"
echo ""
echo "Next: set APPROVAL_WEBHOOK_URL=$APPROVAL_URL in .env"
echo "=============================="
