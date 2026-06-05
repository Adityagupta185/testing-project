# SRE Copilot — Cloud Run Deployment
# Project: eco-splicer-475211-i6
# Run from any directory: & C:\hackathon\sre-copilot\scripts\deploy_cloudrun.ps1

$PROJECT_ID = "eco-splicer-475211-i6"
$REGION     = "us-central1"

# ── Load secrets from .env ────────────────────────────────────────────────────
$envFile = "C:\hackathon\sre-copilot\.env"
$envVars = @{}
Get-Content $envFile | ForEach-Object {
    if ($_ -match "^\s*([^#=]+)=(.+)$") {
        $envVars[$matches[1].Trim()] = $matches[2].Trim()
    }
}

$DT_URL              = $envVars["DYNATRACE_URL"]
$DT_CLIENT_ID        = $envVars["DT_CLIENT_ID"]
$DT_CLIENT_SEC       = $envVars["DT_CLIENT_SECRET"]
$DT_ACCOUNT_URN      = $envVars["DT_ACCOUNT_URN"]
$GITLAB_TOKEN        = $envVars["GITLAB_TOKEN"]
$GITLAB_PID          = $envVars["GITLAB_PROJECT_ID"]
$GEMINI_KEY          = $envVars["GEMINI_API_KEY"]
$SLACK_BOT_TOKEN     = $envVars["SLACK_BOT_TOKEN"]
$SLACK_CHANNEL_ID    = $envVars["SLACK_CHANNEL_ID"]
$SLACK_SIGNING_SEC   = $envVars["SLACK_SIGNING_SECRET"]

Write-Host "`n==> Setting GCP project to $PROJECT_ID"
gcloud config set project $PROJECT_ID

Write-Host "`n==> Enabling required APIs"
gcloud services enable `
  run.googleapis.com `
  cloudbuild.googleapis.com `
  artifactregistry.googleapis.com `
  --project=$PROJECT_ID

# ── 1. payment-service (v2.3.1 — the bad deploy for demo) ────────────────────
Write-Host "`n==> [1/3] Deploying payment-service (v2.3.1)"
gcloud run deploy payment-service `
  --source "C:\hackathon\payment-service" `
  --region $REGION `
  --platform managed `
  --allow-unauthenticated `
  --set-env-vars "APP_VERSION=2.3.1" `
  --memory 512Mi `
  --timeout 60s `
  --project $PROJECT_ID

$PAYMENT_URL = gcloud run services describe payment-service `
  --region $REGION --format "value(status.url)" --project $PROJECT_ID
Write-Host "  payment-service: $PAYMENT_URL"

# ── 2. spark (Flask API + React UI) ──────────────────────────────────────────
Write-Host "`n==> [2/3] Deploying spark (Flask API + React UI)"
gcloud run deploy spark `
  --source "C:\hackathon\sre-copilot\frontend" `
  --region $REGION `
  --platform managed `
  --allow-unauthenticated `
  --memory 256Mi `
  --timeout 60s `
  --set-env-vars "SLACK_BOT_TOKEN=$SLACK_BOT_TOKEN,SLACK_CHANNEL_ID=$SLACK_CHANNEL_ID,SLACK_SIGNING_SECRET=$SLACK_SIGNING_SEC" `
  --project $PROJECT_ID

$APPROVAL_URL = gcloud run services describe spark `
  --region $REGION --format "value(status.url)" --project $PROJECT_ID
Write-Host "  spark: $APPROVAL_URL"

# ── 3. sre-webhook (Dynatrace webhook receiver + Claude agent) ────────────────
Write-Host "`n==> [3/3] Deploying sre-webhook (webhook receiver + Claude agent)"
gcloud run deploy sre-webhook `
  --source "C:\hackathon\sre-copilot" `
  --region $REGION `
  --platform managed `
  --allow-unauthenticated `
  --memory 1Gi `
  --timeout 3600s `
  --concurrency 5 `
  --set-env-vars "DYNATRACE_URL=$DT_URL,DT_CLIENT_ID=$DT_CLIENT_ID,DT_CLIENT_SECRET=$DT_CLIENT_SEC,DT_ACCOUNT_URN=$DT_ACCOUNT_URN,GITLAB_TOKEN=$GITLAB_TOKEN,GITLAB_PROJECT_ID=$GITLAB_PID,GEMINI_API_KEY=$GEMINI_KEY,APPROVAL_WEBHOOK_URL=$APPROVAL_URL" `
  --project $PROJECT_ID

$WEBHOOK_URL = gcloud run services describe sre-webhook `
  --region $REGION --format "value(status.url)" --project $PROJECT_ID
Write-Host "  sre-webhook: $WEBHOOK_URL"

# ── Update .env with live URLs ────────────────────────────────────────────────
Write-Host "`n==> Updating .env with deployed URLs"
$content = Get-Content $envFile -Raw
$content = $content -replace "APPROVAL_WEBHOOK_URL=.*", "APPROVAL_WEBHOOK_URL=$APPROVAL_URL"
if ($content -notmatch "WEBHOOK_URL=") {
    $content += "`nWEBHOOK_URL=$WEBHOOK_URL"
} else {
    $content = $content -replace "WEBHOOK_URL=.*", "WEBHOOK_URL=$WEBHOOK_URL"
}
Set-Content $envFile -Value $content -Encoding utf8

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================"
Write-Host "  DEPLOYED SUCCESSFULLY"
Write-Host "------------------------------------------------------------"
Write-Host "  payment-service  : $PAYMENT_URL"
Write-Host "  spark (UI)       : $APPROVAL_URL  (open this in your browser)"
Write-Host "  sre-webhook      : $WEBHOOK_URL"
Write-Host ""
Write-Host "  Dynatrace webhook endpoint:"
Write-Host "  $WEBHOOK_URL/dynatrace/webhook"
Write-Host ""
Write-Host "  Next step: register the webhook URL in Dynatrace"
Write-Host "    python C:\hackathon\sre-copilot\scripts\setup_dynatrace_webhook.py"
Write-Host "============================================================"
