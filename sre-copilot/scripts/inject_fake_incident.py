"""
Fires a synthetic Dynatrace problem notification directly at the webhook
so you can demo the full agent flow without waiting for a real anomaly.
"""

import json
import requests
import sys

WEBHOOK_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8090"

payload = {
    "ProblemID": "P-DEMO001",
    "ProblemTitle": "Container memory saturation — payment-service",
    "State": "OPEN",
    "ProblemSeverity": "PERFORMANCE",
    "ImpactedEntities": "payment-service",
    "ProblemDetailsText": (
        "Anomaly detected: container memory (RSS) increased by 340% over the last 20 minutes "
        "with no plateau. Response time degraded from 120ms to 890ms p95. "
        "Anomaly started at 14:32 UTC."
    ),
    "ProblemURL": "https://ker44664.apps.dynatrace.com/ui/problems/P-DEMO001"
}

r = requests.post(
    f"{WEBHOOK_URL}/dynatrace/webhook",
    json=payload,
    headers={"Content-Type": "application/json"}
)

print(f"Status: {r.status_code}")
print(json.dumps(r.json(), indent=2))
