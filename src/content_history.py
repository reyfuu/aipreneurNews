"""History helpers for avoiding duplicate stories and footage."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import fcntl
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_TITLE_STOP_WORDS = {
    "a", "ai", "an", "and", "atau", "dan", "dari", "di", "in", "ini",
    "is", "itu", "ke", "model", "of", "on", "pada", "the", "to", "yang",
}


def normalize_url(value: str | None) -> str:
    if not value:
        return ""
    parsed = urlsplit(value.strip())
    query = urlencode(sorted(
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ))
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, query, ""))


def title_tokens(value: str | None) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", (value or "").lower())
        if token not in _TITLE_STOP_WORDS
    }


def titles_similar(left: str, right: str, threshold: float = 0.60) -> bool:
    left_tokens, right_tokens = title_tokens(left), title_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens) >= threshold


@dataclass
class HistoryIndex:
    source_urls: set[str] = field(default_factory=set)
    titles: list[str] = field(default_factory=list)
    footage_urls: set[str] = field(default_factory=set)
    footage_hashes: set[str] = field(default_factory=set)

    def story_seen(self, source_url: str = "", title: str = "") -> bool:
        normalized = normalize_url(source_url)
        return bool(
            (normalized and normalized in self.source_urls)
            or (title and any(titles_similar(title, old) for old in self.titles))
        )

    def footage_seen(self, url: str = "", digest: str = "") -> bool:
        normalized = normalize_url(url)
        return bool(
            (normalized and normalized in self.footage_urls)
            or (digest and digest in self.footage_hashes)
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_history_index(history_path: Path, output_root: Path, logger=None) -> HistoryIndex:
    index = HistoryIndex()
    history_path = Path(history_path)
    if history_path.exists():
        with history_path.open(encoding="utf-8") as source:
            for line_number, line in enumerate(source, start=1):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    if logger:
                        logger.warning("Skipping malformed history row %s", line_number)
                    continue
                if not isinstance(row, dict):
                    if logger:
                        logger.warning("Skipping malformed history row %s", line_number)
                    continue
                if "status" in row and row["status"] != "completed":
                    continue
                source_url = normalize_url(row.get("source_url"))
                if source_url:
                    index.source_urls.add(source_url)
                title = row.get("title")
                if title:
                    index.titles.append(title)
                footage_items = row.get("footage_items", [])
                if not isinstance(footage_items, list):
                    if logger:
                        logger.warning("Skipping malformed footage items in history row %s", line_number)
                    continue
                for footage in footage_items:
                    if not isinstance(footage, dict):
                        if logger:
                            logger.warning("Skipping malformed footage entry in history row %s", line_number)
                        continue
                    footage_url = normalize_url(footage.get("url"))
                    if footage_url:
                        index.footage_urls.add(footage_url)
                    digest = footage.get("sha256")
                    if digest:
                        index.footage_hashes.add(digest)
    for footage_path in Path(output_root).glob("*/footage/*"):
        if not footage_path.is_file():
            continue
        try:
            index.footage_hashes.add(sha256_file(footage_path))
        except OSError:
            if logger:
                logger.warning("Could not hash legacy footage %s", footage_path)
    return index


@contextmanager
def pipeline_lock(path: Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
