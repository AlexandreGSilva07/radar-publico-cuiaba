"""Diretório oficial de unidades compradoras da Prefeitura de Cuiabá."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from importlib.resources import files
from pathlib import Path
from urllib.parse import urljoin, urlparse

import duckdb

from radar_publico.http import HttpError, PublicClient
from radar_publico.normalize import text

DIRECTORY_ROOT = "https://www.cuiaba.mt.gov.br"
DIRECTORY_INDEXES = (
    ("secretaria", f"{DIRECTORY_ROOT}/secretarias", "/secretarias/"),
    ("orgao", f"{DIRECTORY_ROOT}/orgaos", "/orgaos/"),
)


class AgencyDirectoryError(RuntimeError):
    """Fonte oficial de órgãos ausente ou incompatível."""


@dataclass(frozen=True)
class AgencyDirectoryCandidate:
    kind: str
    name: str
    source_url: str


@dataclass(frozen=True)
class AgencyDirectoryReport:
    discovered: int
    attempted: int
    saved: int
    failed: int
    cached: int


class _DirectoryIndexParser(HTMLParser):
    def __init__(self, kind: str, path_prefix: str) -> None:
        super().__init__(convert_charrefs=True)
        self.kind = kind
        self.path_prefix = path_prefix
        self.link: str | None = None
        self.capture_title = False
        self.title_parts: list[str] = []
        self.items: list[AgencyDirectoryCandidate] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "a":
            href = attributes.get("href") or ""
            if href.startswith(self.path_prefix) and href.count("/") == 2:
                self.link = urljoin(DIRECTORY_ROOT, href)
        if tag == "h3" and self.link:
            classes = (attributes.get("class") or "").split()
            if "secretary-link-title" in classes:
                self.capture_title = True
                self.title_parts = []

    def handle_data(self, data: str) -> None:
        if self.capture_title:
            self.title_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h3" and self.capture_title and self.link:
            name = text(" ".join(self.title_parts))
            if name:
                self.items.append(AgencyDirectoryCandidate(self.kind, name, self.link))
            self.capture_title = False
            self.title_parts = []
        elif tag == "a":
            self.link = None


class _AgencyDetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.capture_address = False
        self.address_parts: list[str] = []
        self.phones: list[str] = []
        self.emails: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "address" and not self.address_parts:
            self.capture_address = True
        if tag == "a":
            href = attributes.get("href") or ""
            if href.startswith("tel:"):
                value = "".join(character for character in href[4:] if character.isdigit())
                if value and value not in self.phones:
                    self.phones.append(value)
            elif href.startswith("mailto:"):
                value = href[7:].split("?", 1)[0].strip().casefold()
                if "@" in value and value not in self.emails:
                    self.emails.append(value)

    def handle_data(self, data: str) -> None:
        if self.capture_address:
            self.address_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "address" and self.capture_address:
            self.capture_address = False

    @property
    def address(self) -> str | None:
        return text(" ".join(self.address_parts))


def parse_directory_index(html: str, kind: str, path_prefix: str) -> list[AgencyDirectoryCandidate]:
    parser = _DirectoryIndexParser(kind, path_prefix)
    parser.feed(html)
    unique = {item.source_url: item for item in parser.items}
    return list(unique.values())


def parse_agency_detail(html: str) -> tuple[str | None, str | None, list[str], list[str]]:
    parser = _AgencyDetailParser()
    parser.feed(html)
    address = parser.address
    match = re.search(r"\b(\d{5})[-.\s]?(\d{3})\b", address or "")
    postal_code = "".join(match.groups()) if match else None
    return address, postal_code, parser.phones, parser.emails


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def enrich_agency_directory(
    *,
    cache_path: Path,
    http: PublicClient,
    limit: int = 50,
    max_age_days: int = 7,
    interval: float = 0.25,
) -> AgencyDirectoryReport:
    """Coleta contatos e endereços oficiais, sem perfis pessoais de gestores."""
    if limit < 1 or max_age_days < 0 or interval < 0:
        raise AgencyDirectoryError("limite, validade ou intervalo inválido")
    candidates: dict[str, AgencyDirectoryCandidate] = {}
    for kind, index_url, path_prefix in DIRECTORY_INDEXES:
        try:
            response = http.get_text(index_url)
        except HttpError as exc:
            raise AgencyDirectoryError(f"índice oficial indisponível: {kind}") from exc
        parsed = parse_directory_index(str(response.payload), kind, path_prefix)
        candidates.update({item.source_url: item for item in parsed})
    if not candidates:
        raise AgencyDirectoryError("diretório oficial sem unidades reconhecíveis")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(cache_path))
    schema = files("radar_publico").joinpath("migrations/005_agencies.sql").read_text()
    connection.execute(schema)
    threshold = _now() - timedelta(days=max_age_days)
    fresh = {
        str(row[0])
        for row in connection.execute(
            "SELECT source_url FROM agency_directory WHERE fetched_at >= ?", [threshold]
        ).fetchall()
    }
    attempted = saved = failed = 0
    try:
        for candidate in candidates.values():
            if candidate.source_url in fresh:
                continue
            if attempted >= limit:
                break
            attempted += 1
            try:
                response = http.get_text(candidate.source_url)
                body = response.content.decode("utf-8", errors="replace")
                address, postal_code, phones, emails = parse_agency_detail(body)
                slug = urlparse(candidate.source_url).path.rstrip("/").rsplit("/", 1)[-1]
                connection.execute(
                    "INSERT OR REPLACE INTO agency_directory VALUES (?,?,?,?,?,?,?,?,?,?)",
                    [
                        candidate.source_url,
                        candidate.kind,
                        slug,
                        candidate.name,
                        address,
                        postal_code,
                        json.dumps(phones, separators=(",", ":")),
                        json.dumps(emails, ensure_ascii=False, separators=(",", ":")),
                        hashlib.sha256(response.content).hexdigest(),
                        _now(),
                    ],
                )
                connection.execute(
                    "INSERT INTO agency_directory_attempt VALUES (?, ?, 'succeeded', ?, NULL)",
                    [candidate.source_url, _now(), response.status],
                )
                saved += 1
            except HttpError as exc:
                connection.execute(
                    "INSERT INTO agency_directory_attempt VALUES (?, ?, 'failed', ?, ?)",
                    [candidate.source_url, _now(), exc.status, exc.category],
                )
                failed += 1
            if interval and attempted < limit:
                time.sleep(interval)
    finally:
        connection.close()
    return AgencyDirectoryReport(len(candidates), attempted, saved, failed, len(fresh))
