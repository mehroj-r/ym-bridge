from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any
import uuid

import httpx


@dataclass(slots=True)
class ProbeResult:
    method: str
    path: str
    status_code: int
    content_type: str
    output_file: Path
    error: str = ""


@dataclass(slots=True)
class ProbeSpec:
    method: str
    path: str
    body: dict[str, Any] | None = None
    query: dict[str, str] | None = None


DEFAULT_PROBES: tuple[ProbeSpec, ...] = (
    ProbeSpec("GET", "/account/about"),
    ProbeSpec("GET", "/account/settings"),
    ProbeSpec("GET", "/disclaimers"),
    ProbeSpec("GET", "/rotor/wave/last"),
    ProbeSpec("GET", "/rotor/wave/settings", query={"seeds": "user:onyourwave"}),
    ProbeSpec(
        "POST",
        "/rotor/session/new",
        body={
            "includeTracksInResponse": True,
            "includeWaveModel": True,
            "interactive": True,
            "seeds": ["user:onyourwave"],
            "sessions": [],
        },
    ),
    ProbeSpec(
        "POST",
        "/collection/sync",
        body={
            "likedTracks": {"allValuesRequired": False, "revision": 0},
            "likedAlbums": {"allValuesRequired": False, "revision": 0},
            "likedArtists": {"allValuesRequired": False, "revision": 0},
            "likedPlaylists": {"playlists": []},
            "ownPlaylists": {"playlists": []},
            "presavedAlbums": {},
            "likedClips": {"allValuesRequired": False, "revision": 0},
        },
    ),
)


async def run_recon(
    *,
    base_url: str,
    oauth_token: str,
    device_id: str,
    user_agent: str,
    accept_language: str,
    music_client: str,
    content_type: str,
    device_header: str,
    output_dir: Path,
) -> list[ProbeResult]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[ProbeResult] = []

    headers = {
        "Accept": "application/json",
        "Accept-Language": accept_language,
        "User-Agent": user_agent,
        "X-Yandex-Music-Client": music_client,
        "X-Yandex-Music-Content-Type": content_type,
        "X-Yandex-Music-Device": device_header,
    }
    if oauth_token:
        headers["Authorization"] = f"OAuth {oauth_token}"

    async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=20) as http:
        for probe in DEFAULT_PROBES:
            method = probe.method
            path = probe.path
            body = probe.body

            params: dict[str, str] = {}
            if device_id:
                params["device-id"] = device_id
            if probe.query:
                params.update(probe.query)

            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            out_file = output_dir / f"{stamp}_{method}_{path.strip('/').replace('/', '_') or 'root'}.json"
            try:
                response = await http.request(
                    method,
                    path,
                    params=params or None,
                    json=body,
                    headers={
                        "X-Request-Id": str(uuid.uuid4()),
                        "X-Yandex-Music-Client-Now": datetime.now().astimezone().isoformat(timespec="seconds"),
                    },
                )
                payload = {
                    "method": method,
                    "path": path,
                    "query": params or None,
                    "request_json": body,
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": _best_effort_body(response),
                }
                result = ProbeResult(
                    method=method,
                    path=path,
                    status_code=response.status_code,
                    content_type=response.headers.get("content-type", ""),
                    output_file=out_file,
                )
            except Exception as exc:  # noqa: BLE001
                payload = {
                    "method": method,
                    "path": path,
                    "query": params or None,
                    "request_json": body,
                    "error": repr(exc),
                }
                result = ProbeResult(
                    method=method,
                    path=path,
                    status_code=0,
                    content_type="",
                    output_file=out_file,
                    error=repr(exc),
                )
            out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            results.append(result)

    return results


def _best_effort_body(response: httpx.Response) -> object:
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        text = response.text
        if len(text) > 5000:
            return text[:5000]
        return text
