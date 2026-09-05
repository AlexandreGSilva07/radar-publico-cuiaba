"""Estado operacional idempotente da coleta."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

import duckdb


class StateError(RuntimeError):
    """Operação incompatível com o estado persistido."""


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class Run:
    run_id: str
    cycle_id: str
    resource: str
    year: int
    status: str


class State:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection: duckdb.DuckDBPyConnection | None = None

    def __enter__(self) -> State:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = duckdb.connect(str(self.path))
        sql = files("radar_publico").joinpath("migrations/001_ops.sql").read_text()
        self.connection.execute(sql)
        self.connection.execute("INSERT OR IGNORE INTO schema_migration VALUES (1, ?)", [_now()])
        return self

    def __exit__(self, *_: object) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    @property
    def db(self) -> duckdb.DuckDBPyConnection:
        if self.connection is None:
            raise StateError("estado não está aberto")
        return self.connection

    def start_run(self, resource: str, year: int, cycle_id: str) -> Run:
        key = hashlib.sha256(f"{resource}:{year}:{cycle_id}".encode()).hexdigest()
        row = self.db.execute("SELECT run_id, status FROM run WHERE run_key = ?", [key]).fetchone()
        if row:
            return Run(str(row[0]), cycle_id, resource, year, str(row[1]))
        run_id = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO run VALUES (?, ?, ?, ?, ?, 'running', ?, NULL)",
            [run_id, key, cycle_id, resource, year, _now()],
        )
        return Run(run_id, cycle_id, resource, year, "running")

    def start_request(self, run_id: str, page: int) -> str:
        row = self.db.execute(
            "SELECT request_id FROM request WHERE run_id = ? AND page = ?", [run_id, page]
        ).fetchone()
        if row:
            request_id = str(row[0])
            self.db.execute(
                "UPDATE request SET status='running', finished_at=NULL WHERE request_id=?",
                [request_id],
            )
            return request_id
        request_id = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO request VALUES (?, ?, ?, 'running', NULL, NULL, NULL)",
            [request_id, run_id, page],
        )
        return request_id

    def complete_page(
        self, request_id: str, *, object_id: str, record_count: int, total_records: int
    ) -> None:
        self.db.execute("BEGIN TRANSACTION")
        try:
            self.db.execute(
                "UPDATE bronze_reference SET is_current=false WHERE request_id=?", [request_id]
            )
            self.db.execute(
                "INSERT INTO bronze_reference VALUES (?, ?, ?, true, ?)",
                [str(uuid.uuid4()), request_id, object_id, _now()],
            )
            self.db.execute(
                "UPDATE request SET status='succeeded', record_count=?, total_records=?, "
                "finished_at=? WHERE request_id=?",
                [record_count, total_records, _now(), request_id],
            )
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def fail_request(self, request_id: str) -> None:
        self.db.execute(
            "UPDATE request SET status='failed', finished_at=? WHERE request_id=?",
            [_now(), request_id],
        )

    def finish_run(self, run_id: str, status: str) -> None:
        if status not in {"succeeded", "failed", "partial"}:
            raise StateError("status final inválido")
        self.db.execute(
            "UPDATE run SET status=?, finished_at=? WHERE run_id=?", [status, _now(), run_id]
        )

    def next_page(self, run_id: str) -> int:
        rows = self.db.execute(
            "SELECT page, status FROM request WHERE run_id=? ORDER BY page", [run_id]
        ).fetchall()
        expected = 0
        for page, status in rows:
            if int(page) != expected or status != "succeeded":
                break
            expected += 1
        return expected

    def progress(self, run_id: str) -> tuple[int, int, int | None]:
        row = self.db.execute(
            "SELECT count(*), coalesce(sum(record_count),0), max(total_records) "
            "FROM request WHERE run_id=? AND status='succeeded'",
            [run_id],
        ).fetchone()
        assert row is not None
        return int(row[0]), int(row[1]), None if row[2] is None else int(row[2])

    def record_object(self, content_hash: str, storage_path: str) -> str:
        row = self.db.execute(
            "SELECT object_id FROM bronze_object WHERE content_hash=?", [content_hash]
        ).fetchone()
        if row:
            return str(row[0])
        object_id = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO bronze_object VALUES (?, ?, ?, ?)",
            [object_id, content_hash, storage_path, _now()],
        )
        return object_id

    def set_coverage(
        self,
        run_id: str,
        *,
        expected_pages: int | None,
        collected_pages: int,
        expected_records: int | None,
        collected_records: int,
        status: str,
    ) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO coverage VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                run_id,
                expected_pages,
                collected_pages,
                expected_records,
                collected_records,
                status,
                _now(),
            ],
        )
