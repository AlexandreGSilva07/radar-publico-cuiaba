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
from radar_publico.normalize import search_text, text

DIRECTORY_ROOT = "https://www.cuiaba.mt.gov.br"
DIRECTORY_INDEXES = (
    ("secretaria", f"{DIRECTORY_ROOT}/secretarias", "/secretarias/"),
    ("orgao", f"{DIRECTORY_ROOT}/orgaos", "/orgaos/"),
)

AGENCY_DIRECTORY_ALIASES: dict[str, tuple[str, ...]] = {
    "educacao cultura esporte e lazer": ("educacao", "cultura", "esportes-e-lazer"),
    "meio ambiente desenvolvimento e planejamento urbano": (
        "meio-ambiente-e-desenvolvimento-urbano",
        "planejamento-e-desenvolvimento-urbano",
    ),
    "turismo e desenvolvimento economico": (
        "secretaria-municipal-de-desenvolvimento-economico-trabalho-turismo-e-agricultura",
    ),
    "mobilidade urbana": ("mobilidade-urbana-e-seguranca-publica",),
    "agencia de fiscalizacao e regulacao dos servicos publicos delegados cuiaba regula": (
        "cuiaba-regula",
    ),
}


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


def canonical_agency_name(value: object) -> str:
    normalized = search_text(value)
    return re.sub(r"^secretaria municipal (?:de |da |do )?", "", normalized)


def directory_slugs_for(agency_name: object, directory: list[dict[str, object]]) -> tuple[str, ...]:
    """Resolve nomes somente por igualdade canônica ou alias manual versionado."""
    canonical = canonical_agency_name(agency_name)
    aliases = AGENCY_DIRECTORY_ALIASES.get(canonical)
    if aliases:
        return aliases
    exact = [
        str(item["slug"])
        for item in directory
        if canonical_agency_name(item.get("agency_name")) == canonical
    ]
    return tuple(exact)


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
        self.div_depth = 0
        self.contact_scope_depth: int | None = None
        self.saw_contact_scope = False
        self.capture_address = False
        self.address_parts: list[str] = []
        self.addresses: list[tuple[str, bool]] = []
        self.link_kind: str | None = None
        self.link_value = ""
        self.link_parts: list[str] = []
        self.link_in_scope = False
        self.all_phones: list[str] = []
        self.scoped_phones: list[str] = []
        self.all_emails: list[str] = []
        self.scoped_emails: list[str] = []
        self.location_url: str | None = None
        self.longitude: float | None = None
        self.latitude: float | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "div":
            self.div_depth += 1
            classes = (attributes.get("class") or "").split()
            if "component-sidebar" in classes and self.contact_scope_depth is None:
                self.contact_scope_depth = self.div_depth
                self.saw_contact_scope = True
        if tag == "address":
            self.capture_address = True
            self.address_parts = []
        if tag == "a":
            href = attributes.get("href") or ""
            location = re.search(
                r"google\.com/maps/(?:place|search)/(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)",
                href,
            )
            if self.contact_scope_depth is not None and location:
                latitude, longitude = map(float, location.groups())
                if -90 <= latitude <= 90 and -180 <= longitude <= 180:
                    self.location_url = href
                    self.longitude = longitude
                    self.latitude = latitude
            if href.startswith("tel:"):
                self.link_kind = "phone"
                self.link_value = href[4:]
                self.link_parts = []
                self.link_in_scope = self.contact_scope_depth is not None
            elif href.startswith("mailto:"):
                self.link_kind = "email"
                self.link_value = href[7:].split("?", 1)[0].strip().casefold()
                self.link_parts = []
                self.link_in_scope = self.contact_scope_depth is not None

    def handle_data(self, data: str) -> None:
        if self.capture_address:
            self.address_parts.append(data)
        if self.link_kind:
            self.link_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "address" and self.capture_address:
            address = text(" ".join(self.address_parts))
            if address:
                self.addresses.append((address, self.contact_scope_depth is not None))
            self.capture_address = False
            self.address_parts = []
        if tag == "a" and self.link_kind:
            if self.link_kind == "phone":
                label = " ".join(self.link_parts)
                values = _phone_numbers(label) or _phone_numbers(self.link_value)
                target = self.scoped_phones if self.link_in_scope else self.all_phones
                for value in values:
                    if value not in target:
                        target.append(value)
            else:
                target = self.scoped_emails if self.link_in_scope else self.all_emails
                if "@" in self.link_value and self.link_value not in target:
                    target.append(self.link_value)
            self.link_kind = None
            self.link_value = ""
            self.link_parts = []
        if tag == "div":
            if self.contact_scope_depth == self.div_depth:
                self.contact_scope_depth = None
            self.div_depth = max(0, self.div_depth - 1)

    @property
    def address(self) -> str | None:
        scoped = [value for value, in_scope in self.addresses if in_scope]
        fallback = [value for value, _ in self.addresses]
        values = scoped or fallback
        return values[0] if values else None

    @property
    def phones(self) -> list[str]:
        return self.scoped_phones if self.saw_contact_scope else self.all_phones

    @property
    def emails(self) -> list[str]:
        return self.scoped_emails if self.saw_contact_scope else self.all_emails


def _phone_numbers(value: str) -> list[str]:
    """Normaliza telefone brasileiro e expande sufixos como 3324-5903/5904."""
    pattern = re.compile(
        r"(?<!\d)(?:\+?55\s*)?\(?([1-9]\d)\)?[\s.-]*"
        r"(\d{4,5})[\s.-]*(\d{4})(?!\d)"
    )
    numbers = ["".join(match.groups()) for match in pattern.finditer(value)]
    if numbers:
        first = numbers[0]
        for suffix in re.findall(r"/\s*(\d{4})(?!\d)", value):
            expanded = first[:6] + suffix
            if expanded not in numbers:
                numbers.append(expanded)
    return numbers


def parse_directory_index(html: str, kind: str, path_prefix: str) -> list[AgencyDirectoryCandidate]:
    parser = _DirectoryIndexParser(kind, path_prefix)
    parser.feed(html)
    unique = {item.source_url: item for item in parser.items}
    return list(unique.values())


def parse_agency_detail(
    html: str,
) -> tuple[
    str | None,
    str | None,
    list[str],
    list[str],
    str,
    str | None,
    float | None,
    float | None,
]:
    parser = _AgencyDetailParser()
    parser.feed(html)
    address = parser.address
    address_scope = (
        "municipal_headquarters"
        if (address or "").casefold().startswith("razão social: município de cuiabá")
        else "unit"
    )
    match = re.search(r"\b(\d{5})[-.\s]?(\d{3})\b", address or "")
    postal_code = "".join(match.groups()) if match else None
    return (
        address,
        postal_code,
        parser.phones,
        parser.emails,
        address_scope,
        parser.location_url,
        parser.longitude,
        parser.latitude,
    )


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
        pages = {index_url: str(response.payload)}
        page_pattern = rf'href=["\']({re.escape(path_prefix.rstrip("/"))}\?p=\d+)["\']'
        for href in sorted(set(re.findall(page_pattern, str(response.payload)))):
            page_url = urljoin(DIRECTORY_ROOT, href)
            try:
                pages[page_url] = str(http.get_text(page_url).payload)
            except HttpError as exc:
                raise AgencyDirectoryError(f"paginação oficial indisponível: {kind}") from exc
        for page_html in pages.values():
            parsed = parse_directory_index(page_html, kind, path_prefix)
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
                (
                    address,
                    postal_code,
                    phones,
                    emails,
                    address_scope,
                    location_url,
                    longitude,
                    latitude,
                ) = parse_agency_detail(body)
                slug = urlparse(candidate.source_url).path.rstrip("/").rsplit("/", 1)[-1]
                connection.execute(
                    "INSERT OR REPLACE INTO agency_directory VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                        address_scope,
                        location_url,
                        longitude,
                        latitude,
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
