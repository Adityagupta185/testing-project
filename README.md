# <img width="100" src="https://github.com/user-attachments/assets/f27e7a36-4e21-4760-8d2c-4a3a1bce734f" align="center" /> SPARK — Autonomous SRE Agent


SPARK turns a production alert into a diagnosed root cause and a one-click remediation. When Dynatrace detects a problem, an AI agent built on Google Cloud investigates the live telemetry, identifies the root cause, proposes a fix, and — after a human approves — executes a rollback through GitLab.

**Track:** Dynatrace · **Built with:** Google Cloud (Vertex AI Gemini, Agent Development Kit, Cloud Run)

**Live:** [spark-366154347729.us-central1.run.app](https://spark-366154347729.us-central1.run.app) — click **Live Demo** to watch the full detect → diagnose → approve → rollback flow in ~30 seconds, no account required.

---

## The Problem

Mean Time To Resolution (MTTR) for production incidents is dominated by *investigation*, not repair. An on-call engineer, woken at 3 a.m., spends 30–60 minutes correlating alerts, metrics, logs, and recent deployments before they even know what to fix. SPARK compresses that investigation from tens of minutes to seconds, while keeping a human in control of every action that changes production.

## What It Does

```
Dynatrace alert
   -> Webhook (Cloud Run)
      -> Agent (Vertex AI Gemini 2.5 Flash, Google ADK tool-use loop)
           - reads the Dynatrace problem, metrics, and logs
           - reviews recent GitLab deployments
           - determines root cause and whether a rollback is warranted
      -> Approval request: root cause, evidence, and recommended action
           - pushed to Slack and shown on the dashboard
   -> Engineer approves (one tap in Slack, or on the dashboard)
      -> GitLab pipeline executes the rollback
      -> Incident marked resolved
```

The agent does not blindly act. It distinguishes incidents that a rollback will fix (a bad deploy) from those it will not (a resource leak with no preceding deploy), and recommends accordingly.

## Onboarding & Approvals

SPARK is multi-tenant: a user connects their own stack through a short wizard — **Dynatrace** (API token or OAuth2), **GitLab** (project + token), and **Slack** (one-click *Add to Slack*, or a bot token). Each session is isolated, so incidents and notifications are scoped to the tenant that created them.

- **Slack-in-the-loop.** When the agent reaches a diagnosis, an approval card is posted to the tenant's own Slack channel. Approve or reject from Slack and the rollback executes automatically — the same decision is mirrored on the dashboard.
- **Credentials stay protected.** Tokens are never returned to the browser; Slack OAuth keeps the bot token server-side behind an opaque handle. Session tokens are encrypted at rest (Fernet), with optional Firestore persistence.
- **No-account demo.** A sandbox session (`/demo`) runs the entire flow end-to-end without any credentials, for evaluation.

## Architecture

| Layer | Component | Technology |
|-------|-----------|------------|
| Reasoning | `agent/agent.py` | Google ADK `Agent` + `Runner`, Vertex AI Gemini 2.5 Flash |
| Observability | `agent/tools/dynatrace_*.py` | Dynatrace API / MCP — problems, metrics, logs |
| Remediation | `agent/tools/gitlab_client.py` | GitLab API — deployment history, pipeline rollback |
| Ingress | `webhook/` | Cloud Run service receiving Dynatrace alerts |
| Interface | `frontend/` | React approval dashboard + Flask backend (`server.py`) |
| Notifications | `frontend/server.py` | Slack approval cards — *Add to Slack* OAuth or bot token, per tenant |
| Demo target | `payment-service/` | Flask payment API with a seeded memory-leak fault |
| Evaluation | `postmortems/` | Benchmark of the agent against real production post-mortems |

The agent runs a tool-use loop. Gemini decides which tool to call — `dynatrace_get_problem`, `dynatrace_get_metrics`, `dynatrace_get_logs`, `gitlab_get_recent_deployments`, `gitlab_trigger_rollback`, `send_approval_request` — and reasons over the returned evidence until it reaches a conclusion.

## Repository Structure

```
spark/
├── sre-copilot/         # The agent and its interfaces
│   ├── agent/           # Gemini tool-use agent + Dynatrace/GitLab tools
│   ├── webhook/         # Cloud Run alert receiver
│   ├── frontend/        # React approval UI + Flask backend
│   └── scripts/         # Dynatrace webhook setup, incident injection
├── payment-service/     # Demo target service with an injectable fault
├── postmortems/         # Evaluation harness over real-world incidents
├── LICENSE              # MIT
└── README.md
```

## Getting Started

### Prerequisites
- Python 3.11+, Node.js 18+
- A Google Cloud project with Vertex AI enabled
- A Dynatrace environment and a GitLab project

### 1. Configure

```bash
cd sre-copilot
cp .env.example .env
# Fill in your own Google Cloud, Dynatrace, and GitLab values.
```

All configuration is read from environment variables. No credentials are committed to this repository — see `.env.example` for the required keys.

### 2. Run the agent backend

```bash
cd sre-copilot
pip install -r agent/requirements.txt
# Local run with Application Default Credentials:
python -m webhook.main
```

### 3. Run the approval UI

```bash
cd sre-copilot/frontend
npm install
npm run build
python server.py
```

### 4. Trigger a demo incident

```bash
python sre-copilot/scripts/inject_fake_incident.py <webhook-url>
```

### Deploy to Cloud Run

```bash
gcloud run deploy sre-webhook --source sre-copilot --region us-central1
```

## Evaluation

SPARK was benchmarked against five real production post-mortems — including incidents from Cloudflare, PagerDuty, and rust-lang — that took human engineers between 15 minutes and several hours to resolve.

```bash
python postmortems/runner.py --scenario 01   # run a single scenario (01–05)
```

The hardest scenario models a database out-of-memory failure with no preceding deployment. The correct answer is *not* to roll back, but to address the underlying query. The agent identifies this and withholds a rollback — demonstrating judgement, not just automation.

## Technologies Used

- **Google Cloud:** Vertex AI (Gemini 2.5 Flash), Agent Development Kit (ADK), Cloud Run, Firestore (optional session store)
- **Dynatrace (partner):** problem, metrics, and log APIs via the partner integration
- **GitLab:** deployment history and CI/CD pipeline-driven rollback
- **Slack:** OAuth (*Add to Slack*) and Block Kit approval cards for human-in-the-loop sign-off
- **Application:** Python (Flask), React

## Findings and Learnings

- **The bottleneck is investigation, not action.** Giving the model structured access to the same signals an engineer checks — problem, metrics, logs, deploy history — is what collapses MTTR.
- **Judgement matters more than automation.** The most valuable behaviour was the agent *declining* to roll back when the evidence did not support it. A remediation agent that always acts is dangerous; one that reasons about whether to act is trustworthy.
- **Keep a human at the decision boundary.** The agent investigates autonomously but never changes production without explicit approval. This is the design that makes autonomous SRE tooling acceptable to operate.
- **Evidence must be internally consistent.** Grounding the agent strictly in live telemetry, rather than mixed fallbacks, was essential for the reasoning to hold up under scrutiny.

## License

Released under the [MIT License](LICENSE).
