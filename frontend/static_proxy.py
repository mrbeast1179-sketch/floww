#!/usr/bin/env python3
"""
Static file server for frontend/build/ + reverse-proxy /api/* and /ws/* to backend :8000.

This is the Node-free counterpart to frontend/serve.js — sidesteps the broken
ajv-keywords / ajv v8 incompatibility in node_modules that crashes `craco start`
(ChainDecoder: TypeError: Cannot read properties of undefined (reading 'date')
at ajv-keywords/keywords/_formatLimit.js:63). Renders the prebuilt bundle in
frontend/build/ directly, no react-scripts / webpack-dev-server dependency.

What it does:
- Serves files from frontend/build/ on http://0.0.0.0:3000 (default)
- SPA-fallback: any GET that doesn't match a real file → serves index.html
- GET/POST/OPTIONS requests whose path starts with /api/ or /ws/ → proxied to
  localhost:8000 with method, query, headers, and body forwarded faithfully

What it does NOT do:
- WebSocket upgrade (Python's stock http.server doesn't speak RFC 6455). The
  /ws/ routes will return 502 for upgrade requests; REST endpoints reach the
  backend normally. The steal-list visual verification only needs REST.

Usage:
  python3 frontend/static_proxy.py                    # :3000 -> :8000
  python3 frontend/static_proxy.py -p 8080 -b :9000   # any port pair

Auditability:
- ~90 LOC, mirrors frontend/serve.js line-for-line (proxy-first, then SPA
  fallback). Drop-in replacement; can revert by `node frontend/serve.js` once
  the ajv-keywords toolchain is fixed via `npm rebuild ajv-keywords`.
"""
from __future__ import annotations

import argparse
import http.server
import socketserver
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROXY_PREFIXES: tuple[str, ...] = ("/api/", "/ws/")


class StaticProxyHandler(http.server.SimpleHTTPRequestHandler):
    """Serves frontend/build/ statically; proxies /api/* + /ws/* to the backend."""

    BUILD_DIR: Path = Path(__file__).resolve().parent / "build"
    BACKEND_URL: str = "http://localhost:8000"

    # ---- public hook overrides ----

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler contract)
        if self._should_proxy(self.path):
            self._proxy_request()
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self._should_proxy(self.path):
            self._proxy_request()
            return
        # No POST handler in SimpleHTTPRequestHandler — emit 405 explicitly.
        self.send_error(405, "POST not supported on static path; use /api/* instead")

    def do_PUT(self) -> None:  # noqa: N802
        self._maybe_proxy_or_405()

    def do_DELETE(self) -> None:  # noqa: N802
        self._maybe_proxy_or_405()

    def do_PATCH(self) -> None:  # noqa: N802
        self._maybe_proxy_or_405()

    def do_HEAD(self) -> None:  # noqa: N802
        # BUGFIX: BaseHTTPRequestHandler.do_HEAD sends headers for the static
        # path resolved by translate_path, which would 404 /api/* requests.
        # Override to proxy HEAD just like GET, but drop the response body.
        if self._should_proxy(self.path):
            try:
                req = urllib.request.Request(
                    self.BACKEND_URL + self.path,
                    method="HEAD",
                    headers={
                        k: v for k, v in self.headers.items()
                        if k.lower() not in ("host", "transfer-encoding", "connection")
                    },
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    self.send_response(resp.status)
                    for k, v in resp.headers.items():
                        if k.lower() in ("transfer-encoding", "connection"):
                            continue
                        self.send_header(k, v)
                    self.end_headers()
            except urllib.error.HTTPError as e:
                self.send_response(e.code)
                for k, v in (e.headers or {}).items():
                    if k.lower() in ("transfer-encoding", "connection"):
                        continue
                    self.send_header(k, v)
                self.end_headers()
            except urllib.error.URLError:
                self.send_response(502)
                self.end_headers()
            return
        super().do_HEAD()

    def do_OPTIONS(self) -> None:  # noqa: N802 — CORS preflight
        if self._should_proxy(self.path):
            self._proxy_request()
            return
        self.send_response(204)
        self.send_header("Allow", "GET, POST, PUT, DELETE, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
        self.end_headers()

    # ---- translation hook (SPA fallback) ----

    def translate_path(self, path: str) -> str:
        """Map any unknown path to index.html so React Router handles the route."""
        # Strip query string for filesystem lookup; SimpleHTTPRequestHandler does this
        # already, but be explicit for clarity.
        clean = path.split("?", 1)[0]
        try:
            candidate = (self.BUILD_DIR / clean.lstrip("/")).resolve()
        except (OSError, ValueError):
            return str(self.BUILD_DIR / "index.html")
        # Containment check — don't let "../" escape build/ (defence-in-depth).
        try:
            candidate.relative_to(self.BUILD_DIR.resolve())
        except ValueError:
            return str(self.BUILD_DIR / "index.html")
        if candidate.is_file():
            return str(candidate)
        return str(self.BUILD_DIR / "index.html")

    # ---- proxy helpers ----

    @staticmethod
    def _should_proxy(path: str) -> bool:
        return any(path.startswith(p) for p in PROXY_PREFIXES)

    def _maybe_proxy_or_405(self) -> None:
        if self._should_proxy(self.path):
            self._proxy_request()
            return
        self.send_error(405)

    def _proxy_request(self) -> None:
        target_url = self.BACKEND_URL + self.path
        # Read body if present (Content-Length > 0).
        body: bytes | None = None
        content_length = self.headers.get("Content-Length")
        if content_length:
            try:
                body = self.rfile.read(int(content_length))
            except (ValueError, OSError) as e:
                self.send_error(400, f"bad Content-Length: {e}")
                return
        # Forward headers, but drop hop-by-hop / Host (urllib will set its own).
        fwd_headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in ("host", "transfer-encoding", "connection", "content-length")
        }
        if body is not None:
            fwd_headers.setdefault("Content-Type", self.headers.get("Content-Type", "application/octet-stream"))
        req = urllib.request.Request(
            url=target_url,
            data=body,
            method=self.command,
            headers=fwd_headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = resp.read()
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() in ("transfer-encoding", "connection"):
                        continue
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(payload)))
                # CORS Echo removed — backend already sends its own
                # Access-Control-Allow-Origin (env-gated via CORS_ORIGINS;
                # dev defaults to *, prod locks to a single origin).
                # Hardcoding * here would override prod's locked origin.
                self.end_headers()
                self.wfile.write(payload)
        except urllib.error.HTTPError as e:
            # Pass backend's HTTP error through verbatim.
            payload = e.read()
            self.send_response(e.code)
            for k, v in (e.headers or {}).items():
                if k.lower() in ("transfer-encoding", "connection"):
                    continue
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except urllib.error.URLError as e:
            err_body = b'{"error":"backend unavailable","reason":"' + str(e.reason).encode("utf-8") + b'"}'
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err_body)))
            self.end_headers()
            self.wfile.write(err_body)

    # ---- logging ----

    def log_message(self, fmt: str, *args) -> None:
        # Keep the standard timestamped one-liner; respect parent behaviour.
        sys.stderr.write(
            f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}\n"
        )


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """One thread per request — keeps the dashboard fanning 20+ panel GETs snappy."""
    daemon_threads = True
    allow_reuse_address = True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("-p", "--port", type=int, default=3000, help="frontend listen port (default 3000)")
    ap.add_argument(
        "-b", "--backend",
        default="http://localhost:8000",
        help="backend base URL to proxy /api/* and /ws/* to (default http://localhost:8000)",
    )
    ap.add_argument(
        "--build",
        default=str(Path(__file__).resolve().parent / "build"),
        help="static build dir to serve (default frontend/build/)",
    )
    args = ap.parse_args()

    # Mutate class attributes so do_GET/do_POST resolve to the user's flags.
    StaticProxyHandler.BUILD_DIR = Path(args.build).resolve()
    if not StaticProxyHandler.BUILD_DIR.is_dir():
        sys.exit(f"build dir not found: {StaticProxyHandler.BUILD_DIR}", 2)
    StaticProxyHandler.BACKEND_URL = args.backend.rstrip("/")

    server = ThreadingHTTPServer(("0.0.0.0", args.port), StaticProxyHandler)
    print(
        f"static-proxy on http://localhost:{args.port}\n"
        f"  serving  : {StaticProxyHandler.BUILD_DIR}\n"
        f"  proxying : {PROXY_PREFIXES} -> {StaticProxyHandler.BACKEND_URL}\n"
        "(Ctrl-C to stop)",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstatic-proxy shutting down", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
