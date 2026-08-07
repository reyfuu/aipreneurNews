from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from dateutil import parser


def load_json(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def now_local(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: str) -> datetime:
    if not value:
        raise ValueError("empty date")
    return parser.parse(value)


def safe_truncate(value: str, limit: int, suffix: str = "...") -> str:
    value = (value or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - len(suffix))].rstrip() + suffix


def random_choice(items: Iterable[Path], seed: Optional[int] = None) -> Optional[Path]:
    choices = list(items)
    if not choices:
        return None
    if seed is not None:
        random.seed(seed)
    return random.choice(choices)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def setup_logger(name: str = __name__) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

