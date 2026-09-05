"""Normalização determinística."""

from decimal import Decimal

import pytest

from radar_publico.normalize import NormalizeError, document, money, search_text, source_date


def test_money_accepts_portal_formats_without_float() -> None:
    assert money("             18.655,76") == Decimal("18655.76")
    assert money("188547.78") == Decimal("188547.78")
    assert money("") is None
    with pytest.raises(NormalizeError):
        money("1.234")


def test_dates_treat_sentinel_as_null() -> None:
    assert source_date("0000-00-00") is None
    assert source_date("2026-08-21").isoformat() == "2026-08-21"
    with pytest.raises(NormalizeError):
        source_date("2026-02-30")


def test_document_never_returns_cpf() -> None:
    assert document("00.000.000/0001-91") == ("cnpj", "00000000000191")
    assert document("00000000191") == ("cpf", None)
    assert document(None) == ("missing", None)
    assert document("123") == ("invalid", None)


def test_search_text_removes_accents() -> None:
    assert search_text("  Aquisição de Cadeiras ") == "aquisicao de cadeiras"
