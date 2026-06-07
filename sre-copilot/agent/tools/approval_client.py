"""Sends incident briefing to the React approval UI and blocks until engineer decides."""

import time
import requests
import logging

logger = logging.getLogger(__name__)

class ApprovalClient:
    def __init__(self, webhook_url: str, poll_interval: int = 3, timeout: int = 300):
        self.webhook_url = webhook_url
        self.poll_interval = poll_interval
        self.timeout = timeout

    def send(self, briefing: dict) -> dict:
        """
        POST briefing to approval UI, then poll until engineer approves/rejects.
        Returns {"decision": "approved"|"rejected", "reason": str}
        """
        logger.info(f"Sending approval request: {briefing.get('summary', '')[:100]}")

        r = requests.post(f"{self.webhook_url}/incidents", json=briefing, timeout=10)
        r.raise_for_status()
        incident_id = r.json().get("incident_id")

        logger.info(f"Waiting for engineer decision on incident {incident_id}")

        elapsed = 0
        while elapsed < self.timeout:
            time.sleep(self.poll_interval)
            elapsed += self.poll_interval

            status_r = requests.get(f"{self.webhook_url}/incidents/{incident_id}", timeout=5)
            if status_r.status_code == 200:
                data = status_r.json()
                decision = data.get("decision")
                if decision in ("approved", "rejected"):
                    logger.info(f"Engineer decision: {decision}")
                    return {"decision": decision, "reason": data.get("reason", ""), "incident_id": incident_id}

        return {"decision": "timeout", "reason": "No response within 5 minutes", "incident_id": incident_id}
