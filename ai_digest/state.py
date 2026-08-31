import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ai_digest.config import DigestConfig


@dataclass(frozen=True)
class StatePaths:
    seen_links_blob: str
    last_sent_blob: str


def state_paths() -> StatePaths:
    return StatePaths(
        seen_links_blob=os.environ.get("DIGEST_SEEN_LINKS_BLOB_PATH", "state/seen-links.json"),
        last_sent_blob=os.environ.get("DIGEST_LAST_SENT_BLOB_PATH", "state/last-sent.txt"),
    )


def use_blob_state() -> bool:
    return bool(os.environ.get("BLOB_READ_WRITE_TOKEN"))


def load_seen_links(config: DigestConfig) -> set[str]:
    if use_blob_state():
        return load_seen_links_blob(config)
    return load_seen_links_file(config.state_file)


def save_seen_links(config: DigestConfig, links: set[str]) -> None:
    if use_blob_state():
        save_seen_links_blob(config, links)
        return
    save_seen_links_file(config.state_file, links)


def load_last_sent_date(config: DigestConfig) -> Optional[str]:
    if use_blob_state():
        return load_last_sent_blob(config)
    return load_last_sent_file(config.last_sent_file)


def save_last_sent_date(config: DigestConfig, value: str) -> None:
    if use_blob_state():
        save_last_sent_blob(config, value)
        return
    save_last_sent_file(config.last_sent_file, value)


def load_seen_links_file(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(json.loads(path.read_text()))


def save_seen_links_file(path: Path, links: set[str]) -> None:
    path.write_text(json.dumps(sorted(links), indent=2))


def load_last_sent_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    value = path.read_text().strip()
    return value or None


def save_last_sent_file(path: Path, value: str) -> None:
    path.write_text(value)


def load_seen_links_blob(config: DigestConfig) -> set[str]:
    payload = asyncio.run(read_blob_text(state_paths().seen_links_blob))
    if not payload:
        return set()
    return set(json.loads(payload))


def save_seen_links_blob(config: DigestConfig, links: set[str]) -> None:
    payload = json.dumps(sorted(links), indent=2)
    asyncio.run(write_blob_text(state_paths().seen_links_blob, payload, "application/json"))


def load_last_sent_blob(config: DigestConfig) -> Optional[str]:
    payload = asyncio.run(read_blob_text(state_paths().last_sent_blob))
    if not payload:
        return None
    value = payload.strip()
    return value or None


def save_last_sent_blob(config: DigestConfig, value: str) -> None:
    asyncio.run(write_blob_text(state_paths().last_sent_blob, value, "text/plain"))


async def read_blob_text(pathname: str) -> str:
    from vercel.blob import AsyncBlobClient
    from vercel._internal.blob.errors import BlobNotFoundError

    client = AsyncBlobClient()
    try:
        response = await client.get(pathname, access="private")
    except BlobNotFoundError:
        return ""
    if response is None:
        return ""
    chunks = []
    async for chunk in response.stream:
        chunks.append(chunk)
    return b"".join(chunks).decode("utf-8")


async def write_blob_text(pathname: str, payload: str, content_type: str) -> None:
    from vercel.blob import AsyncBlobClient

    client = AsyncBlobClient()
    await client.put(
        pathname,
        payload.encode("utf-8"),
        access="private",
        overwrite=True,
        content_type=content_type,
    )
