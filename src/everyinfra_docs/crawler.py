"""Sequential document collection; robots and each HTTP attempt share one budget."""

from collections import Counter, deque
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from urllib.robotparser import RobotFileParser

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.exceptions import IgnoreRequest
from scrapy.http import HtmlResponse, TextResponse

from .policy import CrawlPolicy


USER_AGENT = "EveryInfraDocs/0.1 (+https://everyinfra.com)"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def clean_text(value):
    return " ".join(value.split())


class ScopeAndBudgetMiddleware:
    def __init__(self, crawler):
        self.crawler = crawler

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_request(self, request):
        spider = self.crawler.spider
        _, reason = spider.policy.admit(request.url)
        if reason or request.method != "GET" or request.headers.get("Cookie") or request.headers.get("Authorization"):
            spider.abort_reason = "download_scope_violation"
            raise IgnoreRequest("download_scope_violation")
        if spider.http_attempts >= spider.policy.max_requests:
            spider.abort_reason = "max_requests"
            raise IgnoreRequest("max_requests")
        is_document = request.meta.get("kind") == "document"
        if is_document and spider.document_attempts >= spider.policy.max_pages:
            spider.abort_reason = "max_pages"
            raise IgnoreRequest("max_pages")
        spider.http_attempts += 1
        if is_document:
            spider.document_attempts += 1

    def process_response(self, request, response):
        # Responses run in reverse order: Scrapy's decompressor (590) ran first.
        if any(value.strip() for value in response.headers.getlist("Content-Encoding")):
            raise IgnoreRequest("unsupported_content_encoding")
        return response


class DocumentSpider(scrapy.Spider):
    name = "everyinfra_docs"

    def __init__(self, policy, **kwargs):
        super().__init__(**kwargs)
        self.policy = policy
        self.pending = deque()
        self.seen = set()
        self.records = []
        self.excluded = Counter()
        self.http_attempts = 0
        self.document_attempts = 0
        self.abort_reason = None
        self.stop_reason = "running"
        self.robots = None
        self.robots_status = "not_checked"
        self.robots_delay = None
        self.started_at = utc_now()
        self.candidate_limit_reached = False

    async def start(self):
        yield scrapy.Request(self.policy.allowed_origin + "/robots.txt", callback=self.parse_robots,
                             errback=self.failed, meta={"kind": "robots", "handle_httpstatus_all": True})

    def parse_robots(self, response):
        if response.status == 404:
            self.robots_status = "missing_404"
            rules = []
        elif 200 <= response.status < 300 and isinstance(response, TextResponse) and not isinstance(response, HtmlResponse):
            self.robots_status = "loaded"
            rules = response.text.splitlines()
        else:
            self.robots_status = "unavailable"
            self.stop_reason = "robots_unavailable"
            self.records.append({"kind": "robots_error", "url": response.url, "http_status": response.status})
            return
        self.robots = RobotFileParser()
        self.robots.parse(rules)
        self.robots_delay = self.robots.crawl_delay(USER_AGENT)
        if self.robots_delay is not None:
            if self.robots_delay > 60:
                self.stop_reason = "robots_delay_exceeds_limit"
                return
            for slot in self.crawler.engine.downloader.slots.values():
                slot.delay = max(self.policy.delay, self.robots_delay)
        self.enqueue(self.policy.start_url, None, 0)
        yield from self.next_request()

    def enqueue(self, value, discovered_from, depth):
        url, reason = self.policy.admit(value)
        if reason:
            self.excluded[reason] += 1
            return
        if url in self.seen:
            self.excluded["duplicate_url"] += 1
            return
        if len(self.seen) >= self.policy.max_candidates:
            self.candidate_limit_reached = True
            self.excluded["max_candidates"] += 1
            return
        self.seen.add(url)
        self.pending.append((url, discovered_from, depth))

    def enqueue_link(self, response, value, depth):
        try:
            self.enqueue(response.urljoin(value), response.url, depth)
        except (ValueError, UnicodeError):
            self.excluded["invalid_or_sensitive_url"] += 1

    def next_request(self):
        if self.abort_reason:
            self.stop_reason = self.abort_reason
            return
        while self.pending:
            if self.http_attempts >= self.policy.max_requests:
                self.stop_reason = "max_requests"
                return
            if self.document_attempts >= self.policy.max_pages:
                self.stop_reason = "max_pages"
                return
            url, parent, depth = self.pending.popleft()
            if not self.robots.can_fetch(USER_AGENT, url):
                self.records.append({"kind": "blocked_robots", "url": url, "discovered_from": parent})
                continue
            yield scrapy.Request(url, callback=self.parse_document, errback=self.failed, dont_filter=True,
                                 meta={"kind": "document", "parent": parent, "depth": depth,
                                       "handle_httpstatus_all": True})
            return
        self.stop_reason = "max_candidates" if self.candidate_limit_reached else "frontier_exhausted"

    def parse_document(self, response):
        record = {"url": response.url, "discovered_from": response.meta.get("parent"),
                  "depth": response.meta["depth"], "http_status": response.status, "fetched_at": utc_now()}
        if 300 <= response.status < 400:
            record["kind"] = "redirect"
            location = response.headers.get("Location")
            if location:
                try:
                    target = response.urljoin(location.decode("latin-1"))
                    allowed, reason = self.policy.admit(target)
                except (ValueError, UnicodeError):
                    allowed, reason = None, "invalid_or_sensitive_url"
                record["redirect_status"] = reason or "in_scope"
                if allowed:
                    record["redirect_to"] = allowed
                    self.enqueue(allowed, response.url, response.meta["depth"])
            else:
                record["redirect_status"] = "missing_location"
        elif not 200 <= response.status < 300:
            record["kind"] = "http_error"
        elif not isinstance(response, HtmlResponse):
            record["kind"] = "unsupported_content"
        else:
            record["kind"] = "document"
            record["title"] = clean_text(response.xpath("string(//title)").get() or "")
            root = response.css("main, article")
            root = root[0] if root else response
            text = clean_text(" ".join(root.xpath(
                ".//text()[not(ancestor::script or ancestor::style or ancestor::noscript or ancestor::template or ancestor::head)]"
            ).getall()))
            record.update(text=text[:self.policy.max_text_chars], text_truncated=len(text) > self.policy.max_text_chars,
                          content_sha256=sha256(text.encode("utf-8")).hexdigest(),
                          title_missing=not bool(record["title"]))
            for href in response.css("a::attr(href)").getall():
                self.enqueue_link(response, href, response.meta["depth"] + 1)
        self.records.append(record)
        yield from self.next_request()

    def failed(self, failure):
        request = failure.request
        self.records.append({"kind": "download_error", "url": request.url,
                             "error_type": failure.type.__name__, "phase": request.meta["kind"]})
        if request.meta["kind"] == "robots":
            self.robots_status = "unavailable"
            self.stop_reason = self.abort_reason or "robots_unavailable"
            return
        yield from self.next_request()

    def report(self):
        kinds = Counter(row["kind"] for row in self.records)
        incomplete = (self.stop_reason != "frontier_exhausted" or
                      any(kinds[kind] for kind in ("http_error", "download_error", "robots_error", "blocked_robots", "unsupported_content")) or
                      any(row.get("redirect_status") not in {None, "in_scope"} for row in self.records))
        status = "failed" if not kinds["document"] else ("partial" if incomplete else "complete_within_scope")
        return {"schema_version": 1, "tool": "everyinfra-docs-crawler", "scrapy_version": scrapy.__version__,
                "status": status, "stop_reason": self.stop_reason, "started_at": self.started_at,
                "finished_at": utc_now(), "policy": asdict(self.policy), "robots_status": self.robots_status,
                "robots_crawl_delay": self.robots_delay,
                "http_attempts": self.http_attempts, "document_attempts": self.document_attempts,
                "remaining_candidates": len(self.pending), "record_counts": dict(kinds),
                "excluded_link_counts": dict(self.excluded), "records": self.records}


def collect(policy: CrawlPolicy):
    process = CrawlerProcess(settings={
        "USER_AGENT": USER_AGENT, "CONCURRENT_REQUESTS": 1, "DOWNLOAD_DELAY": policy.delay,
        "RANDOMIZE_DOWNLOAD_DELAY": False, "DOWNLOAD_TIMEOUT": policy.timeout,
        "DOWNLOAD_MAXSIZE": policy.max_body_bytes, "DOWNLOAD_WARNSIZE": policy.max_body_bytes,
        "RETRY_ENABLED": False, "REDIRECT_ENABLED": False, "METAREFRESH_ENABLED": False,
        "COOKIES_ENABLED": False, "HTTPPROXY_ENABLED": False, "HTTPCACHE_ENABLED": False,
        "ROBOTSTXT_OBEY": False,  # Explicit, fail-closed robots preflight above.
        "TELNETCONSOLE_ENABLED": False, "LOG_ENABLED": False, "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
        "DOWNLOADER_MIDDLEWARES": {ScopeAndBudgetMiddleware: 1},
    })
    crawler = process.create_crawler(DocumentSpider)
    failures = []
    from scrapy import signals

    def on_spider_error(failure, response, spider):
        failures.append(failure.type.__name__)

    crawler.signals.connect(on_spider_error, signal=signals.spider_error, weak=False)
    process.crawl(crawler, policy=policy).addErrback(lambda failure: failures.append(failure.type.__name__))
    process.start()
    if crawler.spider is None:
        raise RuntimeError("crawler_start_failed")
    report = crawler.spider.report()
    if failures:
        report.update(status="failed", stop_reason="crawler_error", internal_errors=failures)
    return report
