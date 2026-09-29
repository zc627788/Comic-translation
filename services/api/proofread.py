"""Loopback-only proofreading experiment, separate from the production API."""

from typing import Annotated

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from services.worker.bubble_pipeline import ROOT
from services.worker.proofreading import SAMPLES, Proofreader, context_payload
from services.worker.translation import TranslationError

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
reader = Proofreader()
UI = ROOT / "apps/proofreader"


@app.middleware("http")
async def protect(request: Request, call_next):
    if request.method == "POST":
        if (request.headers.get("origin") not in {
                "http://127.0.0.1:4182", "http://localhost:4182"}
                or request.headers.get("x-comic-lab") != "1"
                or request.headers.get("content-type", "").split(";")[0] != "application/json"):
            return JSONResponse({"detail": "LOCAL_REQUEST_REQUIRED"}, status_code=403)
        # Bound streamed payloads too, not only the caller-supplied Content-Length.
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 16_384:
                return JSONResponse({"detail": "BODY_TOO_LARGE"}, status_code=413)
            chunks.append(chunk)
        request._body = b"".join(chunks)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
    return response


@app.exception_handler(ValueError)
async def value_error(request, exc):
    code = str(exc)
    # Never expose paths or unexpected parser/internal exception text.
    safe = code if code.isupper() and len(code) < 80 and " " not in code else "INVALID_DATA"
    status = 409 if safe in {"REVISION_CONFLICT", "RESOURCE_BUSY"} else 400
    return JSONResponse({"detail": safe}, status_code=status)


@app.exception_handler(TranslationError)
async def translation_error(request, exc):
    return JSONResponse({"detail": exc.code}, status_code=502)


@app.exception_handler(FileNotFoundError)
async def missing_file(request, exc):
    return JSONResponse({"detail": "LOCAL_SAMPLE_MISSING"}, status_code=404)


class Version(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: Annotated[int, Field(ge=0)]


class Revision(Version):
    edits: dict[str, dict[str, str]] = Field(default_factory=dict, max_length=20)
    restore: bool = False


@app.get("/")
def index():
    return FileResponse(UI / "index.html")


@app.get("/assets/{name}")
def asset(name: str):
    if name not in {"reader.js", "reader.css"}:
        raise HTTPException(404)
    return FileResponse(UI / name)


@app.get("/api/samples")
def samples():
    return [{"id": sample} for sample in SAMPLES]


def public(state):
    return {k: v for k, v in state.items() if k not in {"baseline_hash", "image"}}


@app.get("/api/pages/{sample}")
def page(sample: str):
    state = public(reader.state(sample))
    try:
        text, ids = context_payload(state["regions"])
        state["context_preview"] = {"text": text, "ids": ids, "characters": len(text),
                                    "bytes": len(text.encode("utf-8"))}
    except ValueError as exc:
        state["context_preview"] = {"error": str(exc)}
    return state


@app.post("/api/pages/{sample}/revision")
def revise(sample: str, request: Revision):
    return public(reader.revise(sample, request.revision, request.edits, request.restore))


@app.post("/api/pages/{sample}/context")
def context(sample: str, request: Version):
    return reader.context(sample, request.revision)


@app.get("/images/{sample}/{kind}")
def picture(sample: str, kind: str, revision: int | None = None):
    if kind not in {"original.png", "translated.png", "export.png"}:
        raise HTTPException(404)
    return FileResponse(reader.image_path(sample, revision, original=kind == "original.png"),
                        media_type="image/png",
                        filename=f"{sample}-review.png" if kind == "export.png" else None)
