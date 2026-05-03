from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import aiosqlite

from omnibot.schemas.events import MemoryItem


class Embedder:
    """Tiny wrapper: sentence-transformers when available, hash embedding otherwise."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", dims: int = 64):
        self.model_name = model_name
        self.dims = dims
        self._model = None
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(model_name)
        except Exception:
            self._model = None

    def embed(self, text: str) -> list[float]:
        if self._model is not None:
            vec = self._model.encode(text, normalize_embeddings=True)
            return [float(x) for x in vec.tolist()]

        vec = [0.0] * self.dims
        for word in re.findall(r"\w+", text.lower()):
            bucket = hash(word) % self.dims
            vec[bucket] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]


class MemoryFabric:
    def __init__(self, db_path: str | Path = "omnibot.db", embedder: Embedder | None = None):
        self.db_path = Path(db_path)
        self.embedder = embedder or Embedder()

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    memory_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_event_id TEXT NOT NULL,
                    task_id TEXT,
                    embedding TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL
                )
                """
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_memories_task ON memories(task_id)")
            await db.commit()

    async def remember(
        self,
        content: str,
        *,
        source_event_id: str,
        task_id: str | None = None,
        kind: str = "episodic",
        confidence: float = 0.7,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryItem:
        item = MemoryItem(
            kind=kind,  # type: ignore[arg-type]
            content=content,
            source_event_id=source_event_id,
            task_id=task_id,
            embedding=self.embedder.embed(content),
            confidence=confidence,
            metadata=metadata or {},
        )
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO memories (
                    memory_id, kind, content, source_event_id, task_id,
                    embedding, confidence, created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.memory_id,
                    item.kind,
                    item.content,
                    item.source_event_id,
                    item.task_id,
                    json.dumps(item.embedding),
                    item.confidence,
                    item.created_at,
                    json.dumps(item.metadata, default=str),
                ),
            )
            await db.commit()
        return item

    async def recall(self, query: str, limit: int = 5) -> list[MemoryItem]:
        qvec = self.embedder.embed(query)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute("SELECT * FROM memories")).fetchall()

        scored: list[tuple[float, MemoryItem]] = []
        for row in rows:
            item = MemoryItem(
                memory_id=row["memory_id"],
                kind=row["kind"],
                content=row["content"],
                source_event_id=row["source_event_id"],
                task_id=row["task_id"],
                embedding=json.loads(row["embedding"]),
                confidence=row["confidence"],
                created_at=row["created_at"],
                metadata=json.loads(row["metadata"]),
            )
            scored.append((self._cosine(qvec, item.embedding), item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for score, item in scored[:limit] if score > 0]

    async def recent(self, limit: int = 20) -> list[MemoryItem]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (
                await db.execute("SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,))
            ).fetchall()
        return [
            MemoryItem(
                memory_id=row["memory_id"],
                kind=row["kind"],
                content=row["content"],
                source_event_id=row["source_event_id"],
                task_id=row["task_id"],
                embedding=json.loads(row["embedding"]),
                confidence=row["confidence"],
                created_at=row["created_at"],
                metadata=json.loads(row["metadata"]),
            )
            for row in rows
        ]

    def _cosine(self, a: list[float], b: list[float]) -> float:
        if not a or not b:
            return 0.0
        n = min(len(a), len(b))
        dot = sum(a[i] * b[i] for i in range(n))
        an = math.sqrt(sum(x * x for x in a[:n])) or 1.0
        bn = math.sqrt(sum(x * x for x in b[:n])) or 1.0
        return dot / (an * bn)
