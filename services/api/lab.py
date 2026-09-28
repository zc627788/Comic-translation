"""Loopback-only research reader. Fixed local samples; not the production upload API."""

import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.middleware.trustedhost import TrustedHostMiddleware

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / "artifacts/private"
OUTPUT = PRIVATE / "bubble-overlay"
UI = ROOT / "apps/lab-reader"
SAMPLES = {
    "ja-page7": {
        "title": "日文漫画 · 竖排对白", "language": "ja",
        "path": PRIVATE / "free-api-probe/page-007.png",
        "credit": "ブラックジャックによろしく / 佐藤秀峰，仅本地研究预览",
        "source": "https://www.densho810.com/free/",
    },
    "ko-page1": {
        "title": "韩文彩漫 · 半透明气泡", "language": "ko",
        "path": OUTPUT / "ko-1-2400.png",
        "credit": "Pepper&Carrot / David Revoy · CC BY 4.0；韩译 initbar 等。"
                  "这是韩文版法国漫画；手写体识别仍有错字。",
        "source": "https://www.peppercarrot.com/kr/webcomic/ep01_Potion-of-Flight.html",
    },
    "ko-strip": {
        "title": "韩文长条 · 原创测试图", "language": "ko",
        "path": OUTPUT / "ko-longstrip.png",
        "credit": "项目原创测试图；用于长图切片验证，不代表商业韩漫质量。",
        "source": None,
    },
}
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bubble-lab")
jobs = {}
pipeline = None


@app.middleware("http")
async def protect(request: Request, call_next):
    if request.method == "POST":
        origin = request.headers.get("origin")
        if (request.headers.get("x-comic-lab") != "1"
                or origin not in {"http://127.0.0.1:4176", "http://localhost:4176"}
                or request.headers.get("content-type", "").split(";")[0] != "application/json"):
            return JSONResponse({"detail": "LOCAL_READER_ONLY"}, status_code=403)
        body = await request.body()
        if len(body) > 1024:
            return JSONResponse({"detail": "REQUEST_TOO_LARGE"}, status_code=413)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
    return response


@app.get("/")
def index():
    return FileResponse(UI / "index.html")


@app.get("/assets/{name}")
def asset(name: str):
    if name not in {"reader.css", "reader.js"}:
        raise HTTPException(404, "NOT_FOUND")
    return FileResponse(UI / name)


@app.get("/api/samples")
def samples():
    return [{"id": key, **{k: v for k, v in value.items() if k != "path"},
             "available": value["path"].is_file()} for key, value in SAMPLES.items()]


@app.get("/samples/{sample_id}/original")
def original(sample_id: str):
    sample = SAMPLES.get(sample_id)
    if not sample or not sample["path"].is_file():
        raise HTTPException(404, "SAMPLE_NOT_AVAILABLE")
    return FileResponse(sample["path"])


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_id: str
    allow_translation: bool


def execute(job_id, sample_id):
    global pipeline

    def progress(message):
        with lock:
            jobs[job_id]["message"] = message

    try:
        from services.worker.bubble_pipeline import BubblePipeline
        if pipeline is None:
            progress("正在校验并载入本地模型")
            pipeline = BubblePipeline()
        sample = SAMPLES[sample_id]
        result = pipeline.process(sample["path"], job_id, sample["language"], progress)
        with lock:
            jobs[job_id].update(state="complete", message="处理完成，请核对机器译文", result=result)
    except Exception as exc:
        # Never return paths, provider URLs or submitted text in diagnostic messages.
        code = str(exc) if re.fullmatch(r"[A-Z_]{3,60}", str(exc)) else "LOCAL_PROCESSING_FAILED"
        with lock:
            jobs[job_id].update(state="failed", message=code)


@app.post("/api/jobs", status_code=202)
def submit(body: Submission):
    if not body.allow_translation:
        raise HTTPException(400, "TRANSLATION_NOT_ENABLED")
    if body.sample_id not in SAMPLES or not SAMPLES[body.sample_id]["path"].is_file():
        raise HTTPException(404, "SAMPLE_NOT_AVAILABLE")
    with lock:
        if any(job["state"] == "running" for job in jobs.values()):
            raise HTTPException(409, "PROCESSING_IN_PROGRESS")
        if len(jobs) >= 20:
            raise HTTPException(429, "LAB_SESSION_LIMIT")
        job_id = body.sample_id + "-" + uuid.uuid4().hex[:12]
        jobs[job_id] = {"id": job_id, "sample_id": body.sample_id,
                        "state": "running", "message": "等待本地模型"}
        executor.submit(execute, job_id, body.sample_id)
        return dict(jobs[job_id])


@app.get("/api/jobs/{job_id}")
def status(job_id: str):
    with lock:
        if job_id not in jobs:
            raise HTTPException(404, "NOT_FOUND")
        return dict(jobs[job_id])


@app.get("/results/{job_id}/{name}")
def result_file(job_id: str, name: str):
    with lock:
        job = jobs.get(job_id)
        if not job or job["state"] != "complete" or name not in {
            "translated.png", "detection.png", "safe-mask.png",
        }:
            raise HTTPException(404, "NOT_FOUND")
    return FileResponse(OUTPUT / job_id / name)
