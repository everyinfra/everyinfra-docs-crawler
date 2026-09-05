"""Synthetic, loopback-only HTTP fixtures. Never serves workspace files."""

from contextlib import contextmanager
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from time import monotonic


def page(title="Synthetic document", links=(), text="Synthetic fixture content."):
    anchors = "".join(f'<a href="{escape(link, quote=True)}">Link</a>' for link in links)
    title_tag = f"<title>{escape(title)}</title>" if title is not None else ""
    body = f"<!doctype html><html><head>{title_tag}</head><body><main><p>{escape(text)}</p></main>{anchors}</body></html>"
    return 200, {"Content-Type": "text/html; charset=utf-8"}, body


@contextmanager
def fixture_site(routes):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append({"path": self.path, "method": self.command, "time": monotonic(),
                             "cookie": self.headers.get("Cookie"), "authorization": self.headers.get("Authorization")})
            status, headers, body = routes.get(self.path, (404, {"Content-Type": "text/plain"}, "Not found"))
            body = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(status)
            for key, value in headers.items():
                if value is not None:
                    self.send_header(key, value)
            if "Content-Length" not in headers:
                self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def demo_routes():
    return {
        "/robots.txt": (200, {"Content-Type": "text/plain"}, "User-agent: *\nDisallow: /private\n"),
        "/": page("EveryInfra synthetic docs", ("/guide", "/guide#repeat", "/untitled", "/private", "/broken", "/image")),
        "/guide": page("=Synthetic formula-like title", ("/page2",), "A source-linked guide for a synthetic API."),
        "/page2": page("Pagination sample", ("/guide",), "Second fixture page."),
        "/untitled": page(None, text="A document with no title; do not invent one."),
        "/private": page("Must never be fetched"),
        "/broken": (503, {"Content-Type": "text/plain"}, "Synthetic service unavailable"),
        "/image": (200, {"Content-Type": "image/png"}, b"synthetic-not-a-real-image"),
    }
