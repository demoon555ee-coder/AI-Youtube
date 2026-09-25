from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
import logging
import time
import uuid

from app.db.session import engine  # pyright: ignore[reportMissingImports]
from app.db.migrations import apply_migrations  # pyright: ignore[reportMissingImports]
from app.db.schema_gate import schema_is_current  # pyright: ignore[reportMissingImports]
from app.deployment import assert_production_settings  # pyright: ignore[reportMissingImports]
from app.models.base import Base  # pyright: ignore[reportMissingImports]
from app import models  # pyright: ignore[reportMissingImports]  # noqa: F401
from app.config import settings  # pyright: ignore[reportMissingImports]
from app.api.runtime import router as agent_runtime_router  # pyright: ignore[reportMissingImports]
from app.api.planner import router as planner_router  # pyright: ignore[reportMissingImports]
from app.api.learning import router as learning_router  # pyright: ignore[reportMissingImports]
from app.api.youtube import router as youtube_router  # pyright: ignore[reportMissingImports]
from app.api.brain import router as brain_router  # pyright: ignore[reportMissingImports]
from app.api.content import router as content_router  # pyright: ignore[reportMissingImports]
from app.api.workflows import router as workflow_router  # pyright: ignore[reportMissingImports]
from app.api.routes import router as project_router  # pyright: ignore[reportMissingImports]
from app.api.experiments import router as experiments_router  # pyright: ignore[reportMissingImports]
from app.api.research import router as research_router  # pyright: ignore[reportMissingImports]
from app.api.autopilot import router as autopilot_router  # pyright: ignore[reportMissingImports]
from app.api.intelligence import router as intelligence_router  # pyright: ignore[reportMissingImports]
from app.api.portfolio import router as portfolio_router  # pyright: ignore[reportMissingImports]
from app.api.routing import router as routing_router  # pyright: ignore[reportMissingImports]
from app.api.portfolio_autopilot import router as portfolio_autopilot_router  # pyright: ignore[reportMissingImports]
from app.api.portfolio_manager import router as portfolio_manager_router  # pyright: ignore[reportMissingImports]
from app.api.research_intelligence import router as research_intelligence_router  # pyright: ignore[reportMissingImports]
from app.api.research_scheduler import router as research_scheduler_router  # pyright: ignore[reportMissingImports]
from app.api.trends import router as trends_router  # pyright: ignore[reportMissingImports]
from app.api.opportunity_intelligence import router as opportunity_intelligence_router  # pyright: ignore[reportMissingImports]
from app.api.quality import router as quality_router  # pyright: ignore[reportMissingImports]
from app.api.postpublish import router as postpublish_router  # pyright: ignore[reportMissingImports]
from app.api.evolution import router as evolution_router  # pyright: ignore[reportMissingImports]
from app.api.creative import router as creative_router  # pyright: ignore[reportMissingImports]
from app.api.multimodal import router as multimodal_router  # pyright: ignore[reportMissingImports]
from app.api.autonomous_optimization import router as autonomous_optimization_router  # pyright: ignore[reportMissingImports]
from app.api.execution import router as execution_router  # pyright: ignore[reportMissingImports]
from app.api.governance import router as governance_router  # pyright: ignore[reportMissingImports]
from app.api.strategy import router as strategy_router  # pyright: ignore[reportMissingImports]
from app.api.auth import router as auth_router  # pyright: ignore[reportMissingImports]
from app.api.billing import router as billing_router  # pyright: ignore[reportMissingImports]
from app.api.privacy import router as privacy_router  # pyright: ignore[reportMissingImports]
from app.auth.authorization import enforce_request_authorization  # pyright: ignore[reportMissingImports]
from app.api.observability import router as observability_router, database_ready  # pyright: ignore[reportMissingImports]
from app.observability import metrics, tracing  # pyright: ignore[reportMissingImports]
from app.observability.access import metrics_token_matches  # pyright: ignore[reportMissingImports]


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.app_env == "production":
        assert_production_settings()
    if settings.auto_migrate:
        await apply_migrations(engine)
    try:
        yield
    finally:
        await engine.dispose()


logger = logging.getLogger("youtube_ai_platform")


app = FastAPI(title="YouTube AI Platform", version=settings.app_version, lifespan=lifespan, dependencies=[Depends(enforce_request_authorization)], docs_url=None if settings.app_env == "production" else "/docs", redoc_url=None if settings.app_env == "production" else "/redoc")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    span = tracing.start_request(request.headers.get("traceparent"))
    request.state.request_id = request_id
    request.state.trace_id = span.trace_id
    try:
        response = await call_next(request)
        status = response.status_code
    except Exception:
        status = 500
        raise
    finally:
        route = getattr(request.scope.get("route"), "path", None) or request.url.path
        duration = time.perf_counter() - started
        metrics.inc("http_requests_total", labels={"method": request.method, "route": route, "status": str(status)})
        metrics.observe("http_request_duration_seconds", duration, labels={"method": request.method, "route": route})
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Trace-ID"] = span.trace_id
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
    response.headers.setdefault("Cache-Control", "no-store")
    if settings.app_env == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    traceparent = tracing.traceparent()
    if traceparent:
        response.headers["traceparent"] = traceparent
    return response
app.include_router(agent_runtime_router)
app.include_router(planner_router)
app.include_router(learning_router)
app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(privacy_router)
app.include_router(observability_router)
app.include_router(project_router)
app.include_router(youtube_router)
app.include_router(brain_router)
app.include_router(content_router)
app.include_router(workflow_router)
app.include_router(experiments_router)
app.include_router(research_router)
app.include_router(autopilot_router)
app.include_router(intelligence_router)
app.include_router(portfolio_router)
app.include_router(routing_router)
app.include_router(portfolio_autopilot_router)
app.include_router(portfolio_manager_router)
app.include_router(research_intelligence_router)
app.include_router(research_scheduler_router)
app.include_router(trends_router)
app.include_router(opportunity_intelligence_router)
app.include_router(quality_router)
app.include_router(postpublish_router)
app.include_router(evolution_router)
app.include_router(creative_router)
app.include_router(multimodal_router)
app.include_router(autonomous_optimization_router)
app.include_router(execution_router)
app.include_router(governance_router)
app.include_router(strategy_router)


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    logger.exception("Unhandled application error", exc_info=exc)
    detail = str(exc) if settings.app_env != "production" else "Internal server error"
    return JSONResponse(status_code=500, content={"detail": detail})


@app.get("/api/v1/health")
async def health():
    readiness = []
    if settings.app_env == "production" and not settings.app_encryption_key:
        readiness.append("APP_ENCRYPTION_KEY is required in production")
    return {"status": "ok" if not readiness else "degraded", "version": settings.app_version, "readiness": readiness}


@app.get("/api/v1/health/live")
async def liveness():
    return {"status": "ok", "version": settings.app_version}


@app.get("/api/v1/health/ready")
async def readiness():
    checks = {}
    db_ok, db_error = await database_ready()
    checks["database"] = {"ok": db_ok, "detail": db_error}
    checks["encryption"] = {"ok": settings.app_env != "production" or bool(settings.app_encryption_key), "detail": None if settings.app_env != "production" or settings.app_encryption_key else "APP_ENCRYPTION_KEY is required"}
    if settings.schema_gate_enabled and db_ok:
        schema_ok, applied, expected = await schema_is_current(engine)
        checks["schema"] = {"ok": schema_ok, "applied": applied, "expected": expected}
    ok = all(item["ok"] for item in checks.values())
    return JSONResponse(status_code=200 if ok else 503, content={"status": "ready" if ok else "not_ready", "version": settings.app_version, "checks": checks})


@app.get("/api/v1/metrics")
async def metrics_endpoint(request: Request):
    if settings.app_env == "production" and not settings.metrics_public and not metrics_token_matches(request):
        raise HTTPException(status_code=404, detail="Not found")
    return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4; charset=utf-8")
