from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class NewsSeverity(str, Enum):
    CRITICAL="CRITICAL"; HIGH="HIGH"; MEDIUM="MEDIUM"; LOW="LOW"; IGNORE="IGNORE"

@dataclass(frozen=True)
class NewsItem:
    news_id: str
    headline: str
    source: str
    url: str
    published_at: datetime
    detected_at: datetime
    event_time: datetime | None = None
    language: str = "en"
    category: str = "UNKNOWN"
    entities: tuple[str,...] = ()
    assets: tuple[str,...] = ()
    severity: NewsSeverity = NewsSeverity.MEDIUM
    def as_legacy_dict(self) -> dict:
        return {"source":self.source,"external_id":self.news_id,"headline":self.headline,"summary":None,"url":self.url,"published_at":self.published_at.isoformat(),"detected_at":self.detected_at.isoformat(),"category":self.category,"relevance":"HIGH" if self.severity in {NewsSeverity.CRITICAL,NewsSeverity.HIGH} else "MEDIUM","rights_status":"SOURCE_POLICY_REVIEW","market_channels":["MACRO" if self.category=="MACRO" else "RISK_SENTIMENT"],"freshness":"FRESH"}
