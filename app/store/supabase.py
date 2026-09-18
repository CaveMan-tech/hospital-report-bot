"""Supabase (Postgres) store. Server-side only, using the service role key."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from supabase import Client, create_client

from app.engine.models import Followup, Report, Session


def _row(model) -> dict[str, Any]:
    return model.model_dump(mode="json")


class SupabaseStore:
    def __init__(self, url: str, service_key: str):
        if not url or not service_key:
            raise RuntimeError("STORE=supabase needs SUPABASE_URL and SUPABASE_SERVICE_KEY")
        self.db: Client = create_client(url, service_key)

    async def _run(self, query):
        # supabase-py is synchronous; keep the event loop free.
        return await asyncio.to_thread(query.execute)

    # sessions
    async def create_session(self, session: Session) -> None:
        await self._run(self.db.table("sessions").insert(_row(session)))

    async def get_session(self, session_id: str) -> Session | None:
        res = await self._run(self.db.table("sessions").select("*").eq("id", session_id).limit(1))
        return Session.model_validate(res.data[0]) if res.data else None

    async def save_session(self, session: Session) -> None:
        await self._run(self.db.table("sessions").upsert(_row(session)))

    async def purge_expired_sessions(self) -> int:
        now = datetime.now(UTC).isoformat()
        res = await self._run(self.db.table("sessions").delete().lt("expires_at", now))
        return len(res.data or [])

    # reports
    async def create_report(self, report: Report) -> None:
        await self._run(self.db.table("reports").insert(_row(report)))

    async def save_report(self, report: Report) -> None:
        await self._run(self.db.table("reports").upsert(_row(report)))

    async def get_report(self, report_id: str) -> Report | None:
        res = await self._run(self.db.table("reports").select("*").eq("id", report_id).limit(1))
        return Report.model_validate(res.data[0]) if res.data else None

    async def get_report_by_ref(self, ref_code_hmac: str) -> Report | None:
        res = await self._run(
            self.db.table("reports").select("*").eq("ref_code_hmac", ref_code_hmac).limit(1))
        return Report.model_validate(res.data[0]) if res.data else None

    async def list_reports(self) -> list[Report]:
        since = (datetime.now(UTC) - timedelta(days=120)).isoformat()
        res = await self._run(
            self.db.table("reports").select("*").gte("created_at", since).limit(10000))
        return [Report.model_validate(r) for r in res.data or []]

    async def find_recent_duplicate(
        self, dedupe_key: str, hospital_id: str | None, category: str
    ) -> bool:
        since = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
        q = (self.db.table("reports").select("id").eq("dedupe_key", dedupe_key)
             .eq("category", category).gte("created_at", since).limit(1))
        q = q.eq("hospital_id", hospital_id) if hospital_id else q.is_("hospital_id", "null")
        return bool((await self._run(q)).data)

    async def add_followup(self, followup: Followup) -> None:
        await self._run(self.db.table("followups").insert(_row(followup)))
