"""
Registers an alerting profile + webhook integration in Dynatrace
so problems automatically hit our SRE Copilot webhook.
Run once after deploying the webhook service to Cloud Run.
"""

import os
import sys
import json
import requests

DT_URL = os.environ.get("DYNATRACE_URL", "https://ker44664.apps.dynatrace.com")
DT_TOKEN = os.environ.get("DYNATRACE_TOKEN", "")
WEBHOOK_URL = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("WEBHOOK_URL", "")

if not WEBHOOK_URL:
    print("Usage: python setup_dynatrace_webhook.py <webhook_cloud_run_url>")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Api-Token {DT_TOKEN}",
    "Content-Type": "application/json"
}

def create_webhook_integration():
    payload = {
        "type": "WEBHOOK",
        "name": "SRE Copilot",
        "enabled": True,
        "alertingProfile": "default",
        "url": f"{WEBHOOK_URL}/dynatrace/webhook",
        "acceptAnyCertificate": True,
        "sendIncidentEvents": False,
        "sendResolutionEvents": False,
        "payload": json.dumps({
            "ProblemID": "{ProblemID}",
            "ProblemTitle": "{ProblemTitle}",
            "State": "{State}",
            "ProblemSeverity": "{ProblemSeverity}",
            "ImpactedEntities": "{ImpactedEntities}",
            "ProblemDetailsText": "{ProblemDetailsText}",
            "ProblemURL": "{ProblemURL}"
        })
    }

    r = requests.post(
        f"{DT_URL}/api/v1/notifications",
        headers=HEADERS,
        json=payload
    )

    if r.status_code in (200, 201):
        print(f"Webhook registered: {r.json().get('id')}")
    else:
        print(f"Failed: {r.status_code} {r.text}")

def verify_token():
    r = requests.get(f"{DT_URL}/api/v2/problems?pageSize=1", headers=HEADERS)
    if r.status_code == 200:
        print(f"Dynatrace token valid. Problems endpoint reachable.")
        return True
    else:
        print(f"Token check failed: {r.status_code} {r.text}")
        return False

if __name__ == "__main__":
    print("Verifying Dynatrace token...")
    if verify_token():
        print("Registering webhook...")
        create_webhook_integration()
