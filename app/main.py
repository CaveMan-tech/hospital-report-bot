"""HTTP layer. Thin on purpose: every route is a small wrapper around the engine."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.config import get_settings
from app.engine.extract import get_extractor
from app.engine.machine import Engine
from app.engine.models import Channel, EngineReply
from app.engine.packs import get_pack
from app.ratelimit import DailyDedupe, RateLimiter
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
        from app.store.supabase import SupabaseStore  # noqa: PLC0415

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
    app.state.engine = build_engine()
    yield


app = FastAPI(title="Hospital Pattern Bot", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")


def engine_of(request: Request) -> Engine:
    return request.app.state.engine


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


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


@app.get("/healthz")
async def healthz():
    return {"ok": True}
