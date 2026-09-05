"""Manifesto tipado das fontes públicas."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class ManifestError(ValueError):
    """Configuração de fonte inválida."""


class Resource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_endpoint: str
    filter_endpoint: str
    year_field: str
    natural_key: str
    document_field: str | None = None

    @field_validator("query_endpoint", "filter_endpoint")
    @classmethod
    def relative_endpoint(cls, value: str) -> str:
        if not value or "/" in value or "://" in value:
            raise ValueError("endpoint deve ser relativo e sem barras")
        return value

    def form(self, *, year: int, page: int, page_size: int) -> dict[str, str]:
        pagination = {
            "currentPage": page,
            "recordsPerPage": page_size,
            "totalRecords": 0,
            "columnOrder": "",
        }
        return {
            "pagination": json.dumps(pagination, separators=(",", ":")),
            "filters": json.dumps({self.year_field: str(year)}, separators=(",", ":")),
        }


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    source_name: str
    base_url: str
    page_size: int = Field(gt=0, le=1000)
    resources: dict[str, Resource]

    @field_validator("base_url")
    @classmethod
    def valid_base_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("base_url deve ser HTTPS absoluta e sem query")
        return value.rstrip("/")

    @field_validator("resources")
    @classmethod
    def required_resources(cls, value: dict[str, Resource]) -> dict[str, Resource]:
        missing = {"contratos", "licitacoes", "despesas"} - set(value)
        if missing:
            raise ValueError(f"recursos obrigatórios ausentes: {', '.join(sorted(missing))}")
        return value

    def url(self, resource: str, kind: str) -> str:
        try:
            definition = self.resources[resource]
        except KeyError as exc:
            raise ManifestError(f"recurso desconhecido: {resource}") from exc
        endpoint = definition.query_endpoint if kind == "query" else definition.filter_endpoint
        if kind not in {"query", "filter"}:
            raise ManifestError(f"tipo de endpoint desconhecido: {kind}")
        return f"{self.base_url}/{endpoint}"


def load_manifest(path: Path = Path("config/sources/cuiaba.yml")) -> Manifest:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return Manifest.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise ManifestError(f"manifesto inválido: {exc}") from exc
