"""Cliente HTTP responsável para fontes públicas."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx


class HttpError(RuntimeError):
    def __init__(self, category: str, attempts: int, status: int | None, duration_ms: int) -> None:
        self.category = category
        self.attempts = attempts
        self.status = status
        self.duration_ms = duration_ms
        message = (
            f"HTTP category={category} status={status} "
            f"attempts={attempts} duration_ms={duration_ms}"
        )
        super().__init__(message)


@dataclass(frozen=True)
class Response:
    payload: Any
    content: bytes
    status: int
    attempts: int
    duration_ms: int


class PublicClient:
    def __init__(
        self,
        *,
        timeout: float = 20,
        attempts: int = 3,
        backoff: float = 0.3,
        client: httpx.Client | None = None,
    ) -> None:
        self.attempts = attempts
        self.backoff = backoff
        self.client = client or httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                "User-Agent": (
                    "radar-publico-cuiaba/0.1 "
                    "(+https://github.com/AlexandreGSilva07/radar-publico-cuiaba)"
                ),
            },
        )
        self.owns_client = client is None

    def __enter__(self) -> PublicClient:
        return self

    def __exit__(self, *_: object) -> None:
        if self.owns_client:
            self.client.close()

    def get(self, url: str) -> Response:
        return self._request("GET", url)

    def get_text(self, url: str) -> Response:
        return self._request("GET", url, expect_json=False)

    def post_form(self, url: str, fields: dict[str, str]) -> Response:
        files = {key: (None, value) for key, value in fields.items()}
        return self._request("POST", url, files=files)

    def _request(
        self,
        method: str,
        url: str,
        *,
        files: dict[str, tuple[None, str]] | None = None,
        expect_json: bool = True,
    ) -> Response:
        started = time.monotonic()
        for attempt in range(1, self.attempts + 1):
            try:
                response = self.client.request(method, url, files=files)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt < self.attempts:
                    time.sleep(self.backoff * 2 ** (attempt - 1))
                    continue
                raise self._error("transport", attempt, None, started) from exc
            if response.status_code in {408, 429} or response.status_code >= 500:
                if attempt < self.attempts:
                    time.sleep(self.backoff * 2 ** (attempt - 1))
                    continue
                raise self._error("transient", attempt, response.status_code, started)
            if not 200 <= response.status_code < 300:
                raise self._error("status", attempt, response.status_code, started)
            if expect_json:
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise self._error("json", attempt, response.status_code, started) from exc
            else:
                payload = response.text
            return Response(
                payload, response.content, response.status_code, attempt, self._elapsed(started)
            )
        raise AssertionError("retry terminou sem retorno")

    def _error(self, category: str, attempt: int, status: int | None, started: float) -> HttpError:
        return HttpError(category, attempt, status, self._elapsed(started))

    @staticmethod
    def _elapsed(started: float) -> int:
        return round((time.monotonic() - started) * 1000)
