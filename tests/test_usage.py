"""Token spend and model, recorded for every AI call."""
import asyncio
import os

os.environ.update(EXTRACT_MODE="mock", STORE="memory", ALLOW_UNVERIFIED="true", DEMO_MODE="true",
                  ANALYST_PASSWORD="pw")

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from app import analyst as A
from app.engine.extract import make_llm_extractor
from app.engine.models import AiCall
from app.main import app

AUTH = ("analyst", "pw")
STORY = [{"role": "user", "text": "A nurse slapped me last week"}]


async def test_every_extraction_reports_its_model_and_tokens():
    seen: list[AiCall] = []
    extract = make_llm_extractor(TestModel(), on_call=seen.append)
    await extract(STORY)
    (call,) = seen
    assert call.purpose == "extract" and call.model == "test" and call.ok
    assert call.input_tokens > 0 and call.output_tokens > 0 and call.requests >= 1 and call.latency_ms >= 0


async def test_a_failed_call_is_still_counted_and_still_fails():
    def boom(messages, info):
        raise RuntimeError("provider is down")

    seen: list[AiCall] = []
    extract = make_llm_extractor(FunctionModel(boom), on_call=seen.append)
    with pytest.raises(RuntimeError):
        await extract(STORY)
    assert len(seen) == 1 and seen[0].ok is False and seen[0].input_tokens == 0


async def test_a_call_cut_off_by_the_timeout_is_counted_too():
    async def slow(messages, info):
        await asyncio.sleep(5)

    seen: list[AiCall] = []
    extract = make_llm_extractor(FunctionModel(slow), on_call=seen.append)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(extract(STORY), 0.05)
    assert len(seen) == 1 and seen[0].ok is False


async def test_a_broken_recorder_never_breaks_the_reply():
    def broken(call):
        raise RuntimeError("database is down")

    ex = await make_llm_extractor(TestModel(), on_call=broken)(STORY)
    assert ex is not None


def test_usage_adds_up_by_day_model_and_purpose():
    calls = [AiCall(purpose="extract", model="m1", input_tokens=100, output_tokens=10, requests=1, latency_ms=1000),
             AiCall(purpose="extract", model="m1", input_tokens=300, output_tokens=30, requests=2, latency_ms=3000),
             AiCall(purpose="extract", model="m1", ok=False, latency_ms=15000),
             AiCall(purpose="transcribe", model="m2", input_tokens=50, output_tokens=5, requests=1)]
    rows = A.usage(calls)
    top = next(r for r in rows if r["model"] == "m1")
    assert (top["calls"], top["failed"], top["input_tokens"], top["output_tokens"], top["requests"]) == (3, 1, 400, 40, 3)
    assert top["avg_latency_ms"] == 2000                                   # failures do not skew the average
    assert {r["purpose"] for r in rows} == {"extract", "transcribe"}


def test_the_usage_page_is_for_analysts_only_and_shows_the_totals():
    with TestClient(app) as c:
        store = c.app.state.engine.store
        asyncio.run(store.add_ai_call(AiCall(purpose="extract", model="openai:gpt-5-mini",
                                             input_tokens=1234, output_tokens=56, requests=1)))
        assert c.get("/analyst/usage").status_code == 401
        page = c.get("/analyst/usage", auth=AUTH)
        assert page.status_code == 200 and "openai:gpt-5-mini" in page.text and "1,234" in page.text
        assert "/analyst/usage" in c.get("/analyst", auth=AUTH).text
