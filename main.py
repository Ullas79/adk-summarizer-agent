"""
main.py — FastAPI entry point for the ADK Summarizer Agent on Cloud Run.

Endpoints
---------
GET  /health       Liveness probe (always 200 if the process is alive)
GET  /ready        Readiness probe (200 only after ADK runner initialised)
POST /run          Summarise text  (primary agent endpoint)
GET  /             API index / usage hint
"""

import json
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field, field_validator

from agent import create_summarizer_agent
from config import get_settings
from logger import get_logger

cfg = get_settings()
log = get_logger("main")

# ── Shared state ──────────────────────────────────────────────────────────────
_session_service: InMemorySessionService | None = None
_runner: Runner | None = None
_ready: bool = False


# ── Lifespan: initialise ADK once at startup ──────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _session_service, _runner, _ready

    log.info("Starting ADK runner initialisation…")
    t0 = time.perf_counter()

    _session_service = InMemorySessionService()
    agent = create_summarizer_agent()
    _runner = Runner(
        agent=agent,
        app_name=cfg.app_name,
        session_service=_session_service,
    )
    _ready = True

    elapsed = round((time.perf_counter() - t0) * 1000)
    log.info("ADK runner ready", startup_ms=elapsed)

    yield

    log.info("Shutting down.")
    _ready = False


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="ADK Summarizer Agent",
    description=(
        "Single AI agent built with Google ADK + Gemini on Vertex AI, "
        "deployed on Cloud Run."
    ),
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


def _parse_origins(raw: str) -> list[str]:
    if raw.strip() == "*":
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_origins(cfg.cors_allow_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Request-ID + structured access logging middleware ─────────────────────────
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    request.state.request_id = request_id

    t0 = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - t0) * 1000)

    log.info(
        "HTTP request",
        httpRequest={
            "requestMethod": request.method,
            "requestUrl": str(request.url),
            "status": response.status_code,
            "latencyMs": elapsed_ms,
            "userAgent": request.headers.get("user-agent", ""),
            "remoteIp": request.client.host if request.client else "",
        },
        request_id=request_id,
    )

    response.headers["X-Request-Id"] = request_id
    return response


# ── Schemas ───────────────────────────────────────────────────────────────────
class RunRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to summarise")
    user_id: str = Field(default="anonymous", description="Optional user identifier")

    @field_validator("text")
    @classmethod
    def check_length(cls, v: str) -> str:
        if len(v) > cfg.max_input_chars:
            raise ValueError(
                f"text exceeds maximum allowed length of {cfg.max_input_chars:,} characters."
            )
        return v


class SummaryOutput(BaseModel):
    summary: str
    key_points: list[str]
    word_count_estimate: int
    language: str


class RunResponse(BaseModel):
    status: str = "ok"
    session_id: str
    user_id: str
    input_chars: int
    latency_ms: int
    result: SummaryOutput


# ── Helpers ───────────────────────────────────────────────────────────────────
def _require_ready():
    if not _ready:
        raise HTTPException(
            status_code=503, detail="Agent not ready. Try again shortly."
        )


async def _invoke_agent(user_id: str, session_id: str, text: str) -> str:
    """Run the ADK agent and return the raw text reply."""
    await _session_service.create_session(
        app_name=cfg.app_name,
        user_id=user_id,
        session_id=session_id,
    )

    user_message = types.Content(
        role="user",
        parts=[types.Part(text=f"Summarise the following text:\n\n{text}")],
    )

    raw_reply = ""
    async for event in _runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=user_message,
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                raw_reply = event.content.parts[0].text
            break

    return raw_reply.strip()


def _parse_agent_reply(raw: str) -> SummaryOutput:
    """Parse the JSON the agent returns into a typed object."""
    # Strip accidental markdown fences if the model added them
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[1:])
    if cleaned.endswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[:-1])

    try:
        data = json.loads(cleaned)
        return SummaryOutput(**data)
    except json.JSONDecodeError as exc:
        log.warning("Agent returned non-JSON output", error=str(exc), raw=raw[:500])
        if cfg.strict_json_output:
            raise HTTPException(
                status_code=502, detail="Model returned invalid JSON output."
            )
        return SummaryOutput(
            summary=cleaned,
            key_points=[],
            word_count_estimate=len(cleaned.split()),
            language="und",
        )
    except Exception as exc:
        log.warning(
            "Agent JSON failed schema validation", error=str(exc), raw=raw[:500]
        )
        if cfg.strict_json_output:
            raise HTTPException(
                status_code=502, detail="Model output schema validation failed."
            )
        return SummaryOutput(
            summary=cleaned,
            key_points=[],
            word_count_estimate=len(cleaned.split()),
            language="und",
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def index():
    return {
        "service": cfg.app_name,
        "version": "2.0.0",
        "status": "ready" if _ready else "starting",
        "endpoints": {
            "POST /run": "Submit text for summarisation",
            "GET /health": "Liveness probe",
            "GET /ready": "Readiness probe",
            "GET /docs": "Interactive API documentation",
        },
    }


@app.get("/health", tags=["ops"])
async def health():
    """Liveness probe — always 200 while the process is alive."""
    return {"status": "ok"}


@app.get("/ready", tags=["ops"])
async def ready():
    """Readiness probe — 200 only after the ADK runner has initialised."""
    if not _ready:
        raise HTTPException(status_code=503, detail="Not ready yet.")
    return {"status": "ready"}


@app.post("/run", response_model=RunResponse, tags=["agent"])
async def run_agent(payload: RunRequest, request: Request):
    """
    Summarise text using the ADK agent on Vertex AI.

    Returns a structured summary, 3 key points, estimated word count,
    and the detected language of the input.
    """
    _require_ready()

    session_id = str(uuid.uuid4())
    request_id = getattr(request.state, "request_id", session_id)

    log.info(
        "Agent invocation started",
        session_id=session_id,
        request_id=request_id,
        user_id=payload.user_id,
        input_chars=len(payload.text),
    )

    t0 = time.perf_counter()

    raw_reply = await _invoke_agent(
        user_id=payload.user_id,
        session_id=session_id,
        text=payload.text,
    )

    latency_ms = round((time.perf_counter() - t0) * 1000)

    if not raw_reply:
        log.error("Agent returned empty response", session_id=session_id)
        raise HTTPException(status_code=500, detail="Agent returned an empty response.")

    result = _parse_agent_reply(raw_reply)

    log.info(
        "Agent invocation complete",
        session_id=session_id,
        request_id=request_id,
        latency_ms=latency_ms,
        language=result.language,
    )

    return RunResponse(
        session_id=session_id,
        user_id=payload.user_id,
        input_chars=len(payload.text),
        latency_ms=latency_ms,
        result=result,
    )


# ── Local dev ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=cfg.port,
        log_level=cfg.log_level.lower(),
        reload=False,
    )
