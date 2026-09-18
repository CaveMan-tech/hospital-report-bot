import json
import os
from pathlib import Path

os.environ.update(EXTRACT_MODE="mock", STORE="memory", ALLOW_UNVERIFIED="true", DEMO_MODE="true",
                  ANALYST_PASSWORD="pw")

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app, client_ip

ROOT = Path(__file__).resolve().parents[1]
GOOD = {"ref_code_secret": "x" * 32, "analyst_password": "a-long-password", "allow_unverified": False,
        "extract_mode": "llm", "store": "postgres"}


def test_good_production_config_has_no_problems():
    assert Settings(**GOOD).production_problems() == []


def test_each_unsafe_setting_is_caught():
    for override, needle in [
        ({"ref_code_secret": "dev-only-secret"}, "REF_CODE_SECRET"),
        ({"analyst_password": "demo"}, "ANALYST_PASSWORD"),
        ({"allow_unverified": True}, "ALLOW_UNVERIFIED"),
        ({"extract_mode": "mock"}, "EXTRACT_MODE"),
        ({"store": "memory"}, "STORE"),
    ]:
        problems = Settings(**{**GOOD, **override}).production_problems()
        assert len(problems) == 1 and needle in problems[0]


def test_start_command_never_logs_ip_addresses_and_runs_one_worker():
    cmd = json.loads((ROOT / "railway.json").read_text())["deploy"]["startCommand"]
    assert "--no-access-log" in cmd            # access logs would record every reporter's IP
    assert "--workers 1" in cmd                # rate limiter and daily dedupe salt live in memory
    assert "--no-access-log" in (ROOT / "Dockerfile").read_text()


def test_client_ip_ignores_spoofable_left_most_forwarded_entry():
    class R:
        client = None
        def __init__(self, h): self.headers = h
    assert client_ip(R({"x-forwarded-for": "6.6.6.6, 10.0.0.1, 41.58.1.2"})) == "41.58.1.2"
    assert client_ip(R({"x-real-ip": "41.58.1.2", "x-forwarded-for": "6.6.6.6"})) == "41.58.1.2"
    assert client_ip(R({})) == "unknown"


def test_privacy_headers_and_robots():
    with TestClient(app) as c:
        r = c.post("/api/chat", json={"text": ""})
        assert r.headers["cache-control"] == "no-store" and "noindex" in r.headers["x-robots-tag"]
        assert c.get("/").headers["referrer-policy"] == "no-referrer"
        assert "Disallow: /analyst" in c.get("/robots.txt").text
