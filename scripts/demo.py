"""Run the CLI against a synthetic loopback site and preserve its real output."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.fixture_site import demo_routes, fixture_site


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    with fixture_site(demo_routes()) as (site, requests):
        command = [sys.executable, "-m", "everyinfra_docs.cli", site + "/", "--allow-origin", site,
                   "--allow-loopback", "--acknowledge-authorized", "--delay", "0", "--output", str(args.output / "crawl")]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    evidence = {"fixture": "Synthetic local documents; not customer or third-party platform data",
                "cli_exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr,
                "server_requests": requests, "public_network_crawl": False}
    (args.output / "demo-evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(result.stdout)
    # The fixture deliberately contains failures, so partial (2) is the expected demonstration.
    return 0 if result.returncode == 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
