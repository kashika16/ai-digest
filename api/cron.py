import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from ai_digest.config import load_config
from ai_digest.digest import preview_digest, run_digest, run_scheduled_digest


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if not authorized(self):
            self.respond(401, "unauthorized")
            return

        query = parse_qs(urlparse(self.path).query)
        mode = query.get("mode", ["schedule"])[0]
        config = load_config()

        if mode == "preview":
            self.respond(200, preview_digest(config, ignore_seen=True))
            return

        if mode == "send":
            run_digest(config, ignore_seen=True)
            self.respond(200, "sent")
            return

        result = run_scheduled_digest(config)
        self.respond(200, result)

    def log_message(self, format: str, *args: object) -> None:
        return

    def respond(self, status_code: int, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def authorized(request: BaseHTTPRequestHandler) -> bool:
    secret = os.environ.get("CRON_SECRET")
    if not secret:
        return True
    return request.headers.get("Authorization") == f"Bearer {secret}"
