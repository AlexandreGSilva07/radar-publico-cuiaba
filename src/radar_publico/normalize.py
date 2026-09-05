"""Normalizadores puros usados pelo ETL."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation


class NormalizeError(ValueError):
    """Valor de origem não pode ser normalizado com segurança."""


def money(value: object) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip().replace("R$", "").replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise NormalizeError(f"valor monetário inválido: {value!r}") from exc
    exponent = result.as_tuple().exponent
    if not isinstance(exponent, int):
        raise NormalizeError("valor monetário não é finito")
    if exponent < -2:
        raise NormalizeError("valor monetário possui mais de duas casas")
    return result.quantize(Decimal("0.01"))


def source_date(value: object) -> date | None:
    if value is None or str(value).strip() in {"", "0000-00-00"}:
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise NormalizeError(f"data inválida: {value!r}") from exc


def text(value: object) -> str | None:
    if value is None:
        return None
    result = " ".join(str(value).split())
    return result or None


def search_text(value: object) -> str:
    normalized = text(value) or ""
    ascii_text = unicodedata.normalize("NFKD", normalized).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.casefold()).strip()


def document(value: object) -> tuple[str, str | None]:
    digits = re.sub(r"\D", "", "" if value is None else str(value))
    if not digits:
        return "missing", None
    if len(digits) == 11:
        return "cpf", None
    if len(digits) == 14 and valid_cnpj(digits):
        return "cnpj", digits
    return "invalid", None


def masked_cpf(value: object) -> str | None:
    """Return a display-safe CPF mask without retaining the full identifier."""
    digits = re.sub(r"\D", "", "" if value is None else str(value))
    if len(digits) != 11:
        return None
    return f"***.{digits[3:6]}.{digits[6:9]}-**"


def valid_cnpj(value: str) -> bool:
    if len(value) != 14 or not value.isdigit() or len(set(value)) == 1:
        return False
    base = value[:12]
    first = _cnpj_digit(base, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))
    second = _cnpj_digit(base + first, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))
    return value[-2:] == first + second


def _cnpj_digit(value: str, weights: tuple[int, ...]) -> str:
    remainder = sum(int(number) * weight for number, weight in zip(value, weights)) % 11
    return str(0 if remainder < 2 else 11 - remainder)
