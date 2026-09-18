"""In-memory store for local development and tests. No external services needed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.engine.models import Followup, Report, Session


class MemoryStore:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.reports: dict[str, Report] = {}
        self.followups: list[Followup] = []

    async def create_session(self, session: Session) -> None:
        self.sessions[session.id] = session.model_copy(deep=True)

    async def get_session(self, session_id: str) -> Session | None:
        s = self.sessions.get(session_id)
        return s.model_copy(deep=True) if s else None

    async def save_session(self, session: Session) -> None:
        self.sessions[session.id] = session.model_copy(deep=True)

    async def purge_expired_sessions(self) -> int:
        dead = [sid for sid, s in self.sessions.items() if s.expired]
        for sid in dead:
            del self.sessions[sid]
        return len(dead)

    async def create_report(self, report: Report) -> None:
        self.reports[report.id] = report.model_copy(deep=True)

    async def save_report(self, report: Report) -> None:
        self.reports[report.id] = report.model_copy(deep=True)

    async def get_report(self, report_id: str) -> Report | None:
        r = self.reports.get(report_id)
        return r.model_copy(deep=True) if r else None

    async def get_report_by_ref(self, ref_code_hmac: str) -> Report | None:
        for r in self.reports.values():
            if r.ref_code_hmac == ref_code_hmac:
                return r.model_copy(deep=True)
        return None

    async def list_reports(self) -> list[Report]:
        return [r.model_copy(deep=True) for r in self.reports.values()]

    async def find_recent_duplicate(
        self, dedupe_key: str, hospital_id: str | None, category: str
    ) -> bool:
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        return any(
            r.dedupe_key == dedupe_key
            and r.hospital_id == hospital_id
            and r.category == category
            and r.created_at >= cutoff
            for r in self.reports.values()
        )

    async def add_followup(self, followup: Followup) -> None:
        self.followups.append(followup.model_copy(deep=True))
