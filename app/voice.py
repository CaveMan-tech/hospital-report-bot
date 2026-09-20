"""Voice notes: speech in, text out, audio gone.

The recording is held in memory for the length of one request, sent to the transcription
service, and discarded. It is never written to disk, a database or a log. The text comes back
to the reporter's own screen to check and edit before anything is sent to the bot.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from app.engine.extract import OnCall, report_call
from app.engine.models import AiCall

MAX_BYTES = 1_500_000          # about 90 seconds of phone-quality audio
EXT = {"audio/webm": "webm", "audio/mp4": "mp4", "audio/ogg": "ogg", "audio/mpeg": "mp3",
       "audio/wav": "wav", "audio/x-m4a": "m4a", "audio/aac": "m4a"}

# (audio bytes, mime type, vocabulary hint) -> text
Transcriber = Callable[[bytes, str, str], Awaitable[str]]


def make_openai_transcriber(api_key: str, model: str, on_call: OnCall | None = None) -> Transcriber:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, timeout=30.0)

    async def transcribe(audio: bytes, mime: str, hint: str) -> str:
        ext = EXT.get(mime.split(";")[0].strip().lower(), "webm")
        started, ok, usage = time.monotonic(), False, None
        try:
            # json, not text: the plain-text response carries no token counts.
            result = await client.audio.transcriptions.create(
                model=model, file=(f"note.{ext}", audio, mime), prompt=hint, response_format="json")
            ok, usage = True, getattr(result, "usage", None)
            return (result if isinstance(result, str) else getattr(result, "text", "")).strip()
        finally:
            report_call(on_call, AiCall(
                purpose="transcribe", model=f"openai:{model}", ok=ok, requests=1,
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                latency_ms=int((time.monotonic() - started) * 1000)))

    return transcribe
