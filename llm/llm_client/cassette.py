"""L1 — cassette record/replay.

A cassette is one JSON file per call, named by the request's content
hash: `{request, attempts: [{payload, response}, ...], final}`.
Record mode writes after a successful live call; replay mode serves the
recorded final response and raises `CassetteMiss` on any unknown request
— which is what makes CI API-free: an unexpected prompt is a loud
failure, never a silent live call.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


class CassetteMiss(KeyError):
    """A replay was requested for a request with no cassette."""


def request_key(canonical: dict) -> str:
    """Content hash of the canonical request (sort-keys JSON)."""
    blob = json.dumps(canonical, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


class CassetteStore:
    """Directory-backed cassette collection."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def has(self, key: str) -> bool:
        return self._path(key).exists()

    def record(self, key: str, request: dict, attempts: list[dict]) -> None:
        """Persist a completed call. `attempts` are {payload, response}
        pairs; the last attempt's response is what replay serves."""
        payload = {
            "request": request,
            "attempts": attempts,
            "final": attempts[-1]["response"],
        }
        self._path(key).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

    def replay(self, key: str) -> dict:
        """Return the recorded final response, or raise CassetteMiss."""
        path = self._path(key)
        if not path.exists():
            raise CassetteMiss(f"no cassette for request {key} in {self.directory}")
        return json.loads(path.read_text(encoding="utf-8"))["final"]

    def list(self) -> list[str]:
        return sorted(p.stem for p in self.directory.glob("*.json"))
