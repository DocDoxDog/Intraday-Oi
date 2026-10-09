from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NewsProvenance:
    provenance_id: str
    source: str
    url: str
    published_at: datetime
    detected_at: datetime
    retrieval_method: str
    rights_status: str
    retention_policy: str
