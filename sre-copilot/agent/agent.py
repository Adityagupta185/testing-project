"""
SRE Copilot Agent — Google ADK (Agent Development Kit) + Vertex AI Gemini 2.5 Flash
Dynatrace alert → ADK Agent → tool-use loop → human approval → GitLab rollback.

Built with Google Cloud Agent Builder (ADK).
Partner integrations:
  - Dynatrace MCP server  (get_problem, query_metrics, search_logs)
  - GitLab REST client    (deployment history, rollback pipeline)
"""

import os
import json
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
GCP_PROJECT          = os.environ.get("GCP_PROJECT_ID", "eco-splicer-475211-i6")
GCP_REGION           = os.environ.get("REGION", "us-central1")
GITLAB_TOKEN         = os.environ.get("GITLAB_TOKEN", "")
GITLAB_PROJECT_ID    = os.environ.get("GITLAB_PROJECT_ID", "")
APPROVAL_WEBHOOK_URL = os.environ.get("APPROVAL_WEBHOOK_URL", "")

# Route Gemini calls through Vertex AI (Google Cloud Agent Builder backend)
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "1"
os.environ["GOOGLE_CLOUD_PROJECT"]      = GCP_PROJECT

# ── Google ADK imports ────────────────────────────────────────────────────────
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types


# ── Tool functions ────────────────────────────────────────────────────────────
# ADK reads Python type annotations + docstrings to build the tool schema
# automatically — no manual JSON schema required.

def dynatrace_get_problem(problem_id: str) -> dict:
    """Fetch full Dynatrace problem details via MCP: affected entities, severity, start time, and evidence."""
    from tools.dynatrace_mcp import get_problem
    result = get_problem(problem_id)
    logger.info(f"[tool] dynatrace_get_problem({problem_id})")
    return result


def dynatrace_get_metrics(entity_id: str, metric: str, from_minutes_ago: int = 60) -> dict:
    """Pull time-series metrics (CPU, memory, latency) for an entity via Dynatrace MCP query_metrics."""
    from tools.dynatrace_mcp import get_metrics
    result = get_metrics(entity_id, metric, from_minutes_ago)
    logger.info(f"[tool] dynatrace_get_metrics({entity_id}, {metric})")
    return result


def dynatrace_get_logs(service_name: str, from_minutes_ago: int = 30, limit: int = 50) -> dict:
    """Fetch recent log lines for a named service via Dynatrace MCP search_logs."""
    from tools.dynatrace_mcp import get_logs
    result = get_logs(service_name, from_minutes_ago, limit)
    logger.info(f"[tool] dynatrace_get_logs({service_name})")
    return result


def gitlab_get_recent_deployments(project_id: str, hours_back: int = 3) -> dict:
    """List recent GitLab CI/CD pipeline runs to surface deployments that may have caused the incident."""
    from tools.gitlab_client import GitLabClient
    result = GitLabClient(GITLAB_TOKEN).get_deployments(project_id, hours_back)
    logger.info(f"[tool] gitlab_get_recent_deployments({project_id}) → {result.get('deployment_count', 0)} pipelines")
    return result


def gitlab_trigger_rollback(project_id: str, rollback_to_version: str) -> dict:
    """Trigger the GitLab rollback pipeline to revert the service to a previous stable version."""
    from tools.gitlab_client import GitLabClient
    result = GitLabClient(GITLAB_TOKEN).trigger_rollback(project_id, rollback_to_version)
    logger.info(f"[tool] gitlab_trigger_rollback({project_id}, {rollback_to_version})")
    return result


def send_approval_request(
    summary: str,
    root_cause: str,
    recommended_action: str,
    confidence_score: float,
    rollback_version: str,
) -> dict:
    """Post an incident briefing to the on-call engineer approval UI and block until they approve or reject."""
    from tools.approval_client import ApprovalClient
    result = ApprovalClient(APPROVAL_WEBHOOK_URL).send({
        "summary": summary,
        "root_cause": root_cause,
        "recommended_action": recommended_action,
        "confidence_score": confidence_score,
        "rollback_version": rollback_version,
    })
    logger.info(f"[tool] send_approval_request → decision: {result.get('decision')}")
    return result


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are SRE Copilot, an expert incident response agent powered by Gemini on Google Cloud.

When an alert fires:
1. Use dynatrace_get_problem to fetch full problem details (Dynatrace MCP)
2. Use dynatrace_get_metrics to pull memory and latency metrics (Dynatrace MCP)
3. Use dynatrace_get_logs to fetch logs around the incident window (Dynatrace MCP)
4. Use gitlab_get_recent_deployments to check for deploys in the last 3 hours
5. Correlate deployment timestamp with anomaly start time — this is your root cause
6. Form a hypothesis with a confidence score (0–1)
7. Use send_approval_request to post a ONE-SCREEN briefing to the on-call engineer
8. If approved, use gitlab_trigger_rollback to revert the service
9. Confirm recovery by checking metrics

Be precise. State what you know vs what you infer. Never trigger a rollback without approval.
"""

# ── Google ADK Agent (Google Cloud Agent Builder) ─────────────────────────────

_sre_agent = Agent(
    name="sre_copilot",
    model="gemini-2.5-flash",
    description=(
        "SRE incident response agent — diagnoses Dynatrace alerts and orchestrates "
        "GitLab rollbacks with human-in-the-loop approval"
    ),
    instruction=SYSTEM_PROMPT,
    tools=[
        dynatrace_get_problem,
        dynatrace_get_metrics,
        dynatrace_get_logs,
        gitlab_get_recent_deployments,
        gitlab_trigger_rollback,
        send_approval_request,
    ],
)

_session_service = InMemorySessionService()
_runner = Runner(
    agent=_sre_agent,
    app_name="spark_ai",
    session_service=_session_service,
)


# ── Public entry point (called by webhook/main.py) ────────────────────────────

def investigate_incident(problem_id: str, problem_title: str, credentials: dict = None) -> dict:
    """Run a full investigation for a Dynatrace alert. credentials overrides env vars for multi-tenant users."""
    logger.info(f"SPARK (Google ADK + Gemini 2.5 Flash on Vertex AI) activated: {problem_id} — {problem_title}")

    # Per-session credential overrides for multi-tenant public users
    if credentials:
        global APPROVAL_WEBHOOK_URL, GITLAB_PROJECT_ID
        if credentials.get("dt_url"):
            os.environ["DYNATRACE_URL"] = credentials["dt_url"]
        if credentials.get("gl_project_id"):
            os.environ["GITLAB_PROJECT_ID"] = credentials["gl_project_id"]
            GITLAB_PROJECT_ID = credentials["gl_project_id"]
        if credentials.get("approval_url"):
            os.environ["APPROVAL_WEBHOOK_URL"] = credentials["approval_url"]
            APPROVAL_WEBHOOK_URL = credentials["approval_url"]

    session = _session_service.create_session(app_name="spark_ai", user_id="sre-oncall")

    message = (
        f"INCIDENT ALERT\n"
        f"Problem ID: {problem_id}\n"
        f"Title: {problem_title}\n"
        f"Time: {datetime.now(timezone.utc).isoformat()}\n"
        f"GitLab Project ID: {os.environ.get('GITLAB_PROJECT_ID', GITLAB_PROJECT_ID)}\n\n"
        f"Investigate fully, identify root cause, and coordinate a fix."
    )

    final_text = ""
    for event in _runner.run(
        user_id="sre-oncall",
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text=message)],
        ),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text
            break

    logger.info(f"Investigation complete: {problem_id}")
    return {"summary": final_text, "problem_id": problem_id}


if __name__ == "__main__":
    result = investigate_incident(
        problem_id=os.getenv("PROBLEM_ID", "P-TEST001"),
        problem_title=os.getenv("PROBLEM_TITLE", "Memory leak detected in payment-service"),
    )
    print(json.dumps(result, indent=2))
