"""Voice notes: speech in, text out, audio gone.

The recording is held in memory for the length of one request, sent to the transcription
service, and discarded. It is never written to disk, a database or a log. The text comes back
to the reporter's own screen to check and edit before anything is sent to the bot.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

MAX_BYTES = 1_500_000          # about 90 seconds of phone-quality audio
EXT = {"audio/webm": "webm", "audio/mp4": "mp4", "audio/ogg": "ogg", "audio/mpeg": "mp3",
       "audio/wav": "wav", "audio/x-m4a": "m4a", "audio/aac": "m4a"}

# (audio bytes, mime type, vocabulary hint) -> text
Transcriber = Callable[[bytes, str, str], Awaitable[str]]


def make_openai_transcriber(api_key: str, model: str) -> Transcriber:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, timeout=30.0)

    async def transcribe(audio: bytes, mime: str, hint: str) -> str:
        ext = EXT.get(mime.split(";")[0].strip().lower(), "webm")
        result = await client.audio.transcriptions.create(
            model=model, file=(f"note.{ext}", audio, mime), prompt=hint, response_format="text")
        return (result if isinstance(result, str) else getattr(result, "text", "")).strip()

    return transcribe
