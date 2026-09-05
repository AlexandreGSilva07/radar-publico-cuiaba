"""Persistência Bronze imutável e atômica."""

from __future__ import annotations

import gzip
import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BronzeObject:
    content_hash: str
    relative_path: str
    path: Path


def _safe(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.=-]", "_", value)
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("componente de caminho inválido")
    return cleaned


class BronzeStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def write(self, resource: str, year: int, page: int, content: bytes) -> BronzeObject:
        digest = hashlib.sha256(content).hexdigest()
        relative = Path(_safe(resource)) / str(year) / f"page-{page:06d}-{digest}.json.gz"
        destination = (self.root / relative).resolve()
        if self.root not in destination.parents:
            raise ValueError("caminho Bronze escapou da raiz")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            return BronzeObject(digest, str(relative), destination)

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".bronze-", suffix=".tmp", dir=destination.parent
        )
        try:
            with os.fdopen(descriptor, "wb") as raw:
                with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
                    compressed.write(content)
                raw.flush()
                os.fsync(raw.fileno())
            os.replace(temporary_name, destination)
        except Exception:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
            raise
        return BronzeObject(digest, str(relative), destination)

    @staticmethod
    def read(obj: BronzeObject) -> bytes:
        with gzip.open(obj.path, "rb") as source:
            content = source.read()
        if hashlib.sha256(content).hexdigest() != obj.content_hash:
            raise ValueError("hash Bronze divergente")
        return content
