from __future__ import annotations

import os
import time

from services.audit import JsonlAuditSink
from services.telegram_control import TelegramAuthorizer, TelegramControlPlane
from src.telegram_bot import build_worker_from_env


def main() -> None:
    authorizer = TelegramAuthorizer()
    control = TelegramControlPlane(
        authorizer,
        audit_sink=JsonlAuditSink(
            os.environ.get("TELEGRAM_AUDIT_PATH", "data/audit/telegram.jsonl")
        ),
    )
    worker = build_worker_from_env(control)
    interval = max(0.5, float(os.environ.get("TELEGRAM_POLL_SECONDS", "2")))

    while True:
        try:
            worker.run_once()
        except Exception as exc:
            print(f"TELEGRAM_WORKER_ERROR:{type(exc).__name__}:{exc}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    main()
