"""Enriquecimento empresarial e geográfico seletivo, cacheado e sem QSA."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import duckdb

from radar_publico.http import HttpError, PublicClient
from radar_publico.normalize import NormalizeError, source_date, text, valid_cnpj

BRASIL_API_CNPJ = "https://brasilapi.com.br/api/cnpj/v1"
BRASIL_API_CEP = "https://brasilapi.com.br/api/cep/v2"
NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"


class EnrichmentError(RuntimeError):
    """Configuração local ou resposta empresarial incompatível."""


@dataclass(frozen=True)
class EnrichmentReport:
    candidates: int
    attempted: int
    enriched: int
    failed: int
    cached: int


@dataclass(frozen=True)
class GeocodingReport:
    candidates: int
    attempted: int
    geocoded: int
    missing_coordinates: int
    failed: int
    cached: int


@dataclass(frozen=True)
class AddressGeocodingReport:
    candidates: int
    attempted: int
    geocoded: int
    not_found: int
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


def _phone(value: object) -> str | None:
    digits = "".join(character for character in str(value or "") if character.isdigit())
    return digits if len(digits) in {10, 11} else None


def _email(value: object) -> str | None:
    result = text(value)
    return result.casefold() if result and "@" in result else None


def _postal_code(value: object) -> str | None:
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if not digits or len(digits) > 8:
        return None
    return digits.zfill(8)


def _positive_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = int(str(value))
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _latest_tax_regime(value: object) -> tuple[str | None, int | None]:
    if not isinstance(value, list):
        return None, None
    options: list[tuple[int, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        year = _positive_int(item.get("ano"))
        regime = text(item.get("forma_de_tributacao"))
        if year is not None and regime is not None:
            options.append((year, regime))
    if not options:
        return None, None
    year, regime = max(options, key=lambda item: item[0])
    return regime, year


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
    tax_regime, tax_regime_year = _latest_tax_regime(payload.get("regime_tributario"))
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
        _postal_code(payload.get("cep")),
        _phone(payload.get("ddd_telefone_1")),
        _phone(payload.get("ddd_telefone_2")),
        _email(payload.get("email")),
        tax_regime,
        tax_regime_year,
        _positive_int(payload.get("codigo_municipio_ibge")),
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
    interval: float = 1.0,
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
                    """
                    INSERT OR REPLACE INTO company_profile(
                      cnpj, cnpj_root, legal_name, trade_name, registration_status, status_on,
                      opened_on, headquarters_type, company_size, legal_nature, share_capital,
                      primary_cnae, primary_cnae_description, secondary_cnaes_json, state, city,
                      district, street, street_number, address_extra, postal_code, phone_primary,
                      phone_secondary, email, tax_regime, tax_regime_year, municipality_ibge,
                      simples, mei, source_url, fetched_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
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


def _coordinate(value: object, minimum: float, maximum: float) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        result = float(str(value))
    except (TypeError, ValueError) as exc:
        raise EnrichmentError("coordenada inválida") from exc
    if not minimum <= result <= maximum:
        raise EnrichmentError("coordenada fora do intervalo")
    return result


def _location(payload: Any, requested_postal_code: str, source_url: str) -> tuple[object, ...]:
    if not isinstance(payload, dict):
        raise EnrichmentError("resposta CEP não é objeto")
    returned_postal_code = _postal_code(payload.get("cep"))
    if returned_postal_code != requested_postal_code:
        raise EnrichmentError("CEP da resposta diverge da consulta")
    location = payload.get("location")
    coordinates = location.get("coordinates") if isinstance(location, dict) else None
    coordinates = coordinates if isinstance(coordinates, dict) else {}
    longitude = _coordinate(coordinates.get("longitude"), -180, 180)
    latitude = _coordinate(coordinates.get("latitude"), -90, 90)
    if (longitude is None) != (latitude is None):
        longitude = latitude = None
    return (
        returned_postal_code,
        text(payload.get("state")),
        text(payload.get("city")),
        text(payload.get("neighborhood")),
        text(payload.get("street")),
        text(payload.get("service")),
        longitude,
        latitude,
        source_url,
        _now(),
    )


def geocode_company_postal_codes(
    *,
    cache_path: Path,
    http: PublicClient,
    limit: int,
    max_age_days: int = 180,
    interval: float = 1.0,
) -> GeocodingReport:
    """Resolve CEPs empresariais uma vez e mantém coordenadas em cache separado."""
    if limit < 1 or max_age_days < 0 or interval < 0:
        raise EnrichmentError("limite, validade ou intervalo inválido")
    if not cache_path.exists():
        raise EnrichmentError(f"cache empresarial não encontrado: {cache_path}")
    connection = duckdb.connect(str(cache_path))
    schema = files("radar_publico").joinpath("migrations/004_enrichment.sql").read_text()
    connection.execute(schema)
    agency_schema = files("radar_publico").joinpath("migrations/005_agencies.sql").read_text()
    connection.execute(agency_schema)
    threshold = _now() - timedelta(days=max_age_days)
    candidates = [
        str(row[0])
        for row in connection.execute(
            "SELECT postal_code FROM ("
            "SELECT postal_code, CASE WHEN upper(city) IN ('CUIABA', 'CUIABÁ') "
            "THEN 1 ELSE 2 END AS priority FROM company_profile "
            "WHERE postal_code IS NOT NULL UNION ALL "
            "SELECT postal_code, 0 AS priority FROM agency_directory "
            "WHERE postal_code IS NOT NULL"
            ") GROUP BY postal_code ORDER BY min(priority), postal_code"
        ).fetchall()
    ]
    fresh = {
        str(row[0])
        for row in connection.execute(
            "SELECT postal_code FROM company_location WHERE fetched_at >= ?", [threshold]
        ).fetchall()
    }
    attempted = geocoded = missing_coordinates = failed = 0
    try:
        for postal_code in candidates:
            if postal_code in fresh:
                continue
            if attempted >= limit:
                break
            attempted += 1
            source_url = f"{BRASIL_API_CEP}/{postal_code}"
            try:
                response = http.get(source_url)
                location = _location(response.payload, postal_code, source_url)
                connection.execute(
                    "INSERT OR REPLACE INTO company_location VALUES (?,?,?,?,?,?,?,?,?,?)",
                    location,
                )
                has_coordinates = location[6] is not None and location[7] is not None
                status = "succeeded" if has_coordinates else "missing_coordinates"
                connection.execute(
                    "INSERT INTO geocoding_attempt VALUES (?, ?, ?, ?, NULL)",
                    [postal_code, _now(), status, response.status],
                )
                if has_coordinates:
                    geocoded += 1
                else:
                    missing_coordinates += 1
            except (EnrichmentError, HttpError) as exc:
                status_code = exc.status if isinstance(exc, HttpError) else None
                reason = exc.category if isinstance(exc, HttpError) else str(exc)
                connection.execute(
                    "INSERT INTO geocoding_attempt VALUES (?, ?, 'failed', ?, ?)",
                    [postal_code, _now(), status_code, reason[:100]],
                )
                failed += 1
            if interval and attempted < limit:
                time.sleep(interval)
    finally:
        connection.close()
    return GeocodingReport(
        len(candidates), attempted, geocoded, missing_coordinates, failed, len(fresh)
    )


def _address_fingerprint(parts: tuple[object, ...]) -> str:
    normalized = "|".join(text(part) or "" for part in parts).casefold()
    return hashlib.sha256(normalized.encode()).hexdigest()


def _nominatim_url(
    *, street: str, street_number: str | None, city: str, state: str, postal_code: str | None
) -> str:
    parameters = {
        "street": " ".join(item for item in (street_number, street) if item),
        "city": city,
        "state": state,
        "country": "Brasil",
        "countrycodes": "br",
        "format": "jsonv2",
        "addressdetails": "1",
        "limit": "1",
    }
    if postal_code:
        parameters["postalcode"] = postal_code
    return f"{NOMINATIM_SEARCH}?{urlencode(parameters)}"


def _nominatim_location(payload: Any) -> tuple[str, str | None, str | None, float, float]:
    if not isinstance(payload, list):
        raise EnrichmentError("resposta Nominatim não é lista")
    if not payload:
        raise LookupError("endereço não encontrado")
    result = payload[0]
    if not isinstance(result, dict):
        raise EnrichmentError("resultado Nominatim não é objeto")
    raw_address = result.get("address")
    address: dict[str, Any] = raw_address if isinstance(raw_address, dict) else {}
    if str(address.get("country_code", "")).casefold() != "br":
        raise EnrichmentError("resultado Nominatim fora do Brasil")
    longitude = _coordinate(result.get("lon"), -180, 180)
    latitude = _coordinate(result.get("lat"), -90, 90)
    if longitude is None or latitude is None:
        raise EnrichmentError("resultado Nominatim sem coordenadas")
    result_type = text(result.get("addresstype") or result.get("type"))
    normalized_type = (result_type or "").casefold()
    if normalized_type in {"house", "building", "office", "commercial", "company", "shop"}:
        accuracy = "address"
    elif normalized_type in {"road", "residential", "pedestrian"}:
        accuracy = "street"
    elif normalized_type == "postcode":
        accuracy = "postal_code"
    else:
        accuracy = "locality"
    return accuracy, result_type, text(result.get("display_name")), longitude, latitude


def geocode_company_addresses(
    *,
    cache_path: Path,
    http: PublicClient,
    limit: int,
    analytics_path: Path | None = None,
    max_age_days: int = 365,
    interval: float = 1.1,
) -> AddressGeocodingReport:
    """Refina sedes por endereço, em série e com cache, usando Nominatim explicitamente."""
    if limit < 1 or max_age_days < 0 or interval < 0:
        raise EnrichmentError("limite, validade ou intervalo inválido")
    if not cache_path.exists():
        raise EnrichmentError(f"cache empresarial não encontrado: {cache_path}")
    connection = duckdb.connect(str(cache_path))
    schema = files("radar_publico").joinpath("migrations/004_enrichment.sql").read_text()
    connection.execute(schema)
    threshold = _now() - timedelta(days=max_age_days)
    rows = connection.execute(
        "SELECT cnpj, street, street_number, city, state, postal_code "
        "FROM company_profile WHERE street IS NOT NULL AND city IS NOT NULL "
        "AND state IS NOT NULL"
    ).fetchall()
    priorities: dict[str, int] = {}
    if analytics_path is not None and analytics_path.exists():
        analytics = duckdb.connect(str(analytics_path), read_only=True)
        try:
            priorities = {
                str(row[0]): index
                for index, row in enumerate(
                    analytics.execute(
                        "SELECT cnpj FROM gold_suppliers ORDER BY "
                        "greatest(coalesce(paid_value, 0), coalesce(contract_value, 0)) DESC, "
                        "cnpj"
                    ).fetchall()
                )
            }
        except duckdb.Error:
            priorities = {}
        finally:
            analytics.close()
    rows.sort(
        key=lambda row: (
            str(row[3]).upper() not in {"CUIABA", "CUIABÁ"},
            priorities.get(str(row[0]), len(priorities)),
            str(row[0]),
        )
    )
    candidates = [
        (
            str(row[0]),
            str(row[1]),
            text(row[2]),
            str(row[3]),
            str(row[4]),
            text(row[5]),
            _address_fingerprint(row[1:]),
        )
        for row in rows
    ]
    fresh = {
        (str(row[0]), str(row[1]))
        for row in connection.execute(
            "SELECT cnpj, address_fingerprint FROM company_address_location WHERE fetched_at >= ?",
            [threshold],
        ).fetchall()
    }
    attempted = geocoded = not_found = failed = 0
    try:
        for cnpj, street, number, city, state, postal_code, fingerprint in candidates:
            if (cnpj, fingerprint) in fresh:
                continue
            if attempted >= limit:
                break
            attempted += 1
            request_url = _nominatim_url(
                street=street,
                street_number=number,
                city=city,
                state=state,
                postal_code=postal_code,
            )
            try:
                response = http.get(request_url)
                accuracy, result_type, display_name, longitude, latitude = _nominatim_location(
                    response.payload
                )
                connection.execute(
                    "INSERT OR REPLACE INTO company_address_location VALUES (?,?,?,?,?,?,?,?,?,?)",
                    [
                        cnpj,
                        fingerprint,
                        "nominatim-openstreetmap",
                        accuracy,
                        result_type,
                        display_name,
                        longitude,
                        latitude,
                        NOMINATIM_SEARCH,
                        _now(),
                    ],
                )
                connection.execute(
                    "INSERT INTO address_geocoding_attempt VALUES (?, ?, 'succeeded', ?, NULL)",
                    [cnpj, _now(), response.status],
                )
                geocoded += 1
            except LookupError:
                connection.execute(
                    "INSERT OR REPLACE INTO company_address_location VALUES (?,?,?,?,?,?,?,?,?,?)",
                    [
                        cnpj,
                        fingerprint,
                        "nominatim-openstreetmap",
                        "not_found",
                        None,
                        None,
                        None,
                        None,
                        NOMINATIM_SEARCH,
                        _now(),
                    ],
                )
                connection.execute(
                    "INSERT INTO address_geocoding_attempt VALUES "
                    "(?, ?, 'not_found', 200, 'no_result')",
                    [cnpj, _now()],
                )
                not_found += 1
            except (EnrichmentError, HttpError) as exc:
                status_code = exc.status if isinstance(exc, HttpError) else None
                reason = exc.category if isinstance(exc, HttpError) else str(exc)
                connection.execute(
                    "INSERT INTO address_geocoding_attempt VALUES (?, ?, 'failed', ?, ?)",
                    [cnpj, _now(), status_code, reason[:100]],
                )
                failed += 1
            if interval and attempted < limit:
                time.sleep(interval)
    finally:
        connection.close()
    return AddressGeocodingReport(
        len(candidates), attempted, geocoded, not_found, failed, len(fresh)
    )
