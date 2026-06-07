"""GitLab REST API client — deployment history + pipeline triggers."""

import requests
from datetime import datetime, timezone, timedelta


class GitLabClient:
    def __init__(self, token: str, base_url: str = "https://gitlab.com"):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "PRIVATE-TOKEN": token,
            "Content-Type": "application/json"
        }

    def _get(self, path: str, params: dict = None):
        r = requests.get(f"{self.base_url}/api/v4/{path}", headers=self.headers, params=params)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, data: dict = None):
        r = requests.post(f"{self.base_url}/api/v4/{path}", headers=self.headers, json=data)
        r.raise_for_status()
        return r.json()

    def get_deployments(self, project_id: str, hours_back: int = 3) -> dict:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()
        try:
            pipelines = self._get(f"projects/{project_id}/pipelines", {
                "updated_after": since,
                "order_by": "updated_at",
                "sort": "desc",
                "per_page": 10
            })
        except Exception as e:
            # Don't let a GitLab hiccup crash the whole investigation
            return {"project_id": project_id, "hours_back": hours_back,
                    "deployment_count": 0, "deployments": [], "error": str(e)[:200]}
        deployments = []
        for p in pipelines:
            deployments.append({
                "pipeline_id": p.get("id"),
                "ref": p.get("ref"),
                "status": p.get("status"),
                "created_at": p.get("created_at"),
                "updated_at": p.get("updated_at"),
                "web_url": p.get("web_url"),
                "triggered_by": p.get("user", {}).get("username")
            })
        return {
            "project_id": project_id,
            "hours_back": hours_back,
            "deployment_count": len(deployments),
            "deployments": deployments
        }

    def trigger_rollback(self, project_id: str, rollback_to_version: str) -> dict:
        """Trigger the GitLab rollback pipeline (returns gracefully on failure)."""
        try:
            result = self._post(f"projects/{project_id}/pipeline", {
                "ref": "master",
                "variables": [
                    {"key": "ROLLBACK_VERSION", "value": rollback_to_version},
                    {"key": "TRIGGERED_BY", "value": "sre-copilot-agent"}
                ]
            })
            return {
                "triggered": True,
                "pipeline_id": result.get("id"),
                "status": result.get("status"),
                "web_url": result.get("web_url"),
                "rollback_to": rollback_to_version
            }
        except Exception as e:
            # The rollback job is `when: manual` in .gitlab-ci.yml by design —
            # surface that to the agent instead of crashing the run.
            return {
                "triggered": False,
                "rollback_to": rollback_to_version,
                "error": str(e)[:200],
                "note": "Rollback pipeline is manual-approval gated in GitLab; engineer triggers the rollback job.",
            }
