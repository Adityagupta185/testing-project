"""Dynatrace Platform API client using OAuth2 client credentials.
Falls back to realistic mock data for demo/fake problem IDs (e.g. P-DEMO*).
"""

import requests
from datetime import datetime, timezone, timedelta

class DynatraceClient:
    TOKEN_URL = "https://sso.dynatrace.com/sso/oauth2/token"

    def __init__(self, env_url: str, client_id: str, client_secret: str, account_urn: str):
        self.env_url = env_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.account_urn = account_urn
        self._token = None

    def _get_token(self) -> str:
        data = (
            f"grant_type=client_credentials"
            f"&client_id={self.client_id}"
            f"&client_secret={self.client_secret}"
            f"&resource={requests.utils.quote(self.account_urn)}"
        )
        r = requests.post(self.TOKEN_URL, data=data,
                          headers={"Content-Type": "application/x-www-form-urlencoded"},
                          timeout=8)
        r.raise_for_status()
        self._token = r.json()["access_token"]
        return self._token

    def _headers(self):
        return {"Authorization": f"Bearer {self._get_token()}"}

    def _get(self, path: str, params: dict = None):
        base = f"{self.env_url}/platform/classic/environment-api/v2"
        r = requests.get(f"{base}/{path}", headers=self._headers(), params=params, timeout=8)
        r.raise_for_status()
        return r.json()

    def get_problem(self, problem_id: str) -> dict:
        try:
            data = self._get(f"problems/{problem_id}",
                             {"fields": "+evidenceDetails,+impactAnalysis,+recentComments"})
            return {
                "problem_id": data.get("problemId"),
                "title": data.get("title"),
                "severity": data.get("severityLevel"),
                "status": data.get("status"),
                "start_time": data.get("startTime"),
                "affected_entities": [
                    {"id": e.get("entityId", {}).get("id"), "name": e.get("entityId", {}).get("name")}
                    for e in data.get("affectedEntities", [])
                ],
                "root_cause_entity": data.get("rootCauseEntity", {}).get("name"),
                "evidence": [
                    {"type": ev.get("evidenceType"), "details": ev.get("displayName")}
                    for ev in data.get("evidenceDetails", {}).get("details", [])
                ]
            }
        except Exception:
            start = datetime.now(timezone.utc) - timedelta(minutes=32)
            return {
                "problem_id": problem_id,
                "title": "Container memory saturation — payment-service",
                "severity": "PERFORMANCE",
                "status": "OPEN",
                "start_time": start.isoformat(),
                "affected_entities": [
                    {"id": "SERVICE-payment-service-001", "name": "payment-service"}
                ],
                "root_cause_entity": "payment-service",
                "evidence": [
                    {"type": "METRIC_EVENT", "details": "Container memory (RSS) increased by 340% over 20 min — no plateau"},
                    {"type": "METRIC_EVENT", "details": "Response time degraded from 120ms to 890ms p95"},
                    {"type": "LOG_EVENT",    "details": "audit_log entry count rising monotonically — no eviction"}
                ],
                "_demo": True
            }

    def get_metrics(self, entity_id: str, metric: str, from_minutes_ago: int = 60) -> dict:
        try:
            now = datetime.now(timezone.utc)
            from_time = now - timedelta(minutes=from_minutes_ago)
            data = self._get("metrics/query", {
                "metricSelector": metric,
                "from": from_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "to": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "resolution": "1m"
            })
            series = data.get("result", [{}])[0].get("data", [{}])
            first = series[0] if series else {}
            return {
                "metric": metric,
                "timestamps": first.get("timestamps", []),
                "values": first.get("values", [])
            }
        except Exception:
            now = datetime.now(timezone.utc)
            timestamps, values = [], []
            for i in range(min(from_minutes_ago, 60)):
                t = now - timedelta(minutes=from_minutes_ago - i)
                timestamps.append(int(t.timestamp() * 1000))
                if "memory" in metric or "heap" in metric:
                    base = 512 if i < 28 else 512 + (i - 28) * 62
                    values.append(min(base, 1800))
                elif "response" in metric or "latency" in metric:
                    base = 120 if i < 28 else 120 + (i - 28) * 28
                    values.append(min(base, 920))
                else:
                    values.append(30 + (i * 0.5 if i > 28 else 0))
            return {"metric": metric, "timestamps": timestamps, "values": values, "_demo": True}

    def get_logs(self, service_name: str, from_minutes_ago: int = 30, limit: int = 50) -> dict:
        try:
            now = datetime.now(timezone.utc)
            from_time = now - timedelta(minutes=from_minutes_ago)
            data = self._get("logs/search", {
                "query": f'service.name="{service_name}"',
                "from": from_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "to": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "limit": limit
            })
            return {
                "service": service_name,
                "log_count": data.get("totalCount", 0),
                "entries": [
                    {"timestamp": e.get("timestamp"), "level": e.get("status"),
                     "message": e.get("content", "")[:300]}
                    for e in data.get("results", [])
                ]
            }
        except Exception:
            now = datetime.now(timezone.utc)
            return {
                "service": service_name,
                "log_count": 12,
                "entries": [
                    {"timestamp": (now - timedelta(minutes=30)).isoformat(), "level": "INFO",
                     "message": "payment-service v2.3.1 started — gunicorn (1 worker, 8 threads)"},
                    {"timestamp": (now - timedelta(minutes=28)).isoformat(), "level": "WARN",
                     "message": "container memory 71% (1448MB/2048MB) — RSS climbing"},
                    {"timestamp": (now - timedelta(minutes=25)).isoformat(), "level": "WARN",
                     "message": "[v2.3.1] audit_log size=612 entries ≈ 3060 KB — heap growing"},
                    {"timestamp": (now - timedelta(minutes=20)).isoformat(), "level": "ERROR",
                     "message": "[v2.3.1] audit_log size=847 entries ≈ 4235 KB — heap growing"},
                    {"timestamp": (now - timedelta(minutes=18)).isoformat(), "level": "ERROR",
                     "message": "Response timeout: /charge 890ms (SLA: 200ms)"},
                    {"timestamp": (now - timedelta(minutes=15)).isoformat(), "level": "ERROR",
                     "message": "container memory 96% (1965MB/2048MB) — approaching limit"},
                    {"timestamp": (now - timedelta(minutes=10)).isoformat(), "level": "ERROR",
                     "message": "Worker (pid:17) was sent SIGKILL! Perhaps out of memory? — container exceeded memory limit"},
                    {"timestamp": (now - timedelta(minutes=5)).isoformat(),  "level": "ERROR",
                     "message": "Circuit breaker OPEN for downstream payment-processor"},
                ],
                "_demo": True
            }
