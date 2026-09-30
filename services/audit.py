from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

class JsonlAuditSink:
    def __init__(self, path: str | Path = "data/audit/telegram.jsonl"):
        self.path = Path(path)
        self._lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, event: dict[str, Any]) -> None:
        payload = dict(event)
        payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str) + "\n")
