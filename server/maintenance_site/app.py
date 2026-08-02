#!/usr/bin/env python3
"""Standalone Oryntra maintenance server.

This server intentionally does not import the Oryntra backend, market-data
providers, scanner routes, account routes, or research tools. It exposes only:

- / and /index.html
- /legal/methodology and /methodology
- /static/*
- /health

Everything else returns 404.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

SITE_ROOT = Path(__file__).resolve().parent


class MaintenanceHandler(SimpleHTTPRequestHandler):
    server_version = "OryntraMaintenance/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE_ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'none'; frame-src 'none'; "
            "object-src 'none'; base-uri 'self'; form-action 'none'",
        )
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802 - standard-library handler API
        path = unquote(urlsplit(self.path).path)

        if path in {"/", "/index.html"}:
            self._serve_file(SITE_ROOT / "index.html", "text/html; charset=utf-8")
            return

        if path in {"/methodology", "/methodology/", "/legal/methodology", "/legal/methodology/"}:
            self._serve_file(SITE_ROOT / "legal" / "methodology.html", "text/html; charset=utf-8")
            return

        if path == "/health":
            payload = json.dumps(
                {
                    "status": "maintenance",
                    "service": "oryntra-ai",
                    "public_features": "offline",
                }
            ).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path.startswith("/static/"):
            relative = path.removeprefix("/")
            candidate = (SITE_ROOT / relative).resolve()
            static_root = (SITE_ROOT / "static").resolve()
            try:
                candidate.relative_to(static_root)
            except ValueError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if candidate.is_file():
                content_type, _ = mimetypes.guess_type(str(candidate))
                self._serve_file(candidate, content_type or "application/octet-stream")
                return

        self.send_error(HTTPStatus.NOT_FOUND, "This service is in maintenance mode")

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)

    def do_PUT(self) -> None:  # noqa: N802
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)

    def do_DELETE(self) -> None:  # noqa: N802
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)

    def _serve_file(self, path: Path, content_type: str) -> None:
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {self.address_string()} {format % args}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the standalone Oryntra maintenance website")
    parser.add_argument("--host", default=os.getenv("ORYNTRA_MAINTENANCE_HOST", "0.0.0.0"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("ORYNTRA_MAINTENANCE_PORT", "8000")),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), MaintenanceHandler)
    print(f"Oryntra maintenance site: http://{args.host}:{args.port}")
    print("Only the announcement, methodology, static assets, and /health are available.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping maintenance server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
