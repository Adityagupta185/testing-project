"""
MTTR.ai Post-Mortem Test Suite
Runs the Gemini agent against real-world incident scenarios from
github.com/danluu/post-mortems and scores its performance.

Usage:
    python runner.py                  # run all scenarios
    python runner.py --scenario 02    # run one scenario by prefix
"""

import os, sys, json, time, argparse, textwrap
from pathlib import Path
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

env_path = Path(__file__).parent.parent / "sre-copilot" / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from openai import OpenAI

client = OpenAI(
    api_key=os.environ["GEMINI_API_KEY"],
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    timeout=120.0,
)
MODEL = "gemini-2.5-flash"

TOOLS = [
    {"type": "function", "function": {
        "name": "dynatrace_get_problem",
        "description": "Fetch Dynatrace problem details: severity, affected entities, evidence.",
        "parameters": {"type": "object", "properties": {
            "problem_id": {"type": "string"}
        }, "required": ["problem_id"]}
    }},
    {"type": "function", "function": {
        "name": "dynatrace_get_metrics",
        "description": "Pull time-series metrics (CPU, memory, latency, error rate) from Dynatrace.",
        "parameters": {"type": "object", "properties": {
            "entity_id": {"type": "string"},
            "metric":    {"type": "string"},
            "from_minutes_ago": {"type": "integer", "default": 60}
        }, "required": ["entity_id", "metric"]}
    }},
    {"type": "function", "function": {
        "name": "dynatrace_get_logs",
        "description": "Fetch log lines from Dynatrace for a service around the incident window.",
        "parameters": {"type": "object", "properties": {
            "service_name":     {"type": "string"},
            "from_minutes_ago": {"type": "integer", "default": 30},
            "limit":            {"type": "integer", "default": 50}
        }, "required": ["service_name"]}
    }},
    {"type": "function", "function": {
        "name": "gitlab_get_recent_deployments",
        "description": "List recent GitLab deployments. Returns version, timestamp, commit message.",
        "parameters": {"type": "object", "properties": {
            "project_id": {"type": "string"},
            "hours_back": {"type": "integer", "default": 3}
        }, "required": ["project_id"]}
    }},
    {"type": "function", "function": {
        "name": "gitlab_trigger_rollback",
        "description": "Trigger GitLab CI rollback pipeline to revert to a previous version.",
        "parameters": {"type": "object", "properties": {
            "project_id":         {"type": "string"},
            "rollback_to_version": {"type": "string"}
        }, "required": ["project_id", "rollback_to_version"]}
    }},
    {"type": "function", "function": {
        "name": "send_approval_request",
        "description": "Post a briefing to the on-call engineer and block for their decision.",
        "parameters": {"type": "object", "properties": {
            "summary":            {"type": "string"},
            "root_cause":         {"type": "string"},
            "recommended_action": {"type": "string"},
            "confidence_score":   {"type": "number"},
            "rollback_version":   {"type": "string"}
        }, "required": ["summary", "root_cause", "recommended_action", "confidence_score", "rollback_version"]}
    }},
]

SYSTEM_PROMPT = """You are MTTR.ai, an expert SRE incident response agent.

When an alert fires:
1. Use dynatrace_get_problem to get full problem details
2. Use dynatrace_get_metrics to pull relevant metrics
3. Use dynatrace_get_logs to get log evidence
4. Use gitlab_get_recent_deployments to check for recent changes
5. Correlate all signals to identify root cause
6. Form a hypothesis with confidence score (0.0–1.0)
7. Use send_approval_request to brief the on-call engineer

IMPORTANT: Only recommend rollback if a recent deployment clearly caused the incident.
If the incident is caused by load, capacity, data growth, or external factors unrelated
to a recent deploy — recommend the appropriate operational fix instead.

Be precise. Distinguish deploy regressions from operational incidents.
"""

def dispatch(tool_name: str, tool_input: dict, scenario: dict, calls: list) -> str:
    calls.append(tool_name)

    if tool_name == "dynatrace_get_problem":
        return json.dumps(scenario["mock_problem"])

    elif tool_name == "dynatrace_get_metrics":
        return json.dumps(scenario["mock_metrics"])

    elif tool_name == "dynatrace_get_logs":
        return json.dumps(scenario["mock_logs"])

    elif tool_name == "gitlab_get_recent_deployments":
        return json.dumps(scenario["mock_deployments"])

    elif tool_name == "gitlab_trigger_rollback":
        version = tool_input.get("rollback_to_version", "unknown")
        return json.dumps({
            "status": "triggered",
            "pipeline_id": 99999,
            "rollback_to_version": version,
            "message": f"Rollback pipeline triggered — deploying {version}"
        })

    elif tool_name == "send_approval_request":
        return json.dumps({
            "decision":    "approved",
            "reason":      "auto-approved (test mode)",
            "decided_by":  "test-runner",
            "decided_at":  datetime.now(timezone.utc).isoformat(),
            "summary":            tool_input.get("summary", ""),
            "root_cause":         tool_input.get("root_cause", ""),
            "recommended_action": tool_input.get("recommended_action", ""),
            "confidence_score":   tool_input.get("confidence_score", 0),
            "rollback_version":   tool_input.get("rollback_version", ""),
        })

    return json.dumps({"error": f"unknown tool: {tool_name}"})

def run_scenario(scenario: dict) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"INCIDENT ALERT\n"
            f"Problem ID: {scenario['problem_id']}\n"
            f"Title: {scenario['problem_title']}\n"
            f"Time: {datetime.now(timezone.utc).isoformat()}\n"
            f"GitLab Project ID: {scenario['mock_deployments']['project_id']}\n\n"
            f"Investigate fully, identify root cause, and coordinate a fix."
        )}
    ]

    tool_calls_made = []
    approval_payload = {}
    triggered_rollback = False
    rollback_version = None
    start = time.time()

    while True:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=4096,
        )

        choice = response.choices[0]
        msg = choice.message

        assistant_entry = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_entry["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]
        messages.append(assistant_entry)

        if choice.finish_reason == "stop" or not msg.tool_calls:
            break

        for tc in msg.tool_calls:
            tool_input = json.loads(tc.function.arguments)
            result = dispatch(tc.function.name, tool_input, scenario, tool_calls_made)

            if tc.function.name == "send_approval_request":
                approval_payload = tool_input

            if tc.function.name == "gitlab_trigger_rollback":
                triggered_rollback = True
                rollback_version = tool_input.get("rollback_to_version")

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result
            })

    return {
        "final_summary":       msg.content or "",
        "tool_calls_made":     tool_calls_made,
        "approval_payload":    approval_payload,
        "triggered_rollback":  triggered_rollback,
        "rollback_version":    rollback_version,
        "duration_seconds":    round(time.time() - start, 1),
    }

def score(result: dict, scenario: dict) -> dict:
    expected   = scenario["expected"]
    summary    = (result["final_summary"] + " " +
                  result["approval_payload"].get("root_cause", "") + " " +
                  result["approval_payload"].get("recommended_action", "")).lower()
    calls      = result["tool_calls_made"]

    keywords_hit = [k for k in expected["root_cause_keywords"] if k.lower() in summary]
    keyword_score = len(keywords_hit) / len(expected["root_cause_keywords"])

    should_rollback  = expected["should_rollback"]
    did_rollback     = result["triggered_rollback"]
    rollback_correct = (should_rollback == did_rollback)

    investigation_tools = {
        "dynatrace_get_problem", "dynatrace_get_metrics",
        "dynatrace_get_logs", "gitlab_get_recent_deployments"
    }
    tools_used       = set(calls)
    coverage         = len(investigation_tools & tools_used) / len(investigation_tools)

    confidence = result["approval_payload"].get("confidence_score", 0)
    confidence_ok = 0.4 <= confidence <= 1.0

    overall = round(
        keyword_score * 0.40 +
        (1.0 if rollback_correct else 0.0) * 0.35 +
        coverage      * 0.15 +
        (1.0 if confidence_ok else 0.0) * 0.10,
        2
    )

    return {
        "overall":          overall,
        "keyword_score":    round(keyword_score, 2),
        "rollback_correct": rollback_correct,
        "tool_coverage":    round(coverage, 2),
        "confidence_ok":    confidence_ok,
        "confidence":       confidence,
        "keywords_hit":     keywords_hit,
        "keywords_missed":  [k for k in expected["root_cause_keywords"] if k.lower() not in summary],
        "should_rollback":  should_rollback,
        "did_rollback":     did_rollback,
    }

def bar(score_val: float, width: int = 20) -> str:
    filled = int(score_val * width)
    return "#" * filled + "." * (width - filled)

def rating(score_val: float) -> str:
    if score_val >= 0.85: return "PASS ✓"
    if score_val >= 0.60: return "PARTIAL ~"
    return "FAIL ✗"

def print_result(scenario: dict, result: dict, sc: dict) -> None:
    name  = scenario["name"]
    calls = result["tool_calls_made"]
    dur   = result["duration_seconds"]
    ap    = result["approval_payload"]

    print(f"\n  Tools called: {' -> '.join(calls)}")
    print(f"  Duration: {dur}s")

    if ap:
        print(f"\n  Agent briefing:")
        if ap.get("root_cause"):
            print(f"    Root cause:  {textwrap.fill(ap['root_cause'][:200], 80, subsequent_indent='                 ')}")
        if ap.get("recommended_action"):
            print(f"    Action:      {ap['recommended_action'][:120]}")
        if ap.get("confidence_score"):
            print(f"    Confidence:  {ap['confidence_score']:.0%}")

    rollback_str = f"v{result['rollback_version']}" if result["triggered_rollback"] else "none"
    print(f"  Rollback triggered: {result['triggered_rollback']} ({rollback_str})")

    print(f"\n  Scores:")
    print(f"    Keyword match:    {bar(sc['keyword_score'])} {sc['keyword_score']:.0%}  hit={sc['keywords_hit']}")
    if sc["keywords_missed"]:
        print(f"                                              missed={sc['keywords_missed']}")
    print(f"    Rollback decision:{bar(1.0 if sc['rollback_correct'] else 0.0)} {'correct' if sc['rollback_correct'] else 'WRONG'} (expected={sc['should_rollback']}, did={sc['did_rollback']})")
    print(f"    Tool coverage:    {bar(sc['tool_coverage'])} {sc['tool_coverage']:.0%}")
    print(f"    Confidence:       {bar(sc['confidence'] if sc['confidence_ok'] else 0)} {sc['confidence']:.0%} {'ok' if sc['confidence_ok'] else 'low'}")
    print(f"\n  OVERALL: {bar(sc['overall'])} {sc['overall']:.0%}  [{rating(sc['overall'])}]")

def print_summary(results: list) -> None:
    print("\n" + "=" * 70)
    print("  FINAL RESULTS SUMMARY")
    print("=" * 70)
    for r in results:
        sc   = r["score"]
        name = r["scenario"]["name"][:55]
        print(f"  {rating(sc['overall']):10s} {sc['overall']:.0%}  {bar(sc['overall'], 15)}  {name}")

    scores  = [r["score"]["overall"] for r in results]
    avg     = sum(scores) / len(scores)
    passed  = sum(1 for s in scores if s >= 0.85)
    partial = sum(1 for s in scores if 0.6 <= s < 0.85)
    failed  = sum(1 for s in scores if s < 0.6)

    print(f"\n  Average score: {avg:.0%}   Pass: {passed}  Partial: {partial}  Fail: {failed}")
    print("=" * 70 + "\n")

def main():
    parser = argparse.ArgumentParser(description="MTTR.ai Post-Mortem Test Runner")
    parser.add_argument("--scenario", "-s", help="Run only scenario matching this prefix (e.g. 02)")
    args = parser.parse_args()

    scenarios_dir = Path(__file__).parent / "scenarios"
    paths = sorted(scenarios_dir.glob("*.json"))

    if args.scenario:
        paths = [p for p in paths if p.name.startswith(args.scenario)]
        if not paths:
            print(f"No scenario found matching prefix '{args.scenario}'")
            sys.exit(1)

    print(f"\n{'='*70}")
    print(f"  MTTR.ai Post-Mortem Test Suite")
    print(f"  Model: {MODEL} | Scenarios: {len(paths)}")
    print(f"  Source: github.com/danluu/post-mortems")
    print(f"{'='*70}")

    all_results = []

    for path in paths:
        scenario = json.loads(path.read_text())
        print(f"\n{'-'*70}")
        print(f"  [{path.stem}]")
        print(f"  {scenario['name']}")
        print(f"  Source: {scenario['source']}")
        print(f"  Expected: {'ROLLBACK' if scenario['expected']['should_rollback'] else 'NO ROLLBACK (operational fix)'}")
        print(f"{'-'*70}")

        try:
            result = run_scenario(scenario)
            sc     = score(result, scenario)
            print_result(scenario, result, sc)
            all_results.append({"scenario": scenario, "result": result, "score": sc})

            out_dir = Path(__file__).parent / "results"
            out_dir.mkdir(exist_ok=True)
            out_file = out_dir / f"{path.stem}_result.json"
            out_file.write_text(json.dumps({
                "scenario_id": scenario["id"],
                "name":        scenario["name"],
                "score":       sc,
                "result":      {k: v for k, v in result.items() if k != "final_summary"},
                "final_summary": result["final_summary"][:500],
                "ran_at":      datetime.now(timezone.utc).isoformat(),
            }, indent=2))

        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback; traceback.print_exc()

    if len(all_results) > 1:
        print_summary(all_results)

if __name__ == "__main__":
    main()
