"""Local-only development API; never pretends model inference is available."""

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from services.worker.capabilities import get_capabilities, is_pipeline_ready

app = FastAPI(title="Comic Translation Development API", version="0.0.1")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])


@app.middleware("http")
async def request_metadata(request: Request, call_next):
    request.state.request_id = str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/health/live")
def liveness():
    return {"service": "comic-translation-api", "status": "alive", "version": "0.0.1"}


@app.get("/health/ready")
def readiness():
    ready = is_pipeline_ready()
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"ready": ready, "capabilities": get_capabilities()},
    )


@app.get("/v1/capabilities")
def capabilities():
    return {
        "stage": "foundation",
        "upload_enabled": False,
        "billing_enabled": False,
        "capabilities": get_capabilities(),
    }


@app.post("/v1/batches")
def reject_unimplemented_translation(request: Request):
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "MODEL_NOT_READY",
                "message": "翻译模型尚未接入；未创建任务，也未扣除额度。",
                "retryable": False,
                "request_id": request.state.request_id,
                "details": {"stage": "foundation"},
            }
        },
    )
