from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class NewsItem:
    title: str
    summary: str
    link: str
    source: str
    pub_date: datetime

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "summary": self.summary,
            "link": self.link,
            "source": self.source,
            "pub_date": self.pub_date.isoformat(),
        }

