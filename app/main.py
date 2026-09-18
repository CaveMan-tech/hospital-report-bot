"""HTTP layer. Thin on purpose: every route is a small wrapper around the engine."""

from __future__ import annotations

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app import analyst as A
from app.config import get_settings
from app.engine.extract import get_extractor
from app.engine.machine import Engine
from app.engine.models import Channel, EngineReply
from app.engine.packs import get_pack
from app.ratelimit import DailyDedupe, RateLimiter
from app.seed import seed
from app.store.memory import MemoryStore

logging.basicConfig(level=logging.INFO)
WEB = Path(__file__).parent / "web"
templates = Jinja2Templates(directory=WEB / "templates")

chat_limiter = RateLimiter(limit=40, window_seconds=600)
lookup_limiter = RateLimiter(limit=10, window_seconds=600)
dedupe = DailyDedupe()


def build_engine() -> Engine:
    cfg = get_settings()
    if cfg.store == "supabase":
        from app.store.supabase import SupabaseStore

        store = SupabaseStore(cfg.supabase_url, cfg.supabase_service_key)
    else:
        store = MemoryStore()
    return Engine(
        store=store,
        extractor=get_extractor(cfg.extract_mode, cfg.openai_model),
        pack=get_pack(cfg.pack, cfg.allow_unverified),
        ref_secret=cfg.ref_code_secret,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_settings()
    problems = cfg.production_problems() if cfg.railway_environment else []
    # Secrets and the verified gate are hard stops. The rest are loud warnings so a
    # demo deployment (mock extractor, in-memory store) is still possible on purpose.
    fatal = [p for p in problems if p.startswith(("REF_CODE_SECRET", "ANALYST_PASSWORD", "ALLOW_UNVERIFIED"))]
    for p in problems:
        logging.getLogger(__name__).warning("DEPLOYMENT CHECK: %s", p)
    if fatal:
        raise RuntimeError("Refusing to start: " + "; ".join(fatal))
    app.state.engine = build_engine()
    if get_settings().demo_mode:
        n = await seed(app.state.engine.store)
        logging.getLogger(__name__).info("Seeded %s sample reports", n)

    async def purge_loop():
        while True:  # expired sessions may still hold an unfinished story; do not keep them
            await asyncio.sleep(600)
            await app.state.engine.store.purge_expired_sessions()

    task = asyncio.create_task(purge_loop())
    yield
    task.cancel()


app = FastAPI(title="Hospital Pattern Bot", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")


def engine_of(request: Request) -> Engine:
    return request.app.state.engine


def client_ip(request: Request) -> str:
    """Used in memory only, for rate limiting and the daily dedupe key. Never stored or logged.

    Behind Railway's proxy the trustworthy value is X-Real-IP, or the right-most
    X-Forwarded-For entry. The left-most entry is whatever the client chose to send.
    """
    real = request.headers.get("x-real-ip", "").strip()
    if real:
        return real
    forwarded = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if forwarded:
        return forwarded[-1]
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def privacy_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith(("/analyst", "/api")):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    return "User-agent: *\nDisallow: /analyst\nDisallow: /api\n"


class ChatIn(BaseModel):
    session_id: str | None = None
    channel: Channel = "web"
    text: str = Field(default="", max_length=4000)


class CodeIn(BaseModel):
    ref_code: str = Field(max_length=32)


@app.get("/", response_class=HTMLResponse)
async def chat_page(request: Request, engine: Engine = Depends(engine_of)):
    return templates.TemplateResponse(request, "chat.html", {
        "org_name": engine.pack.org_name, "demo_mode": get_settings().demo_mode})


@app.post("/api/chat", response_model=EngineReply)
async def chat(body: ChatIn, request: Request, engine: Engine = Depends(engine_of)):
    ip = client_ip(request)
    if not chat_limiter.allow(ip):
        raise HTTPException(429, "Too many messages. Please wait a few minutes.")
    return await engine.handle_message(body.session_id, body.channel, body.text, dedupe_key=dedupe.key(ip))


@app.post("/api/report/lookup")
async def lookup(body: CodeIn, request: Request, engine: Engine = Depends(engine_of)):
    if not lookup_limiter.allow(client_ip(request)):
        raise HTTPException(429, "Too many attempts. Please wait a few minutes.")
    return {"message": await engine.lookup(body.ref_code)}


@app.post("/api/demo/next-day", response_model=EngineReply)
async def demo_next_day(body: CodeIn, request: Request, engine: Engine = Depends(engine_of)):
    """Demo only: pretend a day has passed and start the follow-up conversation."""
    if not get_settings().demo_mode:
        raise HTTPException(404)
    if not lookup_limiter.allow(client_ip(request)):
        raise HTTPException(429, "Too many attempts. Please wait a few minutes.")
    reply = await engine.start_followup(body.ref_code)
    if reply is None:
        raise HTTPException(404, "No report with that code.")
    return reply


# ---------------------------------------------------------------- analyst view
# The partner organisation's side. Nothing here is public.

basic = HTTPBasic(realm="Analyst")


def analyst_auth(creds: HTTPBasicCredentials = Depends(basic)) -> None:
    expected = get_settings().analyst_password.encode()
    if not secrets.compare_digest(creds.password.encode(), expected):
        raise HTTPException(401, "Wrong password", headers={"WWW-Authenticate": 'Basic realm="Analyst"'})


def _pattern_or_404(rows: list[dict], hospital_id: str, category: str) -> dict:
    for p in rows:
        if p["hospital_id"] == hospital_id and p["category"] == category:
            return p
    # Below-threshold groups are indistinguishable from groups that do not exist.
    raise HTTPException(404, "No pattern above the threshold for that hospital and category.")


@app.get("/analyst", response_class=HTMLResponse, dependencies=[Depends(analyst_auth)])
async def analyst_home(request: Request, engine: Engine = Depends(engine_of)):
    reports = await engine.store.list_reports()
    rows = A.patterns(reports, engine.pack)
    return templates.TemplateResponse(request, "analyst.html", {
        "org_name": engine.pack.org_name, "patterns": rows, "threshold": A.THRESHOLD,
        "window": A.WINDOW_DAYS, "sample": any(p["includes_sample_data"] for p in rows),
        "held_back": sum(r.credibility == "review" for r in reports)})


@app.get("/analyst/pattern/{hospital_id}/{category}", response_class=HTMLResponse,
         dependencies=[Depends(analyst_auth)])
async def analyst_pattern(hospital_id: str, category: str, request: Request,
                          engine: Engine = Depends(engine_of)):
    reports = await engine.store.list_reports()
    pattern = _pattern_or_404(A.patterns(reports, engine.pack), hospital_id, category)
    rs = A.pattern_reports(reports, hospital_id, category)
    return templates.TemplateResponse(request, "pattern.html", {
        "org_name": engine.pack.org_name, "p": pattern, "reports": rs, "slices": A.slices(rs),
        "brief": A.brief(pattern, engine.pack)})


@app.get("/analyst/brief/{hospital_id}/{category}.md", response_class=PlainTextResponse,
         dependencies=[Depends(analyst_auth)])
async def analyst_brief(hospital_id: str, category: str, engine: Engine = Depends(engine_of)):
    rows = A.patterns(await engine.store.list_reports(), engine.pack)
    text = A.brief(_pattern_or_404(rows, hospital_id, category), engine.pack)
    name = f"brief-{hospital_id}-{category}.md"
    return PlainTextResponse(text, media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/analyst/patterns.csv", dependencies=[Depends(analyst_auth)])
async def analyst_patterns_csv(engine: Engine = Depends(engine_of)):
    text = A.patterns_csv(A.patterns(await engine.store.list_reports(), engine.pack))
    return PlainTextResponse(text, media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="patterns.csv"'})


@app.get("/analyst/facets.csv", dependencies=[Depends(analyst_auth)])
async def analyst_facets_csv(engine: Engine = Depends(engine_of)):
    text = A.facets_csv(await engine.store.list_reports(), engine.pack)
    return PlainTextResponse(text, media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="facets.csv"'})


@app.post("/analyst/reports/{report_id}/{action}", dependencies=[Depends(analyst_auth)])
async def analyst_set_credibility(report_id: str, action: str, request: Request,
                                  engine: Engine = Depends(engine_of)):
    new = {"exclude": "excluded", "accept": "ok", "hold": "review"}.get(action)
    report = await engine.store.get_report(report_id)
    if new is None or report is None:
        raise HTTPException(404)
    report.credibility = new  # type: ignore[assignment]
    await engine.store.save_report(report)
    back = request.headers.get("referer") or "/analyst"
    return RedirectResponse(back, status_code=303)


@app.get("/healthz")
async def healthz():
    return {"ok": True}
