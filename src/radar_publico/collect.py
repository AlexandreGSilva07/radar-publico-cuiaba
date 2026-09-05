"""Coletor paginado genérico dirigido pelo manifesto."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from radar_publico.bronze import BronzeStore
from radar_publico.http import PublicClient
from radar_publico.sources import Manifest
from radar_publico.state import State


class CollectionError(RuntimeError):
    """Resposta ou cobertura incompatível com o contrato da fonte."""


@dataclass(frozen=True)
class Report:
    run_id: str
    cycle_id: str
    resource: str
    year: int
    status: str
    collected_pages: int
    expected_pages: int | None
    collected_records: int
    expected_records: int | None


def parse_page(payload: Any) -> tuple[list[dict[str, Any]], int]:
    envelope = payload[0] if isinstance(payload, list) and len(payload) == 1 else payload
    if not isinstance(envelope, dict):
        raise CollectionError("envelope inválido")
    records = envelope.get("registers")
    total = envelope.get("totalRecords")
    if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
        raise CollectionError("registers inválido")
    if not isinstance(total, int) or total < 0:
        raise CollectionError("totalRecords inválido")
    if total == 0 and records:
        raise CollectionError("totalRecords zero com registros")
    return records, total


def collect(
    *,
    manifest: Manifest,
    resource_name: str,
    year: int,
    state: State,
    http: PublicClient,
    bronze_root: Path,
    cycle_id: str | None = None,
    max_pages: int | None = None,
) -> Report:
    if resource_name not in manifest.resources:
        raise CollectionError("recurso não declarado")
    if max_pages is not None and max_pages < 1:
        raise CollectionError("max_pages deve ser positivo")
    active_cycle = cycle_id or str(uuid.uuid4())
    run = state.start_run(resource_name, year, active_cycle)
    stored = state.db.execute(
        "SELECT expected_pages,collected_pages,expected_records,collected_records,status "
        "FROM coverage WHERE run_id=?",
        [run.run_id],
    ).fetchone()
    if run.status == "succeeded" and stored:
        expected_pages_saved = None if stored[0] is None else int(str(stored[0]))
        collected_pages_saved = int(str(stored[1]))
        expected_records_saved = None if stored[2] is None else int(str(stored[2]))
        collected_records_saved = int(str(stored[3]))
        return Report(
            run.run_id,
            active_cycle,
            resource_name,
            year,
            str(stored[4]),
            collected_pages_saved,
            expected_pages_saved,
            collected_records_saved,
            expected_records_saved,
        )

    definition = manifest.resources[resource_name]
    page = state.next_page(run.run_id)
    collected_pages, collected_records, known_total = state.progress(run.run_id)
    expected_pages = (
        None if known_total is None else max(1, math.ceil(known_total / manifest.page_size))
    )
    pages_this_call = 0
    store = BronzeStore(bronze_root)
    while max_pages is None or pages_this_call < max_pages:
        request_id = state.start_request(run.run_id, page)
        try:
            response = http.post_form(
                manifest.url(resource_name, "query"),
                definition.form(year=year, page=page, page_size=manifest.page_size),
            )
            bronze = store.write(resource_name, year, page, response.content)
            object_id = state.record_object(bronze.content_hash, bronze.relative_path)
            records, total = parse_page(response.payload)
            if known_total is not None and total != known_total:
                raise CollectionError("totalRecords variou entre páginas")
            known_total = total
            expected_pages = max(1, math.ceil(total / manifest.page_size))
            state.complete_page(
                request_id, object_id=object_id, record_count=len(records), total_records=total
            )
        except Exception:
            state.fail_request(request_id)
            state.finish_run(run.run_id, "failed")
            raise
        collected_pages += 1
        collected_records += len(records)
        pages_this_call += 1
        if collected_records == total:
            if collected_pages != expected_pages:
                raise CollectionError("páginas não reconciliadas")
            status = "empty" if total == 0 else "complete"
            state.set_coverage(
                run.run_id,
                expected_pages=expected_pages,
                collected_pages=collected_pages,
                expected_records=total,
                collected_records=collected_records,
                status=status,
            )
            state.finish_run(run.run_id, "succeeded")
            return Report(
                run.run_id,
                active_cycle,
                resource_name,
                year,
                status,
                collected_pages,
                expected_pages,
                collected_records,
                total,
            )
        if not records or collected_records > total:
            raise CollectionError("registros não reconciliados")
        page += 1

    state.set_coverage(
        run.run_id,
        expected_pages=expected_pages,
        collected_pages=collected_pages,
        expected_records=known_total,
        collected_records=collected_records,
        status="partial",
    )
    state.finish_run(run.run_id, "partial")
    return Report(
        run.run_id,
        active_cycle,
        resource_name,
        year,
        "partial",
        collected_pages,
        expected_pages,
        collected_records,
        known_total,
    )
