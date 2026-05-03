from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import aiosqlite

from omnibot.schemas.events import Event

Subscriber = Callable[[Event], Awaitable[None] | None]


class EventBus:
    """Append-only SQLite event log with lightweight pub/sub."""

    def __init__(self, db_path: str | Path = "omnibot.db"):
        self.db_path = Path(db_path)
        self._subscribers: list[Subscriber] = []
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    source TEXT NOT NULL,
                    task_id TEXT,
                    causal_parent_ids TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    audit_hash TEXT NOT NULL
                )
                """
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(type)")
            await db.commit()

    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.append(subscriber)

    async def emit(
        self,
        event_type: str,
        *,
        actor: str = "system",
        source: str = "omnibot",
        task_id: str | None = None,
        causal_parent_ids: list[str] | None = None,
        payload: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> Event:
        event = Event(
            type=event_type,  # type: ignore[arg-type]
            actor=actor,
            source=source,
            task_id=task_id,
            causal_parent_ids=causal_parent_ids or [],
            payload=payload or {},
            provenance=provenance or {},
        )
        event.audit_hash = self._hash_event(event)

        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO events (
                        event_id, type, timestamp, actor, source, task_id,
                        causal_parent_ids, payload, provenance, audit_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.type,
                        event.timestamp,
                        event.actor,
                        event.source,
                        event.task_id,
                        json.dumps(event.causal_parent_ids),
                        json.dumps(event.payload, default=str),
                        json.dumps(event.provenance, default=str),
                        event.audit_hash,
                    ),
                )
                await db.commit()

        for subscriber in list(self._subscribers):
            result = subscriber(event)
            if asyncio.iscoroutine(result):
                await result
        return event

    async def replay(
        self,
        *,
        task_id: str | None = None,
        limit: int = 200,
    ) -> list[Event]:
        query = "SELECT * FROM events"
        params: list[Any] = []
        if task_id:
            query += " WHERE task_id = ?"
            params.append(task_id)
        query += " ORDER BY sequence ASC LIMIT ?"
        params.append(limit)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(query, params)).fetchall()
        return [self._row_to_event(row) for row in rows]

    async def recent(self, limit: int = 50) -> list[Event]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (
                await db.execute("SELECT * FROM events ORDER BY sequence DESC LIMIT ?", (limit,))
            ).fetchall()
        return [self._row_to_event(row) for row in reversed(rows)]

    def _row_to_event(self, row: aiosqlite.Row) -> Event:
        return Event(
            event_id=row["event_id"],
            type=row["type"],
            timestamp=row["timestamp"],
            actor=row["actor"],
            source=row["source"],
            task_id=row["task_id"],
            causal_parent_ids=json.loads(row["causal_parent_ids"]),
            payload=json.loads(row["payload"]),
            provenance=json.loads(row["provenance"]),
            audit_hash=row["audit_hash"],
        )

    def _hash_event(self, event: Event) -> str:
        raw = event.model_dump(exclude={"audit_hash"})
        canonical = json.dumps(raw, sort_keys=True, default=str)
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
