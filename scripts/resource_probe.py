"""Bounded loopback fixtures and child-process resource observations, not a SLA."""

import argparse
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import json
from pathlib import Path
import platform
import resource
import subprocess
import sys
from time import monotonic, sleep
import zlib


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RSS_LIMIT = 512 * 1024 * 1024
WALL_LIMIT = 90
CPU_LIMIT = 20


def write_json(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def worker(output, argv):
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT, CPU_LIMIT + 1))
    start = monotonic()
    try:
        from everyinfra_docs.cli import main
        return main(argv)
    finally:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        write_json(output, {
            "wall_seconds": monotonic() - start,
            "cpu_seconds": usage.ru_utime + usage.ru_stime,
            "peak_rss_bytes": usage.ru_maxrss * (1 if sys.platform == "darwin" else 1024),
            "measurement": "getrusage(RUSAGE_SELF); crawler process only",
        })


def cases():
    import brotli
    from backports import zstd
    from examples.fixture_site import page

    encoders = {
        "gzip": ("gzip", gzip.compress),
        "x-gzip": ("x-gzip", gzip.compress),
        "deflate": ("deflate", zlib.compress),
        "raw-deflate": ("deflate", lambda body: zlib.compress(body, wbits=-15)),
        "brotli": ("br", lambda body: brotli.compress(body, quality=4)),
        "zstd": ("zstd", zstd.compress),
        "stacked": ("gzip, deflate", lambda body: zlib.compress(gzip.compress(body))),
    }
    for name, (encoding, encode) in encoders.items():
        for size in ("small", "oversize"):
            body = page(text="Resource fixture" if size == "small" else "x" * (4 * 1024 * 1024))[2].encode()
            yield {
                "name": f"{name}-{size}",
                "routes": {"/": (200, {"Content-Type": "text/html", "Content-Encoding": encoding}, encode(body))},
                "extra": ["--max-body-bytes", "1048576"],
                "status": "complete_within_scope" if size == "small" else "failed",
                "exit": 0 if size == "small" else 1, "requests": 2,
                "documents": 1 if size == "small" else 0,
                "document_hash": sha256(b"Resource fixture").hexdigest() if size == "small" else None,
            }
    for name, headers, body in (
        ("raw-length-oversize", {"Content-Type": "text/html"}, b"x" * (4 * 1024 * 1024)),
        ("raw-stream-oversize", {"Content-Type": "text/html", "Content-Length": None}, b"x" * (4 * 1024 * 1024)),
        ("corrupt-gzip", {"Content-Type": "text/html", "Content-Encoding": "gzip"}, b"not gzip"),
        ("unknown-encoding", {"Content-Type": "text/html", "Content-Encoding": "unknown"}, page()[2]),
    ):
        yield {"name": name, "routes": {"/": (200, headers, body)},
               "extra": ["--max-body-bytes", "1048576"], "status": "failed", "exit": 1,
               "requests": 2, "documents": 0}
    routes = {"/": page(links=(f"/p/{i}" for i in range(10000)))}
    routes.update({f"/p/{i}": page() for i in range(24)})
    yield {"name": "link-frontier-10000", "routes": routes,
           "extra": ["--max-candidates", "25", "--max-pages", "30", "--max-requests", "31"],
           "status": "partial", "exit": 2, "requests": 26, "documents": 25,
           "stop_reason": "max_candidates"}
    body = "<html><title>Dense DOM</title><main>" + "<p>node</p>" * 40000 + "</main></html>"
    yield {"name": "dense-dom-40000", "routes": {"/": (200, {"Content-Type": "text/html"}, body)},
           "extra": [], "status": "complete_within_scope", "exit": 0, "requests": 2, "documents": 1}
    count = 300
    routes = {f"/p/{i}": page(links=(f"/p/{i + 1}",) if i + 1 < count else (), text="x" * 20000)
              for i in range(1, count)}
    routes["/"] = page(links=("/p/1",), text="x" * 20000)
    yield {"name": "sequential-300", "routes": routes,
           "extra": ["--max-pages", str(count), "--max-requests", str(count + 1)],
           "status": "complete_within_scope", "exit": 0, "requests": count + 1, "documents": count}
    count = 1000
    routes = {f"/p/{i}": page(links=(f"/p/{i + 1}",) if i + 1 < count else (), text="x" * 20000)
              for i in range(1, count)}
    routes["/"] = page(links=("/p/1",), text="x" * 20000)
    yield {"name": "sequential-1000-paced", "routes": routes,
           "extra": ["--max-pages", str(count), "--max-requests", str(count + 1),
                     "--max-candidates", str(count), "--delay", "0.05"],
           "status": "complete_within_scope", "exit": 0, "requests": count + 1, "documents": count}


def run_case(case, directory):
    from examples.fixture_site import fixture_site

    directory.mkdir()
    resources = directory / "resources.json"
    start = monotonic()
    guard = None
    sampled_peak = 0
    sample_errors = 0
    samples = []
    with fixture_site(case["routes"]) as (site, requests):
        command = [sys.executable, str(Path(__file__).resolve()), "--worker", str(resources),
                   site + "/", "--allow-origin", site, "--allow-loopback", "--acknowledge-authorized",
                   "--delay", "0", "--timeout", "3", "--output", str(directory / "crawl"), *case["extra"]]
        with (directory / "stdout.txt").open("x") as stdout, (directory / "stderr.txt").open("x") as stderr:
            process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
            try:
                while process.poll() is None:
                    try:
                        sample = subprocess.run(["/bin/ps", "-o", "rss=", "-p", str(process.pid)],
                                                capture_output=True, text=True, timeout=2)
                        if sample.returncode == 0 and sample.stdout.strip():
                            rss_bytes = int(sample.stdout.strip()) * 1024
                            sampled_peak = max(sampled_peak, rss_bytes)
                            samples.append({"elapsed_seconds": monotonic() - start, "rss_bytes": rss_bytes})
                    except (OSError, ValueError, subprocess.TimeoutExpired):
                        sample_errors += 1
                    if sampled_peak > RSS_LIMIT:
                        guard = "sampled_rss_limit"
                        break
                    if monotonic() - start > WALL_LIMIT:
                        guard = "wall_limit"
                        break
                    sleep(0.2)
            finally:
                if process.poll() is None:
                    process.kill()
                exit_code = process.wait()
        write_json(directory / "requests.json", requests)
    write_json(directory / "rss-samples.json", samples)
    report_file = directory / "crawl" / "report.json"
    report = json.loads(report_file.read_text()) if report_file.exists() else {}
    metrics = json.loads(resources.read_text()) if resources.exists() else {}
    expected = {key: value for key, value in case.items() if key not in {"routes", "extra"}}
    errors = []
    for label, actual, wanted in (
        ("exit", exit_code, case["exit"]), ("status", report.get("status"), case["status"]),
        ("requests", len(requests), case["requests"]),
        ("attempts", report.get("http_attempts"), len(requests)),
        ("documents", report.get("record_counts", {}).get("document", 0), case["documents"]),
    ):
        if actual != wanted:
            errors.append(f"{label}: {actual!r} != {wanted!r}")
    if case.get("stop_reason") and report.get("stop_reason") != case["stop_reason"]:
        errors.append("stop_reason mismatch")
    documents = [row for row in report.get("records", []) if row["kind"] == "document"]
    if case.get("document_hash") and any(row["content_sha256"] != case["document_hash"] for row in documents):
        errors.append("decoded content hash mismatch")
    if case["documents"] == 0 and report.get("record_counts") != {"download_error": 1}:
        errors.append("expected exactly one download_error")
    if any(row["cookie"] or row["authorization"] or row["method"] != "GET" for row in requests):
        errors.append("request credential/method boundary")
    if guard or not metrics or metrics.get("peak_rss_bytes", RSS_LIMIT + 1) > RSS_LIMIT:
        errors.append("resource guard or missing metrics")
    if metrics.get("cpu_seconds", CPU_LIMIT + 1) > CPU_LIMIT or sample_errors:
        errors.append("CPU limit or measurement failure")
    result = {"name": case["name"], "expected": expected, "passed": not errors, "errors": errors,
              "exit_code": exit_code, "status": report.get("status"), "requests": len(requests),
              "resources": metrics, "guard": guard, "sampled_peak_rss_bytes": sampled_peak,
              "sample_errors": sample_errors}
    write_json(directory / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New evidence directory")
    parser.add_argument("--case", help="Run one named fixture instead of the full suite")
    args = parser.parse_args()
    if sys.platform not in {"darwin", "linux"}:
        parser.error("resource probe currently supports macOS/Linux only")
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    for case in cases():
        if args.case and case["name"] != args.case:
            continue
        result = run_case(case, args.output / case["name"])
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    if not results:
        parser.error("unknown case; no fixtures were run")
    summary = {"created_at": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
               "python": sys.version, "passed": all(row["passed"] for row in results), "cases": results,
               "limits": {"child_cpu_seconds": CPU_LIMIT, "sampled_child_rss_bytes": RSS_LIMIT,
                          "case_wall_seconds": WALL_LIMIT},
               "scope": "Loopback synthetic samples only; RSS monitor is not a kernel memory sandbox; no long-term or production claim.",
               "source_sha256": {str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
                                  for path in (ROOT / "src/everyinfra_docs/crawler.py", Path(__file__).resolve(), ROOT / "uv.lock")}}
    write_json(args.output / "summary.json", summary)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    if sys.argv[1:2] == ["--worker"]:
        raise SystemExit(worker(Path(sys.argv[2]), sys.argv[3:]))
    raise SystemExit(main())
