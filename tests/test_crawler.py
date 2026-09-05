import csv
import gzip
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from everyinfra_docs.cli import csv_text
from everyinfra_docs.policy import CrawlPolicy, normalize_url
from examples.fixture_site import demo_routes, fixture_site, page
from scripts.dependency_inventory import canonical_name


class PolicyTests(unittest.TestCase):
    def test_distribution_name_normalization_matches_lock_conventions(self):
        for value in ("zope.interface", "zope_interface", "Zope-Interface", "zope._-interface"):
            self.assertEqual(canonical_name(value), "zope-interface")

    def test_normalization_preserves_query_order_and_drops_fragment(self):
        self.assertEqual(normalize_url("HTTPS://Example.COM:443/a?b=2&a=1#x"), "https://example.com/a?b=2&a=1")

    def test_invalid_or_credential_urls_rejected(self):
        for url in ("file:///tmp/a", "https://u:p@example.com", "https://example.com/?token=hidden",
                    "https://example.com:wrong/", "https://example.com/\nnext", "http://a\\b"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                normalize_url(url)

    def test_exact_origin_no_subdomains_ports_or_scheme_escape(self):
        policy = CrawlPolicy("https://example.com/", "https://example.com")
        for url in ("https://sub.example.com", "https://example.com.evil.invalid", "http://example.com", "https://example.com:8443"):
            with self.subTest(url=url):
                self.assertEqual(policy.admit(url)[1], "outside_origin")

    def test_limits_and_private_ip_validation(self):
        for kwargs in ({"max_pages": 0}, {"max_requests": 2001}, {"delay": float("nan")}, {"timeout": float("inf")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                CrawlPolicy("https://example.com/", "https://example.com", **kwargs)
        for host in ("127.0.0.1", "169.254.169.254", "10.0.0.1"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                CrawlPolicy(f"http://{host}", f"http://{host}")

    def test_csv_formula_safety_preserves_json_source(self):
        for value in ("=SUM(1,1)", " +42", "\t@cmd", "-1", "\ufeff=1"):
            self.assertTrue(csv_text(value).startswith("'"))
        self.assertEqual(csv_text("ordinary title"), "ordinary title")


class CrawlIntegrationTests(unittest.TestCase):
    def run_crawl(self, site, output, *extra):
        return subprocess.run([sys.executable, "-m", "everyinfra_docs.cli", site + "/",
                               "--allow-origin", site, "--allow-loopback", "--acknowledge-authorized",
                               "--delay", "0", "--output", str(output), *extra],
                              capture_output=True, text=True, timeout=30)

    def read_report(self, output, result):
        self.assertTrue((output / "report.json").exists(), result.stdout + result.stderr)
        return json.loads((output / "report.json").read_text())

    def test_real_http_sources_dedup_errors_and_csv(self):
        with fixture_site(demo_routes()) as (site, requests), TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            result = self.run_crawl(site, output)
            report = self.read_report(output, result)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(report["status"], "partial")
            self.assertEqual(report["record_counts"], {"document": 4, "blocked_robots": 1, "http_error": 1, "unsupported_content": 1})
            paths = [entry["path"] for entry in requests]
            self.assertEqual(paths[0], "/robots.txt")
            self.assertNotIn("/private", paths)
            self.assertEqual(paths.count("/guide"), 1)
            self.assertEqual(paths.count("/broken"), 1)
            self.assertEqual(report["http_attempts"], len(requests))
            self.assertTrue(all(row["method"] == "GET" and row["cookie"] is None and row["authorization"] is None for row in requests))
            documents = [row for row in report["records"] if row["kind"] == "document"]
            self.assertTrue(any(row["title_missing"] and not row["title"] for row in documents))
            self.assertTrue(any(row["discovered_from"] == site + "/guide" for row in documents))
            with (output / "documents.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 4)
            self.assertTrue(any(row["title"].startswith("'=Synthetic") for row in rows))
            self.assertTrue(any(row["title"].startswith("=Synthetic") for row in documents))

    def test_page_budget_stops_actual_requests(self):
        with fixture_site(demo_routes()) as (site, requests), TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            report = self.read_report(output, self.run_crawl(site, output, "--max-pages", "1"))
            self.assertEqual([r["path"] for r in requests], ["/robots.txt", "/"])
            self.assertEqual(report["stop_reason"], "max_pages")

    def test_request_budget_includes_robots(self):
        with fixture_site(demo_routes()) as (site, requests), TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            report = self.read_report(output, self.run_crawl(site, output, "--max-requests", "1"))
            self.assertEqual([r["path"] for r in requests], ["/robots.txt"])
            self.assertEqual(report["stop_reason"], "max_requests")
            self.assertEqual(report["status"], "failed")

    def test_robots_errors_and_redirects_fail_closed(self):
        for status in (401, 403, 302, 503):
            routes = {"/robots.txt": (status, {"Content-Type": "text/plain", "Location": "/robots2"}, "error"), "/": page()}
            with self.subTest(status=status), fixture_site(routes) as (site, requests), TemporaryDirectory() as temporary:
                output = Path(temporary) / "run"
                report = self.read_report(output, self.run_crawl(site, output))
                self.assertEqual([r["path"] for r in requests], ["/robots.txt"])
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["stop_reason"], "robots_unavailable")

    def test_missing_robots_allows_bounded_success(self):
        with fixture_site({"/": page()}) as (site, requests), TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            result = self.run_crawl(site, output)
            report = self.read_report(output, result)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(report["status"], "complete_within_scope")
            self.assertEqual(report["robots_status"], "missing_404")

    def test_html_login_page_is_not_accepted_as_robots_rules(self):
        with fixture_site({"/robots.txt": page("Login required"), "/": page()}) as (site, requests), TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            report = self.read_report(output, self.run_crawl(site, output))
            self.assertEqual(report["stop_reason"], "robots_unavailable")
            self.assertEqual([row["path"] for row in requests], ["/robots.txt"])

    def test_robots_crawl_delay_changes_real_request_timing(self):
        routes = {"/": page(), "/robots.txt": (200, {"Content-Type": "text/plain"}, "User-agent: *\nCrawl-delay: 1\n")}
        with fixture_site(routes) as (site, requests), TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            report = self.read_report(output, self.run_crawl(site, output))
            self.assertEqual(report["robots_crawl_delay"], 1)
            self.assertGreaterEqual(requests[1]["time"] - requests[0]["time"], 0.9)

    def test_cross_origin_links_and_redirects_never_requested(self):
        with fixture_site({"/leak": page()}) as (other, escaped):
            routes = {"/": page(links=(other + "/leak", "/redirect", "/internal")),
                      "/redirect": (302, {"Location": other + "/leak"}, ""),
                      "/internal": (302, {"Location": "/target"}, ""), "/target": page("Target")}
            with fixture_site(routes) as (site, requests), TemporaryDirectory() as temporary:
                output = Path(temporary) / "run"
                report = self.read_report(output, self.run_crawl(site, output))
                self.assertEqual(escaped, [])
                self.assertIn("/target", [row["path"] for row in requests])
                self.assertEqual(report["excluded_link_counts"]["outside_origin"], 1)
                self.assertTrue(any(row.get("redirect_status") == "outside_origin" for row in report["records"]))

    def test_body_size_error_is_not_success(self):
        with fixture_site({"/": page(text="x" * 5000)}) as (site, requests), TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            report = self.read_report(output, self.run_crawl(site, output, "--max-body-bytes", "500"))
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["record_counts"].get("download_error"), 1)

    def test_streamed_and_decompressed_bodies_obey_size_limit(self):
        body = page(text="x" * 5000)[2].encode()
        variants = (
            ({"Content-Type": "text/html", "Content-Length": None}, body),
            ({"Content-Type": "text/html", "Content-Encoding": "gzip"}, gzip.compress(body)),
        )
        for headers, payload in variants:
            with self.subTest(headers=headers), fixture_site({"/": (200, headers, payload)}) as (site, requests), TemporaryDirectory() as temporary:
                output = Path(temporary) / "run"
                report = self.read_report(output, self.run_crawl(site, output, "--max-body-bytes", "500"))
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["record_counts"].get("download_error"), 1)
                self.assertNotIn("document", report["record_counts"])

    def test_text_limit_and_candidate_limit_report_partial(self):
        routes = {"/": page(links=("/a", "/b", "/c"), text="x" * 200), "/a": page()}
        with fixture_site(routes) as (site, requests), TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            report = self.read_report(output, self.run_crawl(site, output, "--max-candidates", "2", "--max-text-chars", "10"))
            self.assertEqual(report["stop_reason"], "max_candidates")
            self.assertEqual(report["status"], "partial")
            self.assertEqual(report["records"][0]["text"], "x" * 10)
            self.assertTrue(report["records"][0]["text_truncated"])
            self.assertNotIn("/b", [row["path"] for row in requests])

    def test_undecoded_content_encoding_never_becomes_document_or_robots(self):
        for phase in ("document", "robots"):
            for encoding in ("unknown", "unknown, gzip"):
                with self.subTest(phase=phase, encoding=encoding):
                    body = (page()[2] if phase == "document" else "User-agent: *\nDisallow: /\n").encode()
                    payload = gzip.compress(body) if encoding.endswith("gzip") else body
                    path = "/" if phase == "document" else "/robots.txt"
                    content_type = "text/html" if phase == "document" else "text/plain"
                    routes = {"/": page(), path: (200, {"Content-Type": content_type, "Content-Encoding": encoding}, payload)}
                    with fixture_site(routes) as (site, requests), TemporaryDirectory() as temporary:
                        output = Path(temporary) / "run"
                        result = self.run_crawl(site, output)
                        report = self.read_report(output, result)
                        self.assertEqual(result.returncode, 1)
                        self.assertEqual(report["record_counts"], {"download_error": 1})
                        self.assertEqual(report["records"][0]["phase"], phase)
                        self.assertEqual(len(requests), 2 if phase == "document" else 1)

    def test_invalid_links_and_sensitive_urls_are_excluded(self):
        routes = {"/": page(links=("http://[", "/?token=hidden", "javascript:alert(1)", "/good")), "/good": page()}
        with fixture_site(routes) as (site, requests), TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            result = self.run_crawl(site, output)
            report = self.read_report(output, result)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(report["excluded_link_counts"]["invalid_or_sensitive_url"], 3)
            self.assertNotIn("hidden", (output / "report.json").read_text())

    def test_existing_output_and_missing_ack_do_not_send_requests(self):
        with fixture_site(demo_routes()) as (site, requests), TemporaryDirectory() as temporary:
            result = self.run_crawl(site, Path(temporary))
            self.assertNotEqual(result.returncode, 0)
            missing_ack = subprocess.run([sys.executable, "-m", "everyinfra_docs.cli", site,
                                         "--allow-origin", site, "--output", str(Path(temporary) / "unused")], capture_output=True)
            self.assertNotEqual(missing_ack.returncode, 0)
            self.assertEqual(requests, [])


if __name__ == "__main__":
    unittest.main()
