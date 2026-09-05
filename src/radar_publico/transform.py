"""Materialização atômica das páginas Bronze na camada Silver."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

import duckdb

from radar_publico.collect import parse_page
from radar_publico.normalize import document, money, search_text, source_date, text


class TransformError(RuntimeError):
    """Snapshot Bronze incompleto ou registro incompatível com o contrato Silver."""


@dataclass(frozen=True)
class Snapshot:
    resource: str
    year: int
    run_id: str
    expected_records: int
    objects: tuple[tuple[int, str, Path], ...]


@dataclass(frozen=True)
class BuildReport:
    output_path: Path
    year: int
    counts: dict[str, int]
    rejected: dict[str, int]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _required_int(record: dict[str, Any], key: str) -> int:
    value = record.get(key)
    if value is None or isinstance(value, bool):
        raise TransformError(f"{key} inválido")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise TransformError(f"{key} inválido") from exc


def _positive_int(record: dict[str, Any], key: str) -> int | None:
    value = _required_int(record, key)
    return value if value > 0 else None


def _snapshots(
    ops_path: Path, bronze_root: Path, resources: tuple[str, ...], year: int
) -> list[Snapshot]:
    if not ops_path.exists():
        raise TransformError(f"estado operacional não encontrado: {ops_path}")
    root = bronze_root.resolve()
    connection = duckdb.connect(str(ops_path), read_only=True)
    snapshots: list[Snapshot] = []
    try:
        for resource in resources:
            run = connection.execute(
                """
                SELECT r.run_id, c.expected_records, c.collected_pages
                FROM run r JOIN coverage c ON c.run_id=r.run_id
                WHERE r.resource=? AND r.year=? AND r.status='succeeded'
                  AND c.status IN ('complete', 'empty')
                  AND c.expected_records=c.collected_records
                  AND c.expected_pages=c.collected_pages
                ORDER BY r.finished_at DESC, r.started_at DESC
                LIMIT 1
                """,
                [resource, year],
            ).fetchone()
            if run is None:
                raise TransformError(f"snapshot completo ausente: {resource}/{year}")
            run_id, expected_records, collected_pages = str(run[0]), int(run[1]), int(run[2])
            rows = connection.execute(
                """
                SELECT q.page, o.content_hash, o.storage_path
                FROM request q
                JOIN bronze_reference b ON b.request_id=q.request_id AND b.is_current
                JOIN bronze_object o ON o.object_id=b.object_id
                WHERE q.run_id=? AND q.status='succeeded'
                ORDER BY q.page
                """,
                [run_id],
            ).fetchall()
            if len(rows) != collected_pages:
                raise TransformError(f"referências Bronze incompletas: {resource}/{year}")
            objects: list[tuple[int, str, Path]] = []
            for page, content_hash, storage_path in rows:
                path = (root / str(storage_path)).resolve()
                if root not in path.parents:
                    raise TransformError("referência Bronze escapou da raiz")
                objects.append((int(page), str(content_hash), path))
            snapshots.append(
                Snapshot(resource, year, run_id, expected_records, tuple(objects))
            )
    finally:
        connection.close()
    return snapshots


def _records(snapshot: Snapshot) -> list[tuple[dict[str, Any], str]]:
    result: list[tuple[dict[str, Any], str]] = []
    for expected_page, (page, content_hash, path) in enumerate(snapshot.objects):
        if page != expected_page:
            raise TransformError(f"sequência de páginas inválida: {snapshot.resource}")
        try:
            with gzip.open(path, "rb") as source:
                payload = source.read()
        except (OSError, FileNotFoundError) as exc:
            raise TransformError(f"objeto Bronze ilegível: {path}") from exc
        if hashlib.sha256(payload).hexdigest() != content_hash:
            raise TransformError(f"hash Bronze divergente: {path.name}")
        try:
            page_records, total = parse_page(json.loads(payload))
        except (json.JSONDecodeError, ValueError) as exc:
            raise TransformError(f"JSON Bronze inválido: {path.name}") from exc
        if total != snapshot.expected_records:
            raise TransformError(f"total Bronze divergente: {snapshot.resource}")
        result.extend((record, content_hash) for record in page_records)
    if len(result) != snapshot.expected_records:
        raise TransformError(f"quantidade Bronze divergente: {snapshot.resource}")
    return result


def _contract(record: dict[str, Any], run_id: str, source_hash: str) -> tuple[object, ...]:
    document_type, cnpj = document(record.get("ContratoFornecedorDoc"))
    return (
        _required_int(record, "ContratoId"),
        text(record.get("ContratoNumero")),
        _required_int(record, "ContratoAno"),
        text(record.get("ContratoDsc")),
        search_text(record.get("ContratoDsc")),
        text(record.get("ContratoOrgao")),
        text(record.get("ContratoFornecedorRazao")),
        text(record.get("ContratoFornecedorNome")),
        document_type,
        cnpj,
        text(record.get("ContratoStatus")),
        text(record.get("ContratoStatusDsc")),
        source_date(record.get("ContratoDataAssinatura")),
        source_date(record.get("ContratoDataIni")),
        source_date(record.get("ContratoDataFim")),
        text(record.get("ContratoTipoNome")),
        text(record.get("ContratoClassificacao")),
        _positive_int(record, "ContratoLicitacaoId"),
        text(record.get("ContratoLicitacaoNumero")),
        _positive_int(record, "ContratoLicitacaoAno"),
        text(record.get("ContratoLicitacaoModalidade")),
        money(record.get("ContratoValor")),
        money(record.get("ContratoValorAtual")),
        bool(record.get("ContratoPossuiDocumento")),
        run_id,
        source_hash,
    )


def _procurement(record: dict[str, Any], run_id: str, source_hash: str) -> tuple[object, ...]:
    return (
        _required_int(record, "LicitacaoId"),
        text(record.get("LicitacaoNumero")),
        _required_int(record, "LicitacaoAno"),
        text(record.get("LicitacaoObjeto")),
        search_text(record.get("LicitacaoObjeto")),
        text(record.get("LicitacaoOrgaoNome")),
        text(record.get("LicitacaoModalidadeNome")),
        text(record.get("LicitacaoSituacao")),
        source_date(record.get("LicitacaoData")),
        source_date(record.get("LicitacaoDataSessao")),
        source_date(record.get("LicitacaoDataAbtProposta")),
        money(record.get("LicitacaoValorEstimado")),
        money(record.get("LicitacaoValorHomologado")),
        text(record.get("LicitacaoFornVencedores")),
        text(record.get("LicitacaoFornVencedoresRazao")),
        bool(record.get("LicitacaoPossuiDocumento")),
        run_id,
        source_hash,
    )


def _expense(
    record: dict[str, Any], run_id: str, source_hash: str, year: int
) -> tuple[object, ...]:
    document_type, cnpj = document(record.get("DespesaCredorDoc"))
    name = text(record.get("DespesaCredorNome"))
    legal_name = text(record.get("DespesaCredorRazao"))
    return (
        year,
        _required_int(record, "DespesaCredorId"),
        name,
        legal_name,
        search_text(f"{name or ''} {legal_name or ''}"),
        document_type,
        cnpj,
        money(record.get("DespesaEmpenho")),
        money(record.get("DespesaLiquidacao")),
        money(record.get("DespesaPagamento")),
        run_id,
        source_hash,
    )


def _insert_resource(
    connection: duckdb.DuckDBPyConnection,
    snapshot: Snapshot,
    table: str,
    placeholders: int,
    converter: Callable[[dict[str, Any], str, str], tuple[object, ...]],
) -> tuple[int, int]:
    rows: list[tuple[object, ...]] = []
    rejections: list[tuple[object, ...]] = []
    source_records = _records(snapshot)
    doc_counts = {"cnpj": 0, "cpf": 0, "invalid": 0}
    seen_keys: set[object] = set()
    for index, (record, source_hash) in enumerate(source_records):
        raw_document = (
            record.get("ContratoFornecedorDoc")
            if snapshot.resource == "contratos"
            else record.get("DespesaCredorDoc")
        )
        if snapshot.resource != "licitacoes":
            doc_type, _ = document(raw_document)
            if doc_type in doc_counts:
                doc_counts[doc_type] += 1
        try:
            converted = converter(record, snapshot.run_id, source_hash)
            natural_key: object = (
                converted[:2] if snapshot.resource == "despesas" else converted[0]
            )
            if natural_key in seen_keys:
                raise TransformError("chave natural duplicada no snapshot")
            seen_keys.add(natural_key)
            rows.append(converted)
        except (TransformError, TypeError, ValueError) as exc:
            rejections.append(
                (snapshot.resource, snapshot.year, index, str(exc)[:300], source_hash)
            )
    if rows:
        connection.executemany(
            f"INSERT INTO {table} VALUES ({','.join('?' for _ in range(placeholders))})", rows
        )
    if rejections:
        connection.executemany("INSERT INTO transform_rejections VALUES (?,?,?,?,?)", rejections)
    connection.execute(
        "INSERT INTO data_quality VALUES (?,?,?,?,?,?,?,?)",
        [
            snapshot.resource,
            snapshot.year,
            len(source_records),
            len(rows),
            len(rejections),
            doc_counts["cnpj"],
            doc_counts["cpf"],
            doc_counts["invalid"],
        ],
    )
    return len(rows), len(rejections)


def build_analytics(
    *,
    ops_path: Path,
    bronze_root: Path,
    output_path: Path,
    year: int,
) -> BuildReport:
    """Reconstrói um snapshot analítico completo e o publica por troca atômica."""
    resources = ("contratos", "licitacoes", "despesas")
    snapshots = _snapshots(ops_path, bronze_root, resources, year)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".analytics-", suffix=".duckdb", dir=output_path.parent
    )
    os.close(descriptor)
    os.unlink(temporary_name)
    temporary_path = Path(temporary_name)
    counts: dict[str, int] = {}
    rejected: dict[str, int] = {}
    connection: duckdb.DuckDBPyConnection | None = None
    try:
        connection = duckdb.connect(str(temporary_path))
        schema = files("radar_publico").joinpath("migrations/002_analytics.sql").read_text()
        connection.execute(schema)
        for snapshot in snapshots:
            if snapshot.resource == "contratos":
                accepted, failures = _insert_resource(
                    connection, snapshot, "silver_contracts", 26, _contract
                )
            elif snapshot.resource == "licitacoes":
                accepted, failures = _insert_resource(
                    connection, snapshot, "silver_procurements", 18, _procurement
                )
            else:
                accepted, failures = _insert_resource(
                    connection,
                    snapshot,
                    "silver_expenses",
                    12,
                    lambda record, run_id, source_hash: _expense(
                        record, run_id, source_hash, snapshot.year
                    ),
                )
            counts[snapshot.resource] = accepted
            rejected[snapshot.resource] = failures
        connection.executemany(
            "INSERT INTO analytics_metadata VALUES (?,?)",
            [("schema_version", "3"), ("source_year", str(year)), ("built_at", _now())],
        )
        gold = files("radar_publico").joinpath("migrations/003_gold.sql").read_text()
        connection.execute(gold)
        connection.execute("CHECKPOINT")
        connection.close()
        connection = None
        os.replace(temporary_path, output_path)
    except Exception:
        if connection is not None:
            connection.close()
        temporary_path.unlink(missing_ok=True)
        raise
    return BuildReport(output_path, year, counts, rejected)
