"""
SPARK — AI incident response agent backend.
- Multi-tenant: users connect their own DT + GitLab via /connect
- Sandbox: /demo creates a no-credentials session for judges
- Simulate incidents per-session with scripted agent steps + real GitLab rollback
- Slack approval notifications + /slack/actions interactive endpoint
- Serves the React SPA at /
"""

import os
import re
import uuid
import time
import hmac
import hashlib
import logging
import threading
import requests
from datetime import datetime, timezone
from urllib.parse import urlencode
from flask import Flask, request, jsonify, send_from_directory, redirect
from flask_cors import CORS

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")
CORS(app)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─── Token encryption + session persistence ──────────────────────────────────
# Tokens (Dynatrace, GitLab, Slack) are encrypted at rest with Fernet when
# SESSION_ENC_KEY is set. Sessions are stored in Firestore when
# FIRESTORE_SESSIONS=1, otherwise in an in-memory dict (fine for one worker).
# Both layers degrade gracefully so the app runs with zero extra config.

SECRET_FIELDS = ("dt_token", "gl_token", "slack_bot_token")
_ENC_PREFIX   = "enc::"
_fernet_cache: list = []


def _fernet():
    """Lazily build the Fernet cipher from SESSION_ENC_KEY (cached, may be None)."""
    if _fernet_cache:
        return _fernet_cache[0]
    key = os.getenv("SESSION_ENC_KEY", "").strip()
    cipher = None
    if key:
        try:
            from cryptography.fernet import Fernet
            cipher = Fernet(key.encode())
        except Exception as e:
            logger.warning("Token encryption disabled (bad SESSION_ENC_KEY): %s", e)
    else:
        logger.info("SESSION_ENC_KEY not set — tokens stored unencrypted")
    _fernet_cache.append(cipher)
    return cipher


def _enc(value):
    cipher = _fernet()
    if not cipher or not isinstance(value, str) or not value:
        return value
    return _ENC_PREFIX + cipher.encrypt(value.encode()).decode()


def _dec(value):
    if not isinstance(value, str) or not value.startswith(_ENC_PREFIX):
        return value
    cipher = _fernet()
    if not cipher:
        return value
    try:
        return cipher.decrypt(value[len(_ENC_PREFIX):].encode()).decode()
    except Exception:
        return value


def _enc_row(d):
    return {k: (_enc(v) if k in SECRET_FIELDS else v) for k, v in d.items()}


def _dec_row(d):
    return {k: (_dec(v) if k in SECRET_FIELDS else v) for k, v in d.items()}


class SessionStore:
    """Dict-like store: Firestore-backed when enabled, else in-memory.
    Secret fields are encrypted on write and decrypted on read."""

    def __init__(self, collection: str):
        self._mem: dict = {}
        self._col = None
        if os.getenv("FIRESTORE_SESSIONS") == "1":
            try:
                from google.cloud import firestore
                self._col = firestore.Client().collection(collection)
                logger.info("SessionStore[%s]: Firestore backend active", collection)
            except Exception as e:
                logger.warning("Firestore unavailable for %s — using memory: %s", collection, e)

    def __setitem__(self, key, value):
        row = _enc_row(value)
        if self._col is not None:
            try:
                self._col.document(key).set(row)
                return
            except Exception as e:
                logger.warning("Firestore write failed for %s — using memory: %s", key, e)
        self._mem[key] = row

    def get(self, key, default=None):
        row = None
        if self._col is not None:
            try:
                doc = self._col.document(key).get()
                row = doc.to_dict() if doc.exists else None
            except Exception as e:
                logger.warning("Firestore read failed for %s: %s", key, e)
        if row is None:
            row = self._mem.get(key)
        return _dec_row(row) if row is not None else default

    def __getitem__(self, key):
        v = self.get(key)
        if v is None:
            raise KeyError(key)
        return v

    def __contains__(self, key):
        return self.get(key) is not None


sessions      = SessionStore(os.getenv("FIRESTORE_COLLECTION", "spark_sessions"))
oauth_pending = SessionStore("spark_oauth_pending")
incidents: dict = {}  # ephemeral demo state — mutated in place by worker threads, stays in memory

WEBHOOK_URL          = os.getenv("WEBHOOK_URL", "https://sre-webhook-366154347729.us-central1.run.app")
SLACK_BOT_TOKEN      = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL_ID     = os.getenv("SLACK_CHANNEL_ID", "")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
SLACK_CLIENT_ID      = os.getenv("SLACK_CLIENT_ID", "")
SLACK_CLIENT_SECRET  = os.getenv("SLACK_CLIENT_SECRET", "")
SLACK_OAUTH_SCOPES   = os.getenv("SLACK_OAUTH_SCOPES", "chat:write,channels:read,groups:read")

DEMO_SERVICES = [
    {"name": "payment-service",     "type": "Java",    "status": "healthy"},
    {"name": "checkout-api",        "type": "Node.js", "status": "healthy"},
    {"name": "user-auth-service",   "type": "Python",  "status": "healthy"},
    {"name": "inventory-service",   "type": "Go",      "status": "healthy"},
    {"name": "notification-worker", "type": "Node.js", "status": "healthy"},
    {"name": "api-gateway",         "type": "Go",      "status": "healthy"},
]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _dt_oauth_token(client_id: str, client_secret: str) -> str:
    """Exchange OAuth2 client credentials for a DT bearer token."""
    r = requests.post(
        "https://sso.dynatrace.com/sso/oauth2/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
        timeout=10,
    )
    if not r.ok:
        raise ValueError(f"Dynatrace OAuth2 failed: {r.json().get('error_description') or r.text[:200]}")
    return r.json()["access_token"]


def _dt_get_entities(dt_url: str, dt_token: str, bearer: bool = False):
    """
    Validate DT credentials and fetch service entities.
    bearer=True → use Authorization: Bearer (for OAuth2 access tokens).
    bearer=False → use Authorization: Api-Token (classic tokens).
    Falls back to the problems endpoint when entities.read scope is missing.
    """
    auth_header = f"Bearer {dt_token}" if bearer else f"Api-Token {dt_token}"
    headers     = {"Authorization": auth_header}
    last_err    = "Could not reach Dynatrace"

    # Attempt 1: entities endpoint
    entity_paths = [
        (f"{dt_url}/platform/classic/environment-api/v2/entities",
         {"entitySelector": "type(SERVICE)", "pageSize": "10"}),
        (f"{dt_url}/api/v2/entities",
         {"entitySelector": "type(SERVICE)", "pageSize": "10"}),
    ]
    for path, params in entity_paths:
        try:
            r = requests.get(path, headers=headers, params=params, timeout=10)
            if r.status_code == 200:
                data = r.json()
                entities = [
                    {
                        "name":   e.get("displayName") or e.get("entityId", "unknown"),
                        "id":     e.get("entityId", ""),
                        "type":   e.get("type", "SERVICE"),
                        "status": "healthy",
                    }
                    for e in data.get("entities", [])
                ]
                return entities, data.get("totalCount", len(entities))
            if r.status_code == 401:
                raise ValueError("Invalid Dynatrace token (401 Unauthorized). Check your credentials.")
            last_err = f"HTTP {r.status_code} from {path.split('/')[-2]}"
        except ValueError:
            raise
        except Exception as exc:
            last_err = str(exc)

    # Fallback: prove the token is valid via problems endpoint
    probe_paths = [
        f"{dt_url}/platform/classic/environment-api/v2/problems",
        f"{dt_url}/api/v2/problems",
        f"{dt_url}/platform/classic/environment-api/v2/metrics",
        f"{dt_url}/api/v2/metrics",
    ]
    for path in probe_paths:
        try:
            r = requests.get(path, headers=headers, params={"pageSize": "1"}, timeout=10)
            if r.status_code == 200:
                logger.info("DT credentials valid (entities scope missing — connected via %s)", path)
                return [], 0
            if r.status_code == 401:
                raise ValueError("Invalid Dynatrace token (401 Unauthorized). Check your credentials.")
        except ValueError:
            raise
        except Exception:
            continue

    raise ValueError(
        f"Cannot reach Dynatrace at {dt_url}. Last error: {last_err}. "
        "Check the URL (e.g. https://abc12345.apps.dynatrace.com) and your credentials."
    )


# ─── Slack channel resolution ─────────────────────────────────────────────────

_SLACK_ID_RE = re.compile(r"^[CGD][A-Z0-9]{6,}$")


def _slack_list_channels(bot_token: str, pages: int = 8):
    """Return [{id, name}] of channels the bot can see (public + private)."""
    out, cursor = [], ""
    for _ in range(pages):
        params = {"types": "public_channel,private_channel", "limit": 200, "exclude_archived": "true"}
        if cursor:
            params["cursor"] = cursor
        r = requests.get(
            "https://slack.com/api/conversations.list",
            headers={"Authorization": f"Bearer {bot_token}"}, params=params, timeout=8,
        ).json()
        if not r.get("ok"):
            raise ValueError(f"Could not list Slack channels: {r.get('error')}")
        out += [{"id": c["id"], "name": c.get("name", "")} for c in r.get("channels", [])]
        cursor = (r.get("response_metadata") or {}).get("next_cursor", "")
        if not cursor:
            break
    return out


def _resolve_slack_channel(bot_token: str, channel: str):
    """Accept a channel ID (C…/G…/D…) or a name (#alerts / alerts) and return
    (channel_id, channel_name). Names are resolved via conversations.list."""
    channel = (channel or "").strip().lstrip("#")
    if not channel:
        return "", None
    if _SLACK_ID_RE.match(channel):
        return channel, None
    for c in _slack_list_channels(bot_token):
        if c["name"] == channel:
            return c["id"], c["name"]
    raise ValueError(f"Slack channel '#{channel}' not found — invite the bot to it first")


# ─── Connect / Demo ───────────────────────────────────────────────────────────

@app.route("/connect", methods=["POST"])
def connect():
    data          = request.get_json() or {}
    dt_url        = (data.get("dt_url") or "").rstrip("/")
    dt_token      = (data.get("dt_token") or "").strip()
    dt_client_id  = (data.get("dt_client_id") or "").strip()
    dt_client_sec = (data.get("dt_client_secret") or "").strip()
    gl_url        = (data.get("gl_url") or "https://gitlab.com").rstrip("/")
    gl_token      = (data.get("gl_token") or "").strip()
    gl_project    = (data.get("gl_project_id") or "").strip()

    if not dt_url:
        return jsonify({"error": "Dynatrace URL required"}), 400
    if not dt_token and not (dt_client_id and dt_client_sec):
        return jsonify({"error": "Provide either an API Token or OAuth2 Client ID + Secret"}), 400
    if not gl_token:
        return jsonify({"error": "GitLab token required"}), 400

    # Validate Dynatrace — support both classic API tokens and OAuth2 client credentials
    try:
        if dt_client_id and dt_client_sec:
            bearer_token = _dt_oauth_token(dt_client_id, dt_client_sec)
            services, services_count = _dt_get_entities(dt_url, bearer_token, bearer=True)
            stored_token = bearer_token
        else:
            services, services_count = _dt_get_entities(dt_url, dt_token)
            stored_token = dt_token
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    env_name = dt_url.replace("https://", "").split(".")[0]

    # Validate GitLab
    try:
        r = requests.get(
            f"{gl_url}/api/v4/user",
            headers={"PRIVATE-TOKEN": gl_token}, timeout=8,
        )
        r.raise_for_status()
        gl_username = r.json().get("username", "unknown")
    except Exception as e:
        return jsonify({"error": f"GitLab connection failed: {e}"}), 400

    project_name = gl_project
    if gl_project:
        try:
            r = requests.get(
                f"{gl_url}/api/v4/projects/{gl_project}",
                headers={"PRIVATE-TOKEN": gl_token}, timeout=8,
            )
            if r.status_code == 200:
                project_name = r.json().get("path_with_namespace", gl_project)
        except Exception:
            pass

    # Validate Slack (optional — step 3 of the connect wizard).
    # The bot token comes either from a one-click OAuth handshake (slack_oauth_state,
    # token kept server-side) or a manually pasted token. Either way this session
    # gets its OWN incident notifications instead of the shared workspace.
    sl_state     = (data.get("slack_oauth_state") or "").strip()
    sl_bot_token = (data.get("slack_bot_token") or "").strip()
    sl_channel   = (data.get("slack_channel_id") or "").strip()
    slack_connected = False
    slack_team      = None
    slack_bot_user  = None
    slack_channel_name = None

    if sl_state:
        pend = oauth_pending.get(sl_state)
        if not pend or not pend.get("authed"):
            return jsonify({"error": "Slack authorization expired — click Add to Slack again"}), 400
        sl_bot_token = pend.get("slack_bot_token", "")
        slack_team   = pend.get("team")

    if sl_bot_token:
        if not sl_channel:
            return jsonify({"error": "Pick a Slack channel for incident alerts"}), 400
        try:
            auth = requests.post(
                "https://slack.com/api/auth.test",
                headers={"Authorization": f"Bearer {sl_bot_token}"}, timeout=8,
            ).json()
        except Exception as e:
            return jsonify({"error": f"Slack connection failed: {e}"}), 400
        if not auth.get("ok"):
            return jsonify({"error": f"Slack auth failed: {auth.get('error')}. Check the bot token."}), 400
        try:
            sl_channel, slack_channel_name = _resolve_slack_channel(sl_bot_token, sl_channel)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        slack_connected = True
        slack_team      = slack_team or auth.get("team")
        slack_bot_user  = auth.get("user")

    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "dt_url":              dt_url,
        "dt_token":            stored_token,
        "gl_url":              gl_url,
        "gl_token":            gl_token,
        "gl_project_id":       gl_project,
        "env_name":            env_name,
        "services_count":      services_count,
        "services":            services,
        "gl_username":         gl_username,
        "project_name":        project_name,
        "slack_bot_token":     sl_bot_token,
        "slack_channel_id":    sl_channel,
        "slack_channel_name":  slack_channel_name,
        "slack_connected":     slack_connected,
        "slack_team":          slack_team,
        "created_at":          datetime.now(timezone.utc).isoformat(),
    }

    return jsonify({
        "session_id":         session_id,
        "env_name":           env_name,
        "services_count":     services_count,
        "services":           services,
        "gl_username":        gl_username,
        "project_name":       project_name,
        "slack_connected":    slack_connected,
        "slack_team":         slack_team,
        "slack_bot_user":     slack_bot_user,
        "slack_channel_name": slack_channel_name,
        "webhook_url":        f"{WEBHOOK_URL}/dynatrace/webhook?session={session_id}",
    })


@app.route("/demo", methods=["POST"])
def start_demo():
    """No-credentials sandbox session for judges who don't have Dynatrace."""
    session_id = "demo-" + str(uuid.uuid4())[:6]
    sessions[session_id] = {
        "dt_url":         "https://demo.apps.dynatrace.com",
        "gl_url":         "https://gitlab.com",
        "gl_project_id":  "",
        "gl_token":       "",
        "env_name":       "demo",
        "services_count": len(DEMO_SERVICES),
        "services":       DEMO_SERVICES,
        "gl_username":    "demo-user",
        "project_name":   "payment-service",
        "is_demo":        True,
        "created_at":     datetime.now(timezone.utc).isoformat(),
    }
    return jsonify({
        "session_id":     session_id,
        "env_name":       "demo",
        "services_count": len(DEMO_SERVICES),
        "services":       DEMO_SERVICES,
        "gl_username":    "demo-user",
        "project_name":   "payment-service",
        "is_demo":        True,
        "webhook_url":    f"{WEBHOOK_URL}/dynatrace/webhook?session={session_id}",
    })


@app.route("/sessions/<session_id>", methods=["GET"])
def get_session(session_id):
    s = sessions.get(session_id)
    if not s:
        return jsonify({"error": "Not found"}), 404
    return jsonify({k: v for k, v in s.items() if k not in ("dt_token", "gl_token", "slack_bot_token")})


# ─── Incidents ────────────────────────────────────────────────────────────────

@app.route("/incidents", methods=["POST"])
def create_incident():
    data   = request.get_json() or {}
    pre_id = data.get("incident_id")
    if pre_id and pre_id in incidents:
        inc = incidents[pre_id]
        inc.update({k: v for k, v in data.items() if k != "incident_id"})
        inc["status"] = "awaiting_decision"
        return jsonify({"incident_id": pre_id}), 200

    incident_id = str(uuid.uuid4())[:8]
    incidents[incident_id] = {
        "incident_id": incident_id,
        "created_at":  datetime.now(timezone.utc).isoformat(),
        "status":      "awaiting_decision",
        "decision":    None,
        "reason":      None,
        "steps":       [],
        **data,
    }
    return jsonify({"incident_id": incident_id}), 201


@app.route("/incidents", methods=["GET"])
def list_incidents():
    session_id = request.args.get("session")
    result = list(incidents.values())
    if session_id:
        result = [i for i in result if i.get("session_id") == session_id]
    return jsonify(result)


@app.route("/incidents/<incident_id>", methods=["GET"])
def get_incident(incident_id):
    inc = incidents.get(incident_id)
    if not inc:
        return jsonify({"error": "Not found"}), 404
    return jsonify(inc)


@app.route("/incidents/<incident_id>/decide", methods=["POST"])
def decide(incident_id):
    inc = incidents.get(incident_id)
    if not inc:
        return jsonify({"error": "Not found"}), 404

    data     = request.get_json() or {}
    decision = data.get("decision")
    if decision not in ("approved", "rejected"):
        return jsonify({"error": "decision must be approved or rejected"}), 400

    inc["decision"]   = decision
    inc["reason"]     = data.get("reason", "")
    inc["decided_at"] = datetime.now(timezone.utc).isoformat()
    inc["decided_by"] = data.get("engineer", "on-call")

    if decision == "approved":
        session = sessions.get(inc.get("session_id"))
        threading.Thread(
            target=_execute_rollback, args=(incident_id, session), daemon=True,
        ).start()
    else:
        inc["status"] = "rejected"

    return jsonify(inc)


@app.route("/incidents/<incident_id>/step", methods=["POST"])
def add_step(incident_id):
    inc = incidents.get(incident_id)
    if not inc:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json() or {}
    step = {
        "label":  data.get("label", ""),
        "status": data.get("status", "done"),
        "ts":     datetime.now(timezone.utc).isoformat(),
    }
    inc.setdefault("steps", []).append(step)
    return jsonify(step), 201


@app.route("/incidents/<incident_id>/resolve", methods=["POST"])
def resolve_incident(incident_id):
    inc = incidents.get(incident_id)
    if not inc:
        return jsonify({"error": "Not found"}), 404
    inc["status"]      = "resolved"
    inc["resolved_at"] = datetime.now(timezone.utc).isoformat()
    return jsonify(inc)


# ─── Simulate ────────────────────────────────────────────────────────────────

@app.route("/sessions/<session_id>/simulate", methods=["POST"])
def simulate_incident(session_id):
    session = sessions.get(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    incident_id = str(uuid.uuid4())[:8]
    incidents[incident_id] = {
        "incident_id":        incident_id,
        "session_id":         session_id,
        "created_at":         datetime.now(timezone.utc).isoformat(),
        "status":             "investigating",
        "steps":              [],
        "decision":           None,
        "reason":             None,
        "summary":            None,
        "root_cause":         None,
        "recommended_action": None,
        "confidence_score":   None,
        "rollback_version":   None,
        "severity":           "PERFORMANCE",
    }

    threading.Thread(
        target=_simulate_investigation, args=(incident_id, session_id), daemon=True,
    ).start()

    return jsonify({"incident_id": incident_id})


def _simulate_investigation(incident_id: str, session_id: str):
    STEPS = [
        (1.2, "Fetching problem details from Dynatrace"),
        (2.8, "Querying memory metrics (last 60 min)"),
        (1.8, "Querying response time metrics"),
        (2.2, "Searching application logs"),
        (1.9, "Checking recent GitLab deployments"),
        (2.5, "Correlating deployment timeline with anomaly start"),
        (1.8, "Forming root cause hypothesis (confidence: 94%)"),
    ]

    for delay, label in STEPS:
        time.sleep(delay)
        inc = incidents.get(incident_id)
        if not inc:
            return
        inc["steps"].append({
            "label": label, "status": "done",
            "ts": datetime.now(timezone.utc).isoformat(),
        })

    time.sleep(1.0)

    session = sessions.get(session_id, {})
    project = session.get("project_name") or session.get("gl_project_id") or "payment-service"

    inc = incidents.get(incident_id)
    if not inc:
        return

    inc.update({
        "status":             "awaiting_decision",
        "summary":            f"Memory leak detected in {project} — container RSS +340%",
        "root_cause": (
            "Deployment pushed 32 minutes ago introduced a memory leak in the v2.3.1 audit-log "
            "handler — full transaction payloads appended to an unbounded in-memory list with no "
            "cap or TTL. Container memory grew 340% over 20 min (512 MB → 1.8 GB), degrading "
            "response times from 120 ms to 890 ms p95 until the worker was OOM-killed."
        ),
        "recommended_action": (
            f"Roll back {project} to the previous stable version. The anomaly start time "
            "correlates with the deployment timestamp at 100% confidence. "
            "No database migrations were included — rollback is safe."
        ),
        "confidence_score":   0.94,
        "rollback_version":   "v2.3.0",
    })

    # Notify Slack (no-op if SLACK_BOT_TOKEN not configured)
    threading.Thread(target=_notify_slack, args=(incident_id,), daemon=True).start()


def _execute_rollback(incident_id: str, session: dict):
    inc = incidents.get(incident_id)
    if not inc:
        return

    for delay, label in [
        (1.2, "Engineer approved — initiating rollback sequence"),
        (1.8, "Connecting to GitLab pipeline API"),
    ]:
        time.sleep(delay)
        inc.setdefault("steps", []).append({
            "label": label, "status": "done",
            "ts": datetime.now(timezone.utc).isoformat(),
        })

    pipeline_url = None
    is_demo = (session or {}).get("is_demo", False)

    if not is_demo and session and session.get("gl_token") and session.get("gl_project_id"):
        try:
            r = requests.post(
                f"{session.get('gl_url','https://gitlab.com')}/api/v4/projects/{session['gl_project_id']}/pipeline",
                headers={"PRIVATE-TOKEN": session["gl_token"], "Content-Type": "application/json"},
                json={
                    "ref": "master",
                    "variables": [
                        {"key": "ROLLBACK_VERSION", "value": inc.get("rollback_version", "v2.3.0")},
                        {"key": "TRIGGERED_BY",     "value": "mttr-ai"},
                    ],
                },
                timeout=10,
            )
            if r.status_code in (200, 201):
                pdata = r.json()
                pipeline_url = pdata.get("web_url")
                inc["pipeline_url"] = pipeline_url
                inc["steps"].append({
                    "label":  f"GitLab pipeline #{pdata.get('id')} triggered — rollback running",
                    "status": "done", "ts": datetime.now(timezone.utc).isoformat(),
                })
        except Exception as e:
            logger.warning(f"GitLab trigger failed: {e}")

    if not pipeline_url:
        time.sleep(1.5)
        inc["steps"].append({
            "label":  "Rollback pipeline triggered (demo mode)",
            "status": "done", "ts": datetime.now(timezone.utc).isoformat(),
        })

    for delay, label in [
        (2.2, "Monitoring memory metrics — heap returning to baseline"),
        (2.0, "Response times normalizing (890 ms → 145 ms p95)"),
        (1.8, "Dynatrace problem status: RESOLVED"),
    ]:
        time.sleep(delay)
        inc.setdefault("steps", []).append({
            "label": label, "status": "done",
            "ts": datetime.now(timezone.utc).isoformat(),
        })

    inc["status"]      = "resolved"
    inc["resolved_at"] = datetime.now(timezone.utc).isoformat()


# ─── Slack approval notifications ────────────────────────────────────────────

def _session_slack(incident_id: str):
    """Resolve the Slack bot token + channel for an incident.
    Prefers the per-session credentials the user connected at /connect (step 3),
    falling back to the shared SLACK_BOT_TOKEN / SLACK_CHANNEL_ID env vars."""
    inc = incidents.get(incident_id) or {}
    session = sessions.get(inc.get("session_id")) or {}
    bot_token = session.get("slack_bot_token") or SLACK_BOT_TOKEN
    channel   = session.get("slack_channel_id") or SLACK_CHANNEL_ID
    return bot_token, channel


def _notify_slack(incident_id: str):
    """Post a Slack Block Kit approval card when an incident needs a decision."""
    bot_token, channel_cfg = _session_slack(incident_id)
    if not bot_token or not channel_cfg:
        logger.warning("Slack not configured for this session — no bot token or channel")
        return
    inc = incidents.get(incident_id)
    if not inc:
        return

    pct = int((inc.get("confidence_score") or 0) * 100)
    summary = inc.get("summary", "Incident detected")
    fallback_text = f"🔥 SPARK: {summary} — {pct}% confidence. Approval needed."

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🔥 SPARK — Incident Needs Your Approval", "emoji": True},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{summary}*"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Root Cause:*\n{inc.get('root_cause', 'Investigating...')[:300]}"},
                {"type": "mrkdwn", "text": f"*AI Confidence:*\n{pct}%"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Recommended:* {inc.get('recommended_action', '')[:200]}\n*Rollback to:* `{inc.get('rollback_version', 'N/A')}`"},
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button", "style": "primary",
                    "text": {"type": "plain_text", "text": "✅ Approve Rollback", "emoji": True},
                    "url": f"{APP_URL}/approve/{incident_id}",
                    "action_id": "spark_approve",
                },
                {
                    "type": "button", "style": "danger",
                    "text": {"type": "plain_text", "text": "❌ Reject", "emoji": True},
                    "url": f"{APP_URL}/reject/{incident_id}",
                    "action_id": "spark_reject",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🔥 View Dashboard", "emoji": True},
                    "url": f"{APP_URL}/dashboard",
                    "action_id": "spark_dashboard",
                },
            ],
        },
    ]

    headers = {"Authorization": f"Bearer {bot_token}", "Content-Type": "application/json"}
    channel = channel_cfg

    try:
        # For DM channels (D...) ensure the conversation is open first
        if channel_cfg.startswith("D"):
            open_r = requests.post(
                "https://slack.com/api/conversations.open",
                headers=headers,
                json={"channel": channel_cfg},
                timeout=8,
            )
            open_data = open_r.json()
            if open_data.get("ok"):
                channel = open_data["channel"]["id"]
                logger.info(f"DM conversation opened: {channel}")
            else:
                logger.warning(f"conversations.open failed: {open_data.get('error')} — posting direct anyway")

        r = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers=headers,
            json={"channel": channel, "text": fallback_text, "blocks": blocks},
            timeout=8,
        )
        data = r.json()
        if data.get("ok"):
            logger.info(f"Slack notification sent for {incident_id} (ts={data.get('ts')})")
            incidents[incident_id]["slack_ts"] = data.get("ts")
            incidents[incident_id]["slack_sent"] = True
        else:
            logger.warning(f"Slack chat.postMessage error: {data.get('error')} | channel={channel}")
            incidents[incident_id]["slack_error"] = data.get("error")
    except Exception as e:
        logger.warning(f"Slack notify failed: {e}")
        incidents[incident_id]["slack_error"] = str(e)


def _update_slack_message(incident_id: str, decision: str, engineer: str):
    """Replace the approval buttons with a resolved status message."""
    bot_token, channel_cfg = _session_slack(incident_id)
    if not bot_token or not channel_cfg:
        return
    inc = incidents.get(incident_id)
    if not inc or not inc.get("slack_ts"):
        return
    emoji = "✅" if decision == "approved" else "❌"
    text  = f"{emoji} *{decision.capitalize()}* by {engineer} at {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
    try:
        requests.post(
            "https://slack.com/api/chat.update",
            headers={"Authorization": f"Bearer {bot_token}", "Content-Type": "application/json"},
            json={"channel": channel_cfg, "ts": inc["slack_ts"], "text": text, "blocks": [
                {"type": "section", "text": {"type": "mrkdwn", "text": text}},
            ]},
            timeout=8,
        )
    except Exception as e:
        logger.warning(f"Slack update failed: {e}")


@app.route("/slack/test", methods=["GET"])
def slack_test():
    """Diagnostic endpoint — returns Slack config state and tests posting."""
    if not SLACK_BOT_TOKEN:
        return jsonify({"error": "SLACK_BOT_TOKEN not set in environment"}), 503
    if not SLACK_CHANNEL_ID:
        return jsonify({"error": "SLACK_CHANNEL_ID not set in environment"}), 503
    try:
        r = requests.post(
            "https://slack.com/api/auth.test",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            timeout=8,
        )
        auth = r.json()
        if not auth.get("ok"):
            return jsonify({"error": f"Slack auth failed: {auth.get('error')}", "token_prefix": SLACK_BOT_TOKEN[:12] + "..."}), 400
        return jsonify({
            "ok": True,
            "bot_user": auth.get("user"),
            "team": auth.get("team"),
            "channel_id": SLACK_CHANNEL_ID,
            "signing_secret_set": bool(SLACK_SIGNING_SECRET),
            "token_prefix": SLACK_BOT_TOKEN[:12] + "...",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/slack/actions", methods=["POST"])
def slack_actions():
    """Handle interactive Slack button clicks (approve / reject)."""
    # Read raw body FIRST — must happen before any form parsing
    import json as _json
    body_text = request.get_data(as_text=True)

    # Verify Slack signature
    if SLACK_SIGNING_SECRET:
        ts  = request.headers.get("X-Slack-Request-Timestamp", "")
        sig = request.headers.get("X-Slack-Signature", "")
        base = f"v0:{ts}:{body_text}"
        h = hmac.new(SLACK_SIGNING_SECRET.encode(), base.encode(), hashlib.sha256)
        expected = "v0=" + h.hexdigest()
        if not hmac.compare_digest(expected, sig):
            return jsonify({"error": "Invalid signature"}), 403

    import urllib.parse as _urlparse
    params  = _urlparse.parse_qs(body_text)
    payload = _json.loads(params.get("payload", ["{}"])[0])
    actions = payload.get("actions", [])
    user    = payload.get("user", {}).get("name", "slack-user")

    for action in actions:
        action_id   = action.get("action_id", "")
        incident_id = action.get("value", "")
        decision    = "approved" if action_id == "spark_approve" else "rejected"

        inc = incidents.get(incident_id)
        if not inc or inc.get("decision"):
            continue

        inc["decision"]   = decision
        inc["reason"]     = f"Via Slack by @{user}"
        inc["decided_at"] = datetime.now(timezone.utc).isoformat()
        inc["decided_by"] = user

        if decision == "approved":
            session = sessions.get(inc.get("session_id"))
            threading.Thread(target=_execute_rollback, args=(incident_id, session), daemon=True).start()
        else:
            inc["status"] = "rejected"

        _update_slack_message(incident_id, decision, user)

    return jsonify({"response_type": "ephemeral", "text": "Decision recorded ✓"})


# ─── Direct approve/reject via URL (used by Slack URL buttons) ───────────────

APP_URL = os.getenv("APP_URL", "https://spark-366154347729.us-central1.run.app")


# ─── Slack "Add to Slack" OAuth (one-click connect) ──────────────────────────
# Enabled only when SLACK_CLIENT_ID + SLACK_CLIENT_SECRET are set. The bot token
# returned by Slack is kept server-side keyed by an opaque `state` handle — the
# browser only ever sees the handle, never the token.

def _oauth_popup_html(state=None, team=None, error=None):
    import json as _j
    import html as _h
    msg       = _j.dumps({"type": "spark_slack_oauth", "state": state, "team": team, "error": error})
    target    = _j.dumps(APP_URL)  # pin postMessage to our origin, never "*"
    safe_note = _h.escape(f"✅ Connected to {team}" if not error else f"❌ {error}")
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Slack</title></head>
<body style="background:#08080a;color:#f0f0f2;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
<div style="text-align:center"><div style="font-size:40px">{'💬' if not error else '⚠️'}</div>
<p>{safe_note}. You can close this window.</p></div>
<script>
  try {{ if (window.opener) window.opener.postMessage({msg}, {target}); }} catch (e) {{}}
  setTimeout(function () {{ window.close(); }}, 900);
</script></body></html>"""


@app.route("/slack/oauth/config")
def slack_oauth_config():
    return jsonify({"enabled": bool(SLACK_CLIENT_ID and SLACK_CLIENT_SECRET)})


@app.route("/slack/oauth/start")
def slack_oauth_start():
    if not (SLACK_CLIENT_ID and SLACK_CLIENT_SECRET):
        return jsonify({"error": "Slack OAuth not configured"}), 503
    state = uuid.uuid4().hex
    oauth_pending[state] = {"authed": False, "created_at": datetime.now(timezone.utc).isoformat()}
    url = "https://slack.com/oauth/v2/authorize?" + urlencode({
        "client_id":    SLACK_CLIENT_ID,
        "scope":        SLACK_OAUTH_SCOPES,
        "redirect_uri": f"{APP_URL}/slack/oauth/callback",
        "state":        state,
    })
    return redirect(url)


@app.route("/slack/oauth/callback")
def slack_oauth_callback():
    code  = request.args.get("code", "")
    state = request.args.get("state", "")
    if not code or not state or oauth_pending.get(state) is None:
        return _oauth_popup_html(error="Invalid or expired authorization"), 400
    try:
        d = requests.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id":     SLACK_CLIENT_ID,
                "client_secret": SLACK_CLIENT_SECRET,
                "code":          code,
                "redirect_uri":  f"{APP_URL}/slack/oauth/callback",
            }, timeout=10,
        ).json()
    except Exception as e:
        return _oauth_popup_html(error=str(e)), 400
    if not d.get("ok"):
        return _oauth_popup_html(error=d.get("error", "oauth_failed")), 400

    team = (d.get("team") or {}).get("name")
    oauth_pending[state] = {
        "authed":          True,
        "slack_bot_token": d.get("access_token", ""),
        "team":            team,
        "created_at":      datetime.now(timezone.utc).isoformat(),
    }
    return _oauth_popup_html(state=state, team=team)


@app.route("/slack/channels")
def slack_channels():
    """List channels for a completed OAuth handshake (token stays server-side)."""
    state = request.args.get("state", "")
    pend  = oauth_pending.get(state)
    if not pend or not pend.get("authed"):
        return jsonify({"error": "Not authorized"}), 400
    try:
        channels = _slack_list_channels(pend.get("slack_bot_token", ""))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    channels.sort(key=lambda c: c["name"])
    return jsonify({"channels": channels})


@app.route("/approve/<incident_id>")
def approve_redirect(incident_id):
    """One-click approve from Slack URL button — approves and sends to dashboard."""
    inc = incidents.get(incident_id)
    if not inc:
        return "<h2>Incident not found (session may have expired). <a href='/dashboard'>Go to dashboard</a></h2>", 404
    if inc.get("decision"):
        return f"<script>window.location='{APP_URL}/dashboard'</script>", 200

    inc["decision"]   = "approved"
    inc["reason"]     = "Approved via Slack"
    inc["decided_at"] = datetime.now(timezone.utc).isoformat()
    inc["decided_by"] = "slack-admin"

    session = sessions.get(inc.get("session_id"))
    threading.Thread(target=_execute_rollback, args=(incident_id, session), daemon=True).start()
    threading.Thread(target=_update_slack_message, args=(incident_id, "approved", "slack-admin"), daemon=True).start()

    # Redirect to dashboard so admin watches the live rollback
    return f"""<!doctype html>
<html><head><meta http-equiv="refresh" content="0;url={APP_URL}/dashboard">
<title>Approved</title></head>
<body style="background:#08080a;color:#f0f0f2;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
<div style="text-align:center"><div style="font-size:48px">✅</div>
<h2 style="color:#16a34a">Rollback Approved</h2>
<p style="color:#6b6b7a">Redirecting to SPARK dashboard...</p></div></body></html>""", 200


@app.route("/reject/<incident_id>")
def reject_redirect(incident_id):
    """One-click reject from Slack URL button."""
    inc = incidents.get(incident_id)
    if not inc:
        return "<h2>Incident not found. <a href='/dashboard'>Go to dashboard</a></h2>", 404
    if inc.get("decision"):
        return f"<script>window.location='{APP_URL}/dashboard'</script>", 200

    inc["decision"]   = "rejected"
    inc["reason"]     = "Rejected via Slack"
    inc["decided_at"] = datetime.now(timezone.utc).isoformat()
    inc["decided_by"] = "slack-admin"
    inc["status"]     = "rejected"

    threading.Thread(target=_update_slack_message, args=(incident_id, "rejected", "slack-admin"), daemon=True).start()

    return f"""<!doctype html>
<html><head><meta http-equiv="refresh" content="0;url={APP_URL}/dashboard">
<title>Rejected</title></head>
<body style="background:#08080a;color:#f0f0f2;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
<div style="text-align:center"><div style="font-size:48px">❌</div>
<h2 style="color:#dc2626">Rollback Rejected</h2>
<p style="color:#6b6b7a">Redirecting to SPARK dashboard...</p></div></body></html>""", 200


# ─── Health + SPA ────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path):
    target = os.path.join(STATIC_DIR, path)
    if path and os.path.exists(target):
        return send_from_directory(STATIC_DIR, path)
    return send_from_directory(STATIC_DIR, "index.html")


@app.errorhandler(404)
@app.errorhandler(405)
def spa_fallback(e):
    """SPA client-side routes (/connect, /dashboard, /demo) share names with the
    POST API routes, so a browser GET/refresh on them would otherwise 404/405.
    Serve the app shell for HTML navigations; keep JSON errors for API clients."""
    if request.method == "GET" and "text/html" in request.headers.get("Accept", ""):
        return send_from_directory(STATIC_DIR, "index.html")
    return jsonify({"error": "Not found"}), getattr(e, "code", 404)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
