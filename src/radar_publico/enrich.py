"""Enriquecimento empresarial seletivo, cacheado e sem dados de contato/QSA."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from importlib.resources import files
from pathlib import Path
from typing import Any

import duckdb

from radar_publico.http import HttpError, PublicClient
from radar_publico.normalize import NormalizeError, source_date, text, valid_cnpj

BRASIL_API_CNPJ = "https://brasilapi.com.br/api/cnpj/v1"


class EnrichmentError(RuntimeError):
    """Configuração local ou resposta empresarial incompatível."""


@dataclass(frozen=True)
class EnrichmentReport:
    candidates: int
    attempted: int
    enriched: int
    failed: int
    cached: int


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _decimal(value: object) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise EnrichmentError("capital social inválido") from exc


def _cnae_json(value: object) -> str:
    if not isinstance(value, list):
        return "[]"
    allowed = []
    for item in value:
        if isinstance(item, dict):
            allowed.append(
                {
                    "code": text(item.get("codigo")),
                    "description": text(item.get("descricao")),
                }
            )
    return json.dumps(allowed, ensure_ascii=False, separators=(",", ":"))


def _profile(payload: Any, requested_cnpj: str, source_url: str) -> tuple[object, ...]:
    if not isinstance(payload, dict):
        raise EnrichmentError("resposta CNPJ não é objeto")
    returned_cnpj = "".join(
        character for character in str(payload.get("cnpj", "")) if character.isdigit()
    )
    if returned_cnpj != requested_cnpj or not valid_cnpj(returned_cnpj):
        raise EnrichmentError("CNPJ da resposta diverge da consulta")
    try:
        status_on = source_date(payload.get("data_situacao_cadastral"))
        opened_on = source_date(payload.get("data_inicio_atividade"))
    except NormalizeError as exc:
        raise EnrichmentError(str(exc)) from exc
    headquarters_code = payload.get("identificador_matriz_filial")
    headquarters = (
        {1: "MATRIZ", 2: "FILIAL"}.get(headquarters_code)
        if isinstance(headquarters_code, int)
        else None
    )
    return (
        returned_cnpj,
        returned_cnpj[:8],
        text(payload.get("razao_social")),
        text(payload.get("nome_fantasia")),
        text(payload.get("descricao_situacao_cadastral")),
        status_on,
        opened_on,
        headquarters,
        text(payload.get("porte")),
        text(payload.get("natureza_juridica")),
        _decimal(payload.get("capital_social")),
        text(payload.get("cnae_fiscal")),
        text(payload.get("cnae_fiscal_descricao")),
        _cnae_json(payload.get("cnaes_secundarios")),
        text(payload.get("uf")),
        text(payload.get("municipio")),
        text(payload.get("bairro")),
        text(payload.get("logradouro")),
        text(payload.get("numero")),
        text(payload.get("complemento")),
        text(payload.get("cep")),
        payload.get("opcao_pelo_simples")
        if isinstance(payload.get("opcao_pelo_simples"), bool)
        else None,
        payload.get("opcao_pelo_mei") if isinstance(payload.get("opcao_pelo_mei"), bool) else None,
        source_url,
        _now(),
    )


def _candidates(analytics_path: Path) -> list[str]:
    if not analytics_path.exists():
        raise EnrichmentError(f"banco analítico não encontrado: {analytics_path}")
    connection = duckdb.connect(str(analytics_path), read_only=True)
    try:
        rows = connection.execute(
            """
            SELECT cnpj
            FROM gold_suppliers
            WHERE cnpj IS NOT NULL
            ORDER BY (contract_count > 0) DESC, contract_value DESC, paid_value DESC, cnpj
            """
        ).fetchall()
    finally:
        connection.close()
    result = [str(row[0]) for row in rows]
    if any(not valid_cnpj(cnpj) for cnpj in result):
        raise EnrichmentError("camada Gold contém CNPJ inválido")
    return result


def enrich_companies(
    *,
    analytics_path: Path,
    cache_path: Path,
    http: PublicClient,
    limit: int,
    max_age_days: int = 30,
    interval: float = 0.2,
) -> EnrichmentReport:
    """Consulta apenas CNPJs novos/expirados e grava somente campos permitidos."""
    if limit < 1 or max_age_days < 0 or interval < 0:
        raise EnrichmentError("limite, validade ou intervalo inválido")
    candidates = _candidates(analytics_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(cache_path))
    schema = files("radar_publico").joinpath("migrations/004_enrichment.sql").read_text()
    connection.execute(schema)
    threshold = _now() - timedelta(days=max_age_days)
    fresh = {
        str(row[0])
        for row in connection.execute(
            "SELECT cnpj FROM company_profile WHERE fetched_at >= ?", [threshold]
        ).fetchall()
    }
    attempted = enriched = failed = 0
    try:
        for cnpj in candidates:
            if cnpj in fresh:
                continue
            if attempted >= limit:
                break
            attempted += 1
            source_url = f"{BRASIL_API_CNPJ}/{cnpj}"
            try:
                response = http.get(source_url)
                profile = _profile(response.payload, cnpj, source_url)
                connection.execute(
                    "INSERT OR REPLACE INTO company_profile "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    profile,
                )
                connection.execute(
                    "INSERT INTO enrichment_attempt VALUES (?, ?, 'succeeded', ?, NULL)",
                    [cnpj, _now(), response.status],
                )
                enriched += 1
            except (EnrichmentError, HttpError) as exc:
                status = exc.status if isinstance(exc, HttpError) else None
                reason = exc.category if isinstance(exc, HttpError) else str(exc)
                connection.execute(
                    "INSERT INTO enrichment_attempt VALUES (?, ?, 'failed', ?, ?)",
                    [cnpj, _now(), status, reason[:100]],
                )
                failed += 1
            if interval and attempted < limit:
                time.sleep(interval)
    finally:
        connection.close()
    return EnrichmentReport(len(candidates), attempted, enriched, failed, len(fresh))
