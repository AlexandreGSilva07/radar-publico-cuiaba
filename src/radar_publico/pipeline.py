"""Orquestração explícita de uma atualização completa do produto."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from radar_publico.agencies import AgencyDirectoryReport, enrich_agency_directory
from radar_publico.collect import Report, collect
from radar_publico.coverage import require_valid
from radar_publico.enrich import (
    EnrichmentReport,
    GeocodingReport,
    enrich_companies,
    geocode_company_postal_codes,
)
from radar_publico.http import PublicClient
from radar_publico.sources import load_manifest
from radar_publico.state import State
from radar_publico.transform import BuildReport, build_analytics


@dataclass(frozen=True)
class RefreshReport:
    cycle_id: str
    collections: tuple[Report, ...]
    analytics: BuildReport
    enrichment: EnrichmentReport | None
    agency_directory: AgencyDirectoryReport | None
    geocoding: GeocodingReport | None


def refresh(
    *,
    year: int,
    ops_path: Path,
    bronze_root: Path,
    analytics_path: Path,
    enrichment_path: Path,
    enrichment_limit: int = 20,
    agency_directory_limit: int = 50,
    geocoding_limit: int = 50,
    cycle_id: str | None = None,
    http: PublicClient | None = None,
) -> RefreshReport:
    """Executa a cadeia completa; transformação só ocorre após cobertura válida."""
    if enrichment_limit < 0 or agency_directory_limit < 0 or geocoding_limit < 0:
        raise ValueError("limites de enriquecimento não podem ser negativos")
    manifest = load_manifest()
    active_cycle = cycle_id or f"refresh-{year}-{uuid4()}"
    client = http or PublicClient()
    owns_client = http is None
    collections: list[Report] = []
    try:
        with State(ops_path) as state:
            for resource in manifest.resources:
                report = collect(
                    manifest=manifest,
                    resource_name=resource,
                    year=year,
                    state=state,
                    http=client,
                    bronze_root=bronze_root,
                    cycle_id=active_cycle,
                )
                require_valid(state, report.run_id)
                collections.append(report)
        analytics = build_analytics(
            ops_path=ops_path,
            bronze_root=bronze_root,
            output_path=analytics_path,
            year=year,
        )
        enrichment = (
            enrich_companies(
                analytics_path=analytics_path,
                cache_path=enrichment_path,
                http=client,
                limit=enrichment_limit,
            )
            if enrichment_limit
            else None
        )
        agency_directory = (
            enrich_agency_directory(
                cache_path=enrichment_path,
                http=client,
                limit=agency_directory_limit,
            )
            if agency_directory_limit
            else None
        )
        geocoding = (
            geocode_company_postal_codes(
                cache_path=enrichment_path,
                http=client,
                limit=geocoding_limit,
            )
            if geocoding_limit
            else None
        )
    finally:
        if owns_client:
            client.__exit__()
    return RefreshReport(
        active_cycle,
        tuple(collections),
        analytics,
        enrichment,
        agency_directory,
        geocoding,
    )
