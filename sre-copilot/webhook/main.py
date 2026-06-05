"""
Dynatrace webhook receiver — wakes the SRE Copilot agent when a problem fires.
Supports ?session=SESSION_ID for multi-tenant public users.
"""

import os
import json
import logging
import threading
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APPROVAL_URL = os.getenv("APPROVAL_WEBHOOK_URL", "https://spark-366154347729.us-central1.run.app")


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/dynatrace/webhook", methods=["POST"])
def dynatrace_webhook():
    payload = request.get_json(silent=True) or {}
    session_id = request.args.get("session")

    problem_id    = payload.get("ProblemID") or payload.get("problemId")
    problem_title = payload.get("ProblemTitle") or payload.get("title", "Unknown problem")
    state         = payload.get("State") or payload.get("status", "OPEN")

    logger.info(f"Webhook received: {problem_id} | {state} | {problem_title} | session={session_id}")

    if state not in ("OPEN", "open"):
        return jsonify({"status": "ignored", "reason": f"state={state}"})
    if not problem_id:
        return jsonify({"status": "error", "reason": "No problem ID"}), 400

    # Fetch session credentials for multi-tenant users
    credentials = None
    if session_id:
        try:
            r = requests.get(f"{APPROVAL_URL}/sessions/{session_id}", timeout=5)
            if r.status_code == 200:
                session_data = r.json()
                credentials = {
                    "dt_url":        session_data.get("dt_url"),
                    "gl_url":        session_data.get("gl_url", "https://gitlab.com"),
                    "gl_project_id": session_data.get("gl_project_id"),
                    "approval_url":  APPROVAL_URL,
                }
                # Credentials endpoint doesn't return tokens for security;
                # use env vars for now (the simulate path handles real tokens server-side)
        except Exception as e:
            logger.warning(f"Could not fetch session {session_id}: {e}")

    thread = threading.Thread(
        target=_run_agent,
        args=(problem_id, problem_title, credentials),
        daemon=True,
    )
    thread.start()

    return jsonify({"status": "agent_triggered", "problem_id": problem_id, "session": session_id})


def _run_agent(problem_id: str, problem_title: str, credentials: dict = None):
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))
        from agent import investigate_incident
        result = investigate_incident(problem_id, problem_title, credentials=credentials)
        logger.info(f"Agent completed for {problem_id}: {json.dumps(result)[:200]}")
    except Exception as e:
        logger.error(f"Agent failed for {problem_id}: {e}", exc_info=True)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
