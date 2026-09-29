"""Read-only localhost evidence preview; no repository traversal or translation requests."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def make_handler(corpus, run_id):
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    files = {"/": (corpus / "runs" / run_id / "review.html", "text/html; charset=utf-8")}
    comparison = corpus.parent / "korean-comparison-v1" / "comparison-v1"
    if (comparison / "review.html").is_file():
        files["/ocr"] = (comparison / "review.html", "text/html; charset=utf-8")
        annotations = json.loads((comparison.parent / "annotations-v1.json").read_text("utf-8"))
        for row in annotations["regions"]:
            sid = row["id"]
            files[f"/ocr-crops/{sid}.png"] = (
                comparison / "raw-1x-block" / f"{sid}.png", "image/png")
    model_run = corpus.parent / "korean-model-v2" / "models-v2"
    if (model_run / "review.html").is_file():
        files["/models"] = (model_run / "review.html", "text/html; charset=utf-8")
        annotations = json.loads((model_run.parent / "annotations-v2.json").read_text("utf-8"))
        for row in annotations["regions"]:
            sid = row["id"]
            files[f"/model-crops/{sid}.png"] = (model_run / f"{sid}.png", "image/png")
    for sample in manifest["samples"]:
        sid = sample["id"]
        files[f"/images/{sid}.png"] = (corpus / sample["path"], "image/png")
        files[f"/results/{sid}/translated.png"] = (
            corpus / "runs" / run_id / sid / "translated.png", "image/png")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            host = self.headers.get("Host", "")
            if host not in {f"127.0.0.1:{self.server.server_port}",
                            f"localhost:{self.server.server_port}"}:
                self.send_error(403)
                return
            item = files.get(urlsplit(self.path).path)
            if not item or not item[0].is_file():
                self.send_error(404)
                return
            payload = item[0].read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", item[1])
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; "
                             "frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="baseline-v1")
    parser.add_argument("--port", default=4177, type=int)
    args = parser.parse_args()
    if not args.run_id.replace("-", "").isalnum():
        parser.error("Invalid run ID")
    handler = make_handler(ROOT / "artifacts/private/quality-v1", args.run_id)
    print(f"Read-only evidence: http://127.0.0.1:{args.port}/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
