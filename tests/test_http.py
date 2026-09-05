"""Política HTTP sem chamadas externas."""

import pytest
import respx

from radar_publico.http import HttpError, PublicClient

URL = "https://example.test/api"


@respx.mock
def test_success_and_minimum_headers() -> None:
    route = respx.get(URL).respond(200, json={"ok": True})
    with PublicClient(backoff=0) as client:
        result = client.get(URL)

    assert result.payload == {"ok": True}
    assert route.calls[0].request.headers["Accept"] == "application/json"


@respx.mock
def test_503_retries_but_404_and_redirect_do_not() -> None:
    transient = respx.get(URL).respond(503, text="private body")
    with PublicClient(attempts=2, backoff=0) as client:
        with pytest.raises(HttpError, match="attempts=2") as error:
            client.get(URL)
    assert transient.call_count == 2
    assert "private body" not in str(error.value)

    respx.get(URL).respond(302, headers={"Location": "https://other.test"})
    with PublicClient(backoff=0) as client:
        with pytest.raises(HttpError, match="status=302"):
            client.get(URL)


@respx.mock
def test_post_multipart_contains_declared_fields() -> None:
    route = respx.post(URL).respond(200, json=[])
    with PublicClient(backoff=0) as client:
        client.post_form(URL, {"filters": "{}", "pagination": "{}"})
    body = route.calls[0].request.content
    assert b'name="filters"' in body
    assert b'name="pagination"' in body
