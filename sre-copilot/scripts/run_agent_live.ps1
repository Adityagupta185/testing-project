# SPARK — run the REAL agent live (Gemini 2.5 Flash on Vertex AI).
# Investigates P-DEMO001, posts a real incident to the dashboard + Slack,
# and blocks for your approval. One command, nothing to set up.
#
#   powershell -ExecutionPolicy Bypass -File C:\hackathon\sre-copilot\scripts\run_agent_live.ps1

$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\hackathon\key.json"
$env:GCP_PROJECT_ID                 = "eco-splicer-475211-i6"
$env:APPROVAL_WEBHOOK_URL           = "https://spark-366154347729.us-central1.run.app"
$env:GITLAB_TOKEN                   = (Get-Content "C:\hackathon\gitlantoken.txt" -Raw).Trim()
$env:GITLAB_PROJECT_ID              = "82503669"
$env:PROBLEM_ID                     = "P-DEMO001"
$env:PROBLEM_TITLE                  = "Container memory saturation - payment-service"

Set-Location "C:\hackathon\sre-copilot\agent"
Write-Host "SPARK agent starting (real Gemini)..." -ForegroundColor Yellow
python agent.py
