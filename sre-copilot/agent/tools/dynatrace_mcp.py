"""
Dynatrace MCP integration.

Package : @dynatrace-oss/dynatrace-mcp-server@1.0.0
Command : npx @dynatrace-oss/dynatrace-mcp-server@1.0.0
Auth    : DT_ENVIRONMENT env var + browser OAuth (interactive)

In Cloud Run we use Dynatrace OAuth2 client-credentials flow instead
(machine-to-machine, non-interactive). The MCP client below is wired for
local/demo use; the fallback handles production.
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

DT_ENVIRONMENT = os.environ.get("DYNATRACE_URL", "")

async def _call_mcp(tool_name: str, arguments: dict) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command="npx",
        args=["@dynatrace-oss/dynatrace-mcp-server@1.0.0"],
        env={**os.environ.copy(), "DT_ENVIRONMENT": DT_ENVIRONMENT},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            raw = result.content[0].text if result.content else "{}"
            try:
                return json.loads(raw)
            except Exception:
                return {"raw": raw}

def _run_mcp(tool_name: str, arguments: dict) -> dict:
    try:
        return asyncio.run(_call_mcp(tool_name, arguments))
    except Exception as e:
        raise RuntimeError(f"MCP call failed: {e}") from e

def _dt_client():
    from tools.dynatrace_client import DynatraceClient
    return DynatraceClient(
        os.environ["DYNATRACE_URL"],
        os.environ["DT_CLIENT_ID"],
        os.environ["DT_CLIENT_SECRET"],
        os.environ["DT_ACCOUNT_URN"],
    )

def _mock_problem(problem_id):
    start = datetime.now(timezone.utc) - timedelta(minutes=32)
    return {
        "problem_id": problem_id,
        "title": "Container memory saturation — payment-service",
        "severity": "PERFORMANCE", "status": "OPEN",
        "start_time": start.isoformat(),
        "affected_entities": [{"id": "SERVICE-001", "name": "payment-service"}],
        "root_cause_entity": "payment-service",
        "evidence": [
            {"type": "METRIC_EVENT", "details": "Container memory (RSS) increased 340% over 20 min — no plateau"},
            {"type": "METRIC_EVENT", "details": "Response time 120ms → 890ms p95"},
            {"type": "LOG_EVENT",    "details": "audit_log entry count rising monotonically — no eviction"},
        ],
        "_source": "mock",
    }

def _mock_metrics(metric, from_minutes_ago):
    now = datetime.now(timezone.utc)
    ts, vals = [], []
    for i in range(min(from_minutes_ago, 60)):
        ts.append(int((now - timedelta(minutes=from_minutes_ago - i)).timestamp() * 1000))
        if "memory" in metric or "heap" in metric:
            vals.append(min(512 + max(0, i - 28) * 62, 1800))
        elif "response" in metric or "latency" in metric:
            vals.append(min(120 + max(0, i - 28) * 28, 920))
        else:
            vals.append(30 + (i * 0.5 if i > 28 else 0))
    return {"metric": metric, "timestamps": ts, "values": vals, "_source": "mock"}

def _mock_logs(service_name):
    now = datetime.now(timezone.utc)
    return {
        "service": service_name, "log_count": 6,
        "entries": [
            {"timestamp": (now - timedelta(minutes=30)).isoformat(), "level": "INFO",  "message": f"{service_name} v2.3.1 started — gunicorn (1 worker, 8 threads)"},
            {"timestamp": (now - timedelta(minutes=28)).isoformat(), "level": "WARN",  "message": "container memory 71% (1448MB/2048MB) — RSS climbing"},
            {"timestamp": (now - timedelta(minutes=20)).isoformat(), "level": "WARN",  "message": "[v2.3.1] audit_log size=612 entries ≈ 3060 KB — heap growing"},
            {"timestamp": (now - timedelta(minutes=15)).isoformat(), "level": "ERROR", "message": "[v2.3.1] audit_log size=847 entries ≈ 4235 KB — heap growing"},
            {"timestamp": (now - timedelta(minutes=10)).isoformat(), "level": "ERROR", "message": "Response timeout /charge 890ms (SLA 200ms)"},
            {"timestamp": (now - timedelta(minutes=5)).isoformat(),  "level": "ERROR", "message": "Worker (pid:17) was sent SIGKILL! Perhaps out of memory? — container exceeded memory limit"},
        ],
        "_source": "mock",
    }

def get_problem(problem_id: str) -> dict:
    try:
        result = _run_mcp("get_problem", {"problemId": problem_id})
        logger.info("Dynatrace MCP ✓ get_problem")
        return result
    except Exception:
        pass

    try:
        result = _dt_client().get_problem(problem_id)
        logger.info("Dynatrace API ✓ get_problem")
        return result
    except Exception:
        pass

    logger.info("Dynatrace mock ✓ get_problem")
    return _mock_problem(problem_id)

def get_metrics(entity_id: str, metric: str, from_minutes_ago: int = 60) -> dict:
    now = datetime.now(timezone.utc)
    try:
        result = _run_mcp("query_metrics", {
            "metricSelector": metric,
            "entitySelector": f"entityId({entity_id})",
            "from": (now - timedelta(minutes=from_minutes_ago)).isoformat(),
            "to": now.isoformat(),
        })
        logger.info("Dynatrace MCP ✓ query_metrics")
        return result
    except Exception:
        pass

    try:
        result = _dt_client().get_metrics(entity_id, metric, from_minutes_ago)
        logger.info("Dynatrace API ✓ get_metrics")
        return result
    except Exception:
        pass

    logger.info("Dynatrace mock ✓ get_metrics")
    return _mock_metrics(metric, from_minutes_ago)

def get_logs(service_name: str, from_minutes_ago: int = 30, limit: int = 50) -> dict:
    now = datetime.now(timezone.utc)
    try:
        result = _run_mcp("search_logs", {
            "query": f'service.name="{service_name}"',
            "from": (now - timedelta(minutes=from_minutes_ago)).isoformat(),
            "to": now.isoformat(),
            "limit": limit,
        })
        logger.info("Dynatrace MCP ✓ search_logs")
        return result
    except Exception:
        pass

    try:
        result = _dt_client().get_logs(service_name, from_minutes_ago, limit)
        logger.info("Dynatrace API ✓ get_logs")
        return result
    except Exception:
        pass

    logger.info("Dynatrace mock ✓ get_logs")
    return _mock_logs(service_name)
