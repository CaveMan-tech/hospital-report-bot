"""Postgres store (asyncpg). Works with Railway Postgres or any other Postgres.

The schema is applied at startup; every statement in db/schema.sql is idempotent.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg
from pydantic import BaseModel

from app.engine.models import Followup, Report, Session

SCHEMA = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


async def _init_connection(conn: asyncpg.Connection) -> None:
    # Let jsonb columns take and return plain Python dicts.
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


def _columns(model: BaseModel) -> dict[str, Any]:
    """Python-mode dump: datetimes stay datetimes, which is what asyncpg wants."""
    return model.model_dump(mode="python")


def _insert_sql(table: str, cols: list[str]) -> str:
    names = ", ".join(cols)
    params = ", ".join(f"${i}" for i in range(1, len(cols) + 1))
    return f"insert into {table} ({names}) values ({params})"  # column names come from our own models, never from user input


def _upsert_sql(table: str, cols: list[str]) -> str:
    updates = ", ".join(f"{c} = excluded.{c}" for c in cols if c != "id")
    return f"{_insert_sql(table, cols)} on conflict (id) do update set {updates}"


def _model(cls, record: asyncpg.Record | None):
    if record is None:
        return None
    data = dict(record)
    data["id"] = str(data["id"])
    if data.get("report_id") is not None:
        data["report_id"] = str(data["report_id"])
    return cls.model_validate(data)


class PostgresStore:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PostgresStore:
        if not dsn:
            raise RuntimeError("STORE=postgres needs DATABASE_URL")
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5, init=_init_connection)
        async with pool.acquire() as conn:
            await conn.execute(SCHEMA.read_text(encoding="utf-8"))
        return cls(pool)

    async def close(self) -> None:
        await self.pool.close()

    async def _write(self, table: str, model: BaseModel, upsert: bool) -> None:
        data = _columns(model)
        cols = list(data)
        sql = _upsert_sql(table, cols) if upsert else _insert_sql(table, cols)
        await self.pool.execute(sql, *data.values())

    # sessions
    async def create_session(self, session: Session) -> None:
        await self._write("sessions", session, upsert=False)

    async def get_session(self, session_id: str) -> Session | None:
        try:
            row = await self.pool.fetchrow("select * from sessions where id = $1", session_id)
        except asyncpg.DataError:  # not a uuid: a client sent a junk session id
            return None
        return _model(Session, row)

    async def save_session(self, session: Session) -> None:
        await self._write("sessions", session, upsert=True)

    async def purge_expired_sessions(self) -> int:
        result = await self.pool.execute("delete from sessions where expires_at < now()")
        return int(result.split()[-1])

    # reports
    async def create_report(self, report: Report) -> None:
        await self._write("reports", report, upsert=False)

    async def save_report(self, report: Report) -> None:
        await self._write("reports", report, upsert=True)

    async def get_report(self, report_id: str) -> Report | None:
        try:
            row = await self.pool.fetchrow("select * from reports where id = $1", report_id)
        except asyncpg.DataError:
            return None
        return _model(Report, row)

    async def get_report_by_ref(self, ref_code_hmac: str) -> Report | None:
        row = await self.pool.fetchrow("select * from reports where ref_code_hmac = $1", ref_code_hmac)
        return _model(Report, row)

    async def list_reports(self) -> list[Report]:
        since = datetime.now(UTC) - timedelta(days=120)
        rows = await self.pool.fetch(
            "select * from reports where created_at >= $1 order by created_at desc limit 20000", since)
        return [_model(Report, r) for r in rows]

    async def find_recent_duplicate(
        self, dedupe_key: str, hospital_id: str | None, category: str
    ) -> bool:
        since = datetime.now(UTC) - timedelta(hours=24)
        return await self.pool.fetchval(
            """select exists(
                 select 1 from reports
                 where dedupe_key = $1 and category = $2 and created_at >= $3
                   and hospital_id is not distinct from $4)""",
            dedupe_key, category, since, hospital_id)

    async def add_followup(self, followup: Followup) -> None:
        await self._write("followups", followup, upsert=False)
