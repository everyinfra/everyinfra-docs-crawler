"""CLI entry point; creates new evidence outputs without overwriting old runs."""

import argparse
import csv
import json
from pathlib import Path

from .crawler import collect
from .policy import CrawlPolicy


def csv_text(value):
    value = str(value if value is not None else "")
    if value.lstrip(" \t\r\n\ufeff").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def write_results(destination, report):
    with (destination / "report.json").open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    fields = ["url", "title", "text", "content_sha256", "fetched_at", "http_status", "discovered_from", "depth", "text_truncated", "title_missing"]
    with (destination / "documents.csv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in report["records"]:
            if row["kind"] == "document":
                writer.writerow({key: csv_text(row.get(key)) for key in fields})


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bounded document collection built with Scrapy; authorized URLs only.")
    parser.add_argument("start_url")
    parser.add_argument("--allow-origin", required=True, help="Exact scheme://hostname[:port], not a wildcard")
    parser.add_argument("--output", type=Path, required=True, help="New directory; existing paths are never overwritten")
    parser.add_argument("--acknowledge-authorized", action="store_true")
    parser.add_argument("--allow-loopback", action="store_true", help="Allow an explicitly selected loopback fixture server")
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--max-requests", type=int, default=25)
    parser.add_argument("--max-candidates", type=int, default=500)
    parser.add_argument("--max-body-bytes", type=int, default=2_000_000)
    parser.add_argument("--max-text-chars", type=int, default=5000)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args(argv)
    if not args.acknowledge_authorized:
        parser.error("--acknowledge-authorized is required; this flag does not grant permission")
    try:
        policy = CrawlPolicy(args.start_url, args.allow_origin, args.max_pages, args.max_requests,
                             args.max_candidates, args.max_body_bytes, args.max_text_chars,
                             args.delay, args.timeout, args.allow_loopback)
        args.output.mkdir(parents=True, exist_ok=False)
    except (ValueError, UnicodeError, OSError) as exc:
        parser.error(str(exc))
    try:
        report = collect(policy)
        write_results(args.output, report)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        return 1
    print(json.dumps({key: value for key, value in report.items() if key not in {"records", "policy"}}, ensure_ascii=False))
    return {"complete_within_scope": 0, "partial": 2, "failed": 1}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
