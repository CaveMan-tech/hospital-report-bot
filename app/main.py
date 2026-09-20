"""HTTP layer. Thin on purpose: every route is a small wrapper around the engine."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app import analyst as A
from app.channels.telegram import TelegramAdapter
from app.channels.telegram_api import HttpBotAPI
from app.config import get_settings
from app.engine.extract import get_extractor
from app.engine.machine import Engine
from app.engine.models import AuditEntry, Channel, EngineReply
from app.engine.packs import get_pack
from app.ratelimit import DailyDedupe, RateLimiter
from app.seed import seed
from app.store.memory import MemoryStore
from app.voice import MAX_BYTES, make_openai_transcriber

logging.basicConfig(level=logging.INFO)
WEB = Path(__file__).parent / "web"
templates = Jinja2Templates(directory=WEB / "templates")
# Version static URLs by content, so a phone never keeps running last week's script after a deploy.
ASSET_V = hashlib.sha256(b"".join(p.read_bytes() for p in sorted((WEB / "static").iterdir()))).hexdigest()[:8]
templates.env.globals["asset_v"] = ASSET_V

chat_limiter = RateLimiter(limit=40, window_seconds=600)
lookup_limiter = RateLimiter(limit=10, window_seconds=600)
dedupe = DailyDedupe()


def _pack_ids(cfg) -> list[str]:
    ids = [p.strip() for p in cfg.packs.split(",") if p.strip()]
    return [cfg.pack, *[p for p in ids if p != cfg.pack]]  # default first


async def build_engine() -> Engine:
    cfg = get_settings()
    if cfg.store == "postgres":
        from app.store.postgres import PostgresStore

        store = await PostgresStore.connect(cfg.database_url)
    else:
        store = MemoryStore()
    return Engine(
        store=store,
        extractor=get_extractor(cfg.extract_mode, cfg.openai_model, cfg.openai_api_key,
                                cfg.openai_reasoning_effort),
        pack=[get_pack(pid, cfg.allow_unverified) for pid in _pack_ids(cfg)],
        ref_secret=cfg.ref_code_secret,
        extract_timeout=cfg.extract_timeout_seconds,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_settings()
    problems = cfg.production_problems() if cfg.railway_environment else []
    # Secrets and the verified gate are hard stops. The rest are loud warnings so a
    # demo deployment (mock extractor, in-memory store) is still possible on purpose.
    fatal = [p for p in problems if p.startswith(("REF_CODE_SECRET", "ANALYST_PASSWORD", "ALLOW_UNVERIFIED", "TELEGRAM_"))]
    for p in problems:
        logging.getLogger(__name__).warning("DEPLOYMENT CHECK: %s", p)
    if fatal:
        raise RuntimeError("Refusing to start: " + "; ".join(fatal))
    app.state.engine = await build_engine()
    app.state.transcriber = (make_openai_transcriber(cfg.openai_api_key, cfg.openai_transcribe_model)
                             if cfg.voice_enabled and cfg.openai_api_key else None)
    app.state.telegram, app.state.telegram_secret, bot_api = None, cfg.telegram_webhook_secret, None
    if cfg.telegram_bot_token and cfg.telegram_webhook_secret:
        bot_api = HttpBotAPI(cfg.telegram_bot_token)
        app.state.telegram = TelegramAdapter(app.state.engine, bot_api, demo_mode=cfg.demo_mode)
        await app.state.telegram.publish_commands()
    if get_settings().demo_mode:
        n = await seed(app.state.engine.store, list(app.state.engine.packs.values()))
        logging.getLogger(__name__).info("Seeded %s sample reports", n)

    async def purge_loop():
        while True:  # expired sessions may still hold an unfinished story; do not keep them
            await asyncio.sleep(600)
            await app.state.engine.store.purge_expired_sessions()
            if app.state.telegram:
                app.state.telegram.prune()

    task = asyncio.create_task(purge_loop())
    yield
    task.cancel()
    if bot_api:
        await bot_api.close()
    if hasattr(app.state.engine.store, "close"):
        await app.state.engine.store.close()


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
    if request.url.path.startswith(("/analyst", "/api", "/telegram")):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    return "User-agent: *\nDisallow: /analyst\nDisallow: /api\nDisallow: /telegram\n"


class ChatIn(BaseModel):
    session_id: str | None = None
    channel: Channel = "web"
    pack: str | None = Field(default=None, max_length=32)  # only read when a conversation starts
    text: str = Field(default="", max_length=4000)


class CodeIn(BaseModel):
    ref_code: str = Field(max_length=32)


@app.get("/", response_class=HTMLResponse)
async def chat_page(request: Request, pack: str | None = None, engine: Engine = Depends(engine_of)):
    current = engine.pack_for(pack)
    return templates.TemplateResponse(request, "chat.html", {
        "pack": current, "packs": list(engine.packs.values()), "demo_mode": get_settings().demo_mode,
        "voice": getattr(request.app.state, "transcriber", None) is not None})


@app.post("/api/chat", response_model=EngineReply)
async def chat(body: ChatIn, request: Request, engine: Engine = Depends(engine_of)):
    ip = client_ip(request)
    if not chat_limiter.allow(ip):
        raise HTTPException(429, "Too many messages. Please wait a few minutes.")
    try:
        return await engine.handle_message(body.session_id, body.channel, body.text,
                                           dedupe_key=dedupe.key(ip), pack_id=body.pack)
    except Exception:
        # Database down, a bug, anything. The reporter must still see what to do if someone is
        # in danger, in words from the pack, never a bare "Internal Server Error".
        logging.getLogger(__name__).exception("chat failed")
        raise HTTPException(503, engine.pack_for(body.pack).message("E.unavailable")) from None


voice_limiter = RateLimiter(limit=12, window_seconds=600)


@app.post("/api/transcribe")
async def transcribe(request: Request, pack: str | None = None, engine: Engine = Depends(engine_of)):
    """Speech to text for people who would rather talk than type. Returns the words to the
    reporter's own screen; nothing is sent to the bot until they press Send."""
    transcriber = getattr(request.app.state, "transcriber", None)
    if transcriber is None:
        raise HTTPException(404, "Voice notes are not switched on.")
    if not voice_limiter.allow(client_ip(request)):
        raise HTTPException(429, "Too many recordings. Please wait a few minutes, or type instead.")
    mime = request.headers.get("content-type", "audio/webm")
    if not mime.startswith("audio/"):
        raise HTTPException(415, "Send the recording as audio.")
    audio = await request.body()
    if not audio:
        raise HTTPException(400, "The recording was empty. Please try again.")
    if len(audio) > MAX_BYTES:
        raise HTTPException(413, "That recording is too long. Please keep it under a minute, or type instead.")
    current = engine.pack_for(pack)
    try:
        # The hint is vocabulary only: local words plus this pack's hospital names, so that
        # "Harmattan General" does not come back as "Harmadan General".
        hint = current.meta.get("transcription_hint", "") + " Hospitals: " + ", ".join(h.name for h in current.hospitals) + "."
        text = await transcriber(audio, mime, hint)
    except Exception as e:  # noqa: BLE001 - never leave the reporter with a stack trace
        logging.getLogger(__name__).error("Transcription failed (%s)", type(e).__name__)
        raise HTTPException(503, "I could not turn that into text. Please try again, or type instead.") from None
    finally:
        del audio  # held in memory for this request only; never written anywhere
    if not text:
        raise HTTPException(422, "I could not hear any words. Please try again, or type instead.")
    return {"text": text[:4000]}


class ForgetIn(BaseModel):
    session_id: str = Field(max_length=64)


@app.post("/api/chat/forget", status_code=204)
async def forget(body: ForgetIn, engine: Engine = Depends(engine_of)):
    """Quick exit and "start again": delete the unfinished conversation now, not at expiry.
    A finished report is untouched; it holds no story and the session no longer links to it."""
    await engine.store.delete_session(body.session_id)


_telegram_tasks: set[asyncio.Task] = set()


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """Telegram adapter, webhook side. Answers at once and does the work afterwards, so Telegram
    never times out waiting on extraction and sends the same story again."""
    adapter = getattr(request.app.state, "telegram", None)
    if adapter is None:
        raise HTTPException(404)
    expected = getattr(request.app.state, "telegram_secret", "")
    sent = request.headers.get("x-telegram-bot-api-secret-token", "")
    if not expected or not secrets.compare_digest(sent.encode(), expected.encode()):
        raise HTTPException(403)
    try:
        update = await request.json()
    except ValueError:
        return {"ok": True}
    if isinstance(update, dict):
        task = asyncio.create_task(adapter.handle_update(update))
        _telegram_tasks.add(task)                      # keep a reference until it finishes
        task.add_done_callback(_telegram_tasks.discard)
    return {"ok": True}

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


def analyst_auth(creds: HTTPBasicCredentials = Depends(basic)) -> str:
    """Returns the username typed at the prompt. The password is shared in this proof of concept,
    so the name is a courtesy, not proof; it still makes the audit log readable."""
    expected = get_settings().analyst_password.encode()
    if not secrets.compare_digest(creds.password.encode(), expected):
        raise HTTPException(401, "Wrong password", headers={"WWW-Authenticate": 'Basic realm="Analyst"'})
    return creds.username[:60] or "unknown"


def _pack_of_hospital(engine: Engine, hospital_id: str):
    for p in engine.packs.values():
        if any(h.id == hospital_id for h in p.hospitals):
            return p
    raise HTTPException(404, "No pattern above the threshold for that hospital and category.")


def _pattern_or_404(rows: list[dict], hospital_id: str, category: str) -> dict:
    for p in rows:
        if p["hospital_id"] == hospital_id and p["category"] == category:
            return p
    # Below-threshold groups are indistinguishable from groups that do not exist.
    raise HTTPException(404, "No pattern above the threshold for that hospital and category.")


@app.get("/analyst", response_class=HTMLResponse, dependencies=[Depends(analyst_auth)])
async def analyst_home(request: Request, pack: str | None = None, engine: Engine = Depends(engine_of)):
    current = engine.pack_for(pack)
    reports = [r for r in await engine.store.list_reports() if r.pack == current.id]
    rows = A.patterns(reports, current)
    for p in rows:
        rs = A.pattern_reports(reports, p["hospital_id"], p["category"])
        p["trend"] = A.trend(rs)["word"]
        p["spark"] = A.sparkline_svg(A.weekly_counts(rs))
    return templates.TemplateResponse(request, "analyst.html", {
        "pack": current, "packs": list(engine.packs.values()),
        "org_name": current.org_name, "patterns": rows, "threshold": A.THRESHOLD,
        "window": A.WINDOW_DAYS, "sample": any(p["includes_sample_data"] for p in rows),
        "held_back": len(A.review_queue(reports, current))})


@app.get("/analyst/content", response_class=HTMLResponse, dependencies=[Depends(analyst_auth)])
async def analyst_content(request: Request, pack: str | None = None, engine: Engine = Depends(engine_of)):
    """Every law, number and contact the bot could send, with what to check it against and who
    has signed it off. Read-only: sign-off happens in the pack files so git is the audit trail."""
    current = engine.pack_for(pack)
    rows = current.gated_entries()
    return templates.TemplateResponse(request, "content.html", {
        "pack": current, "packs": list(engine.packs.values()), "rows": rows,
        "done": sum(r["verified"] for r in rows), "allow_unverified": current.allow_unverified})


@app.get("/analyst/pattern/{hospital_id}/{category}", response_class=HTMLResponse,
         dependencies=[Depends(analyst_auth)])
async def analyst_pattern(hospital_id: str, category: str, request: Request,
                          engine: Engine = Depends(engine_of)):
    pack = _pack_of_hospital(engine, hospital_id)
    reports = await engine.store.list_reports()
    pattern = _pattern_or_404(A.patterns(reports, pack), hospital_id, category)
    rs = A.pattern_reports(reports, hospital_id, category)
    return templates.TemplateResponse(request, "pattern.html", {
        "pack": pack, "org_name": pack.org_name, "p": pattern, "reports": rs, "slices": A.slices(rs),
        "brief": A.brief(pattern, pack), "trend": A.trend(rs),
        "spark": A.sparkline_svg(A.weekly_counts(rs), width=260, height=48),
        "posts": [{"text": t, "url": A.intent_url(t), "chars": len(t)} for t in A.thread(pattern, rs, pack)],
        "target": pack.meta.get("target", {})})


@app.get("/analyst/card/{hospital_id}/{category}.svg", dependencies=[Depends(analyst_auth)])
async def analyst_card(hospital_id: str, category: str, engine: Engine = Depends(engine_of)):
    pack = _pack_of_hospital(engine, hospital_id)
    rows = A.patterns(await engine.store.list_reports(), pack)
    svg = A.card_svg(_pattern_or_404(rows, hospital_id, category), pack)
    return Response(svg, media_type="image/svg+xml")


@app.get("/analyst/brief/{hospital_id}/{category}.md", response_class=PlainTextResponse,
         dependencies=[Depends(analyst_auth)])
async def analyst_brief(hospital_id: str, category: str, engine: Engine = Depends(engine_of)):
    pack = _pack_of_hospital(engine, hospital_id)
    rows = A.patterns(await engine.store.list_reports(), pack)
    text = A.brief(_pattern_or_404(rows, hospital_id, category), pack)
    name = f"brief-{hospital_id}-{category}.md"
    return PlainTextResponse(text, media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/analyst/patterns.csv", dependencies=[Depends(analyst_auth)])
async def analyst_patterns_csv(pack: str | None = None, engine: Engine = Depends(engine_of)):
    text = A.patterns_csv(A.patterns(await engine.store.list_reports(), engine.pack_for(pack)))
    return PlainTextResponse(text, media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="patterns.csv"'})


@app.get("/analyst/facets.csv", dependencies=[Depends(analyst_auth)])
async def analyst_facets_csv(pack: str | None = None, engine: Engine = Depends(engine_of)):
    text = A.facets_csv(await engine.store.list_reports(), engine.pack_for(pack))
    return PlainTextResponse(text, media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="facets.csv"'})


@app.get("/analyst/review", response_class=HTMLResponse)
async def analyst_review(request: Request, pack: str | None = None, engine: Engine = Depends(engine_of),
                         _: str = Depends(analyst_auth)):
    current = engine.pack_for(pack)
    rows = A.review_queue(await engine.store.list_reports(), current)
    return templates.TemplateResponse(request, "review.html", {
        "pack": current, "packs": list(engine.packs.values()), "rows": rows,
        "hospitals": [h for h in current.hospitals if h.facility_type != "private"],
        "audit": await engine.store.list_audit(50)})


@app.post("/analyst/reports/{report_id}/{action}")
async def analyst_set_credibility(report_id: str, action: str, request: Request,
                                  engine: Engine = Depends(engine_of), actor: str = Depends(analyst_auth)):
    new = {"exclude": "excluded", "accept": "ok", "hold": "review"}.get(action)
    report = await engine.store.get_report(report_id)
    if new is None or report is None:
        raise HTTPException(404)
    before, detail = report.credibility, ""

    # "accept" from the review queue can also resolve an unrecognised hospital name.
    form = await request.form()
    hospital_id = str(form.get("hospital_id") or "")
    if action == "accept" and hospital_id:
        pack = engine.pack_for(report.pack)
        match = next((h for h in pack.hospitals if h.id == hospital_id), None)
        if match is None:
            raise HTTPException(400, "Unknown hospital for this pack")
        detail = f"hospital set to {match.name}"
        report.hospital_id, report.hospital_name_raw = match.id, None
    if action == "accept" and report.hospital_id is None:
        raise HTTPException(400, "Choose a hospital before counting this report")

    report.credibility = new  # type: ignore[assignment]
    await engine.store.save_report(report)
    await engine.store.add_audit(AuditEntry(actor=actor, action=action, report_id=report.id,
                                            before=before, after=new, detail=detail))
    back = request.headers.get("referer") or "/analyst"
    return RedirectResponse(back, status_code=303)


@app.get("/healthz")
async def healthz():
    return {"ok": True}
