"""Read-only local preview: fixed allowlist, no directory listing or outbound requests."""

import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path("artifacts/private/free-api-probe").resolve()
ALLOWED = {"/": ROOT / "index.html", "/index.html": ROOT / "index.html"}
ALLOWED.update({"/" + p.name: p for p in ROOT.glob("*.png")})


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.headers.get("Host") not in {"127.0.0.1:4175", "localhost:4175"}:
            self.send_error(403)
            return
        file = ALLOWED.get(urlsplit(self.path).path)
        if file is None or not file.is_file():
            self.send_error(404)
            return
        body = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(file)[0] + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; "
                         "frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    print("Local experiment viewer: http://127.0.0.1:4175", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 4175), Handler).serve_forever()
