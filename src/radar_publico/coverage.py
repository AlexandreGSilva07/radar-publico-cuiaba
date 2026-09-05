"""Relatórios e gates de cobertura."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from radar_publico.state import State, StateError


@dataclass(frozen=True)
class Coverage:
    run_id: str
    resource: str
    year: int
    status: str
    collected_pages: int
    expected_pages: int | None
    collected_records: int
    expected_records: int | None
    updated_at: str | None
    valid: bool

    def dict(self) -> dict[str, Any]:
        return asdict(self)


def reports(state: State, run_id: str | None = None) -> list[Coverage]:
    predicate = "WHERE r.run_id=?" if run_id else ""
    params = [run_id] if run_id else []
    rows = state.db.execute(
        f"""SELECT r.run_id,r.resource,r.year,c.status,c.collected_pages,c.expected_pages,
        c.collected_records,c.expected_records,c.updated_at
        FROM run r LEFT JOIN coverage c ON c.run_id=r.run_id {predicate}
        ORDER BY r.started_at DESC""",
        params,
    ).fetchall()
    result = []
    for row in rows:
        status = "unverified" if row[3] is None else str(row[3])
        collected_pages = 0 if row[4] is None else int(row[4])
        expected_pages = None if row[5] is None else int(row[5])
        collected_records = 0 if row[6] is None else int(row[6])
        expected_records = None if row[7] is None else int(row[7])
        valid = status in {"complete", "empty"} and expected_pages is not None
        valid = valid and collected_pages == expected_pages
        valid = valid and collected_records == expected_records
        if status == "empty":
            valid = valid and expected_pages == 1 and expected_records == 0
        if status == "complete":
            valid = valid and expected_records is not None and expected_records > 0
        result.append(
            Coverage(
                str(row[0]),
                str(row[1]),
                int(row[2]),
                status,
                collected_pages,
                expected_pages,
                collected_records,
                expected_records,
                None if row[8] is None else str(row[8]),
                valid,
            )
        )
    return result


def require_valid(state: State, run_id: str) -> Coverage:
    found = reports(state, run_id)
    if not found:
        raise StateError("run desconhecido")
    if not found[0].valid:
        raise StateError("cobertura incompleta ou inconsistente")
    return found[0]
