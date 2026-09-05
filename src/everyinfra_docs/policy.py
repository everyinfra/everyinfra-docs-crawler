"""Explicit URL and resource limits shared by admission and download guards."""

from dataclasses import dataclass
import ipaddress
import math
from urllib.parse import parse_qsl, urlsplit, urlunsplit


SENSITIVE_KEYS = {"token", "access_token", "api_key", "apikey", "password", "secret", "authorization", "signature"}


def normalize_url(value: str) -> str:
    if len(value) > 4096 or any(ord(c) < 32 or c == "\\" for c in value):
        raise ValueError("invalid_url")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("http_or_https_required")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("credentials_in_url")
    if any(key.casefold() in SENSITIVE_KEYS for key, _ in parse_qsl(parsed.query)):
        raise ValueError("sensitive_query")
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    if ":" in host:
        host = f"[{host}]"
    port = parsed.port
    default_port = 443 if parsed.scheme == "https" else 80
    authority = host if port is None or port == default_port else f"{host}:{port}"
    return urlunsplit((parsed.scheme, authority, parsed.path or "/", parsed.query, ""))


def origin(value: str) -> str:
    parsed = urlsplit(normalize_url(value))
    return f"{parsed.scheme}://{parsed.netloc}"


@dataclass(frozen=True)
class CrawlPolicy:
    start_url: str
    allowed_origin: str
    max_pages: int = 20
    max_requests: int = 25
    max_candidates: int = 500
    max_body_bytes: int = 2_000_000
    max_text_chars: int = 5000
    delay: float = 0.5
    timeout: float = 10.0
    allow_loopback: bool = False

    def __post_init__(self):
        start = normalize_url(self.start_url)
        allowed = normalize_url(self.allowed_origin)
        parts = urlsplit(allowed)
        if parts.path != "/" or parts.query or urlsplit(self.allowed_origin).fragment:
            raise ValueError("allow_origin_must_not_include_path_query_or_fragment")
        object.__setattr__(self, "start_url", start)
        object.__setattr__(self, "allowed_origin", origin(allowed))
        if origin(start) != self.allowed_origin:
            raise ValueError("start_outside_allowed_origin")
        for name, upper in (("max_pages", 1000), ("max_requests", 2000), ("max_candidates", 10000),
                            ("max_body_bytes", 10_000_000), ("max_text_chars", 100_000)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= upper:
                raise ValueError(f"invalid_{name}")
        if not math.isfinite(self.delay) or not 0 <= self.delay <= 60:
            raise ValueError("invalid_delay")
        if not math.isfinite(self.timeout) or not 0 < self.timeout <= 60:
            raise ValueError("invalid_timeout")
        host = urlsplit(start).hostname
        if host == "localhost" and not self.allow_loopback:
            raise ValueError("loopback_requires_explicit_flag")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            if not (address.is_loopback and self.allow_loopback):
                raise ValueError("non_public_ip_literal")

    def admit(self, value: str) -> tuple[str | None, str | None]:
        try:
            normalized = normalize_url(value)
            if origin(normalized) != self.allowed_origin:
                return None, "outside_origin"
            return normalized, None
        except (ValueError, UnicodeError):
            return None, "invalid_or_sensitive_url"
