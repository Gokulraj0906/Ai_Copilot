"""
Parses app.log (the file handler configured in main.py) to surface
operational anomalies: error rates, LLM failures, rate-limit hits,
slow requests, and repair-loop exhaustion.

Usage:
    python -m app.log_analysis
    python -m app.log_analysis --since "2026-06-15 00:00:00"
    python -m app.log_analysis --file /path/to/app.log --json
"""

import re
import json
import argparse
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - "
    r"(?P<logger>[\w.]+) - (?P<level>\w+) - (?P<message>.*)$"
)

TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S,%f"


def parse_log_file(path: Path) -> list[dict]:
    """Reads app.log and returns structured records. Lines that don't
    match the expected format (e.g. multi-line tracebacks) are
    appended to the 'message' of the preceding record so nothing is
    silently dropped."""
    records: list[dict] = []

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            match = LOG_LINE_RE.match(line)
            if match:
                record = match.groupdict()
                try:
                    record["timestamp_dt"] = datetime.strptime(record["timestamp"], TIMESTAMP_FMT)
                except ValueError:
                    record["timestamp_dt"] = None
                records.append(record)
            elif records:
                # continuation line (e.g. traceback) — attach to last record
                records[-1]["message"] += "\n" + line

    return records


def filter_since(records: list[dict], since: datetime | None) -> list[dict]:
    if since is None:
        return records
    return [r for r in records if r["timestamp_dt"] and r["timestamp_dt"] >= since]


def analyze(records: list[dict]) -> dict:
    total = len(records)
    by_level = Counter(r["level"] for r in records)

    errors = [r for r in records if r["level"] in ("ERROR", "CRITICAL")]
    warnings = [r for r in records if r["level"] == "WARNING"]

    unhandled_errors = [r for r in errors if "Unhandled error on" in r["message"]]

    # LLM model fallback / failure patterns from llm/client.py
    llm_timeouts = [r for r in records if "timed out, trying next model" in r["message"]]
    llm_model_failures = [r for r in records if "trying next model" in r["message"]]
    llm_all_failed = [r for r in records if "All models failed" in r["message"]]

    model_failure_counts = Counter()
    for r in llm_model_failures:
        m = re.search(r"^(\S+) (?:timed out|returned \d+|failed)", r["message"])
        if m:
            model_failure_counts[m.group(1)] += 1

    # Repair loop / validation outcomes (from copilot.py logger if present)
    repair_failures = [r for r in records if "repair" in r["message"].lower() and r["level"] in ("WARNING", "ERROR")]

    # Execution engine anomalies (execution.py)
    node_failures = [r for r in records if "failed:" in r["message"] and "copilot.execution" in r["logger"]]
    node_failure_by_type = Counter()
    for r in node_failures:
        m = re.search(r"Node \S+ \((\w+)\) failed", r["message"])
        if m:
            node_failure_by_type[m.group(1)] += 1

    # Per-endpoint unhandled error breakdown
    endpoint_error_counts = Counter()
    for r in unhandled_errors:
        m = re.search(r"Unhandled error on (\S+):", r["message"])
        if m:
            endpoint_error_counts[m.group(1)] += 1

    # Time-bucketed error rate (per minute) to spot spikes
    errors_per_minute: dict[str, int] = defaultdict(int)
    for r in errors:
        if r["timestamp_dt"]:
            bucket = r["timestamp_dt"].strftime("%Y-%m-%d %H:%M")
            errors_per_minute[bucket] += 1

    time_range = None
    if records:
        timestamps = [r["timestamp_dt"] for r in records if r["timestamp_dt"]]
        if timestamps:
            time_range = {"start": min(timestamps).isoformat(), "end": max(timestamps).isoformat()}

    return {
        "summary": {
            "total_lines": total,
            "by_level": dict(by_level),
            "time_range": time_range,
        },
        "anomalies": {
            "unhandled_errors": {
                "count": len(unhandled_errors),
                "by_endpoint": dict(endpoint_error_counts),
                "samples": [r["message"].splitlines()[0] for r in unhandled_errors[:5]],
            },
            "llm_failures": {
                "model_timeouts": len(llm_timeouts),
                "model_fallback_events": len(llm_model_failures),
                "by_model": dict(model_failure_counts),
                "all_models_exhausted": len(llm_all_failed),
            },
            "repair_loop_issues": {
                "count": len(repair_failures),
                "samples": [r["message"].splitlines()[0] for r in repair_failures[:5]],
            },
            "node_execution_failures": {
                "count": len(node_failures),
                "by_node_type": dict(node_failure_by_type),
            },
            "warnings": {
                "count": len(warnings),
                "samples": [r["message"].splitlines()[0] for r in warnings[:5]],
            },
        },
        "error_rate_per_minute": dict(sorted(errors_per_minute.items())),
    }


def print_report(report: dict):
    s = report["summary"]
    a = report["anomalies"]

    print("=" * 60)
    print("LOG ANALYSIS REPORT")
    print("=" * 60)
    print(f"Total lines: {s['total_lines']}")
    if s["time_range"]:
        print(f"Time range: {s['time_range']['start']} -> {s['time_range']['end']}")
    print(f"By level: {s['by_level']}")
    print()

    print("-- Unhandled Errors --")
    print(f"Count: {a['unhandled_errors']['count']}")
    if a["unhandled_errors"]["by_endpoint"]:
        print(f"By endpoint: {a['unhandled_errors']['by_endpoint']}")
    for sample in a["unhandled_errors"]["samples"]:
        print(f"  e.g. {sample}")
    print()

    print("-- LLM Reliability --")
    llm = a["llm_failures"]
    print(f"Timeouts: {llm['model_timeouts']}")
    print(f"Fallback events: {llm['model_fallback_events']} (by model: {llm['by_model']})")
    print(f"Fully exhausted (all models failed): {llm['all_models_exhausted']}")
    print()

    print("-- Repair Loop --")
    print(f"Issues logged: {a['repair_loop_issues']['count']}")
    for sample in a["repair_loop_issues"]["samples"]:
        print(f"  e.g. {sample}")
    print()

    print("-- Node Execution Failures --")
    print(f"Count: {a['node_execution_failures']['count']}")
    if a["node_execution_failures"]["by_node_type"]:
        print(f"By node type: {a['node_execution_failures']['by_node_type']}")
    print()

    print("-- Other Warnings --")
    print(f"Count: {a['warnings']['count']}")
    for sample in a["warnings"]["samples"]:
        print(f"  e.g. {sample}")
    print()

    if report["error_rate_per_minute"]:
        print("-- Error Rate Per Minute (spikes) --")
        for minute, count in report["error_rate_per_minute"].items():
            if count >= 1:
                print(f"  {minute}: {count}")


def main():
    parser = argparse.ArgumentParser(description="Analyze app.log for anomalies")
    parser.add_argument("--file", default="app.log", help="Path to log file (default: app.log)")
    parser.add_argument("--since", default=None, help="Only include entries after this timestamp, format: YYYY-MM-DD HH:MM:SS")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of formatted report")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"Log file not found: {path}")
        return

    records = parse_log_file(path)

    since_dt = None
    if args.since:
        since_dt = datetime.strptime(args.since, "%Y-%m-%d %H:%M:%S")
        records = filter_since(records, since_dt)

    report = analyze(records)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report)


if __name__ == "__main__":
    main()