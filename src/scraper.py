from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import feedparser

from .models import NewsItem
from .utils import now_utc, parse_datetime, load_json


logger = logging.getLogger(__name__)


@dataclass
class FeedConfig:
    name: str
    url: str


def load_feed_config(path: Path) -> List[FeedConfig]:
    data = load_json(path)
    return [FeedConfig(**feed) for feed in data.get("feeds", [])]


def _entry_to_datetime(entry) -> Optional[datetime]:
    if hasattr(entry, "published") and entry.published:
        try:
            return parse_datetime(entry.published)
        except Exception:
            pass
    if hasattr(entry, "updated") and entry.updated:
        try:
            return parse_datetime(entry.updated)
        except Exception:
            pass
    if getattr(entry, "published_parsed", None):
        return datetime(*entry.published_parsed[:6], tzinfo=None)
    return None


def scrape_feed(feed: FeedConfig, limit_per_source: int = 8) -> List[NewsItem]:
    parsed = feedparser.parse(feed.url)
    if getattr(parsed, "bozo", False):
        logger.warning("Feed parse issue for %s: %s", feed.name, parsed.bozo_exception)

    items: List[NewsItem] = []
    for entry in parsed.entries[:limit_per_source]:
        pub_date = _entry_to_datetime(entry)
        if not pub_date:
            continue
        raw_summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
        # Decode HTML entities (&#8217; etc.) and strip any HTML tags from feed text.
        summary = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", raw_summary)).split())
        title = " ".join(html.unescape(getattr(entry, "title", "") or "").split())
        link = (getattr(entry, "link", "") or "").strip()
        if not title or not link:
            continue
        if pub_date.tzinfo is None:
            pub_date = pub_date.replace(tzinfo=datetime.utcnow().astimezone().tzinfo)
        items.append(
            NewsItem(
                title=title,
                summary=summary,
                link=link,
                source=feed.name,
                pub_date=pub_date,
            )
        )
    return items


def scrape_recent_news(
    feeds_file: Path,
    *,
    window_min_hours: int = 6,
    window_max_hours: int = 12,
    limit_per_source: int = 8,
    top_n: int = 5,
) -> List[NewsItem]:
    feeds = load_feed_config(feeds_file)
    now = now_utc()
    min_time = now - timedelta(hours=window_max_hours)
    max_time = now - timedelta(hours=window_min_hours)
    logger.info("Filtering news between %s and %s (UTC)", min_time, max_time)

    all_items: List[NewsItem] = []
    for feed in feeds:
        items = scrape_feed(feed, limit_per_source=limit_per_source)
        for item in items:
            # Normalized to UTC if no tz info; keep as is for robust filtering
            item_pub = item.pub_date
            if item_pub.tzinfo is None:
                item_pub = item_pub.replace(tzinfo=now.tzinfo)
            if min_time <= item_pub <= max_time:
                all_items.append(item)

    all_items.sort(key=lambda x: x.pub_date, reverse=True)
    return all_items[:top_n]

