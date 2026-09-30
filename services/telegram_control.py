from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class TelegramRole(str, Enum):
    VIEWER = "VIEWER"
    RESEARCH = "RESEARCH"
    OPERATOR = "OPERATOR"
    ADMIN = "ADMIN"


@dataclass(frozen=True)
class TelegramPrincipal:
    user_id: str
    chat_id: str
    role: TelegramRole


@dataclass(frozen=True)
class TelegramResponse:
    text: str
    buttons: tuple[tuple[tuple[str, str], ...], ...] = ()


@dataclass
class FixedWindowRateLimiter:
    limit: int = 10
    window_seconds: float = 60.0
    _events: dict[str, list[float]] = field(default_factory=dict)

    def allow(self, key: str, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        events = [stamp for stamp in self._events.get(key, []) if current - stamp < self.window_seconds]
        if len(events) >= self.limit:
            self._events[key] = events
            return False
        events.append(current)
        self._events[key] = events
        return True


@dataclass
class AlertDeduplicator:
    cooldown_seconds: float = 900.0
    _last_sent: dict[str, float] = field(default_factory=dict)

    def allow(self, dedup_key: str, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        previous = self._last_sent.get(dedup_key)
        if previous is not None and current - previous < self.cooldown_seconds:
            return False
        self._last_sent[dedup_key] = current
        return True


class TelegramAuthorizer:
    def __init__(
        self,
        principals: dict[tuple[str, str], TelegramPrincipal] | None = None,
    ):
        self.principals = principals or self._from_env()

    @staticmethod
    def _from_env() -> dict[tuple[str, str], TelegramPrincipal]:
        # Format: "user_id:chat_id:ROLE,user_id:chat_id:ROLE"
        raw = os.environ.get("TELEGRAM_AUTHORIZED_PRINCIPALS", "")
        out: dict[tuple[str, str], TelegramPrincipal] = {}
        for item in raw.split(","):
            parts = [x.strip() for x in item.split(":")]
            if len(parts) != 3:
                continue
            user_id, chat_id, role = parts
            try:
                out[(user_id, chat_id)] = TelegramPrincipal(
                    user_id=user_id,
                    chat_id=chat_id,
                    role=TelegramRole(role),
                )
            except ValueError:
                continue
        return out

    def authorize(self, user_id: str, chat_id: str) -> TelegramPrincipal | None:
        return self.principals.get((str(user_id), str(chat_id)))


class TelegramControlPlane:
    READ_COMMANDS = {
        "/start",
        "/help",
        "/status",
        "/gc",
        "/oi",
        "/gex",
        "/levels",
        "/expiry",
        "/regime",
        "/alerts",
        "/report",
    }

    def __init__(
        self,
        authorizer: TelegramAuthorizer,
        *,
        rate_limiter: FixedWindowRateLimiter | None = None,
        alert_deduplicator: AlertDeduplicator | None = None,
        audit_sink: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.authorizer = authorizer
        self.rate_limiter = rate_limiter or FixedWindowRateLimiter()
        self.alert_deduplicator = alert_deduplicator or AlertDeduplicator()
        self.audit_sink = audit_sink

    def _audit(self, principal: TelegramPrincipal | None, action: str, result: str) -> None:
        if self.audit_sink:
            self.audit_sink({
                "actor_user_id": principal.user_id if principal else None,
                "chat_id": principal.chat_id if principal else None,
                "action": action,
                "result": result,
                "timestamp": time.time(),
            })

    @staticmethod
    def _buttons():
        return (
            (
                ("GEX", "gex"),
                ("OI", "oi"),
                ("LEVELS", "levels"),
            ),
            (
                ("EXPIRY", "expiry"),
                ("CHART", "chart"),
            ),
        )

    def handle(
        self,
        *,
        user_id: str,
        chat_id: str,
        command: str,
        market_state: Any | None = None,
    ) -> TelegramResponse:
        principal = self.authorizer.authorize(user_id, chat_id)
        if principal is None:
            self._audit(None, command, "UNAUTHORIZED")
            return TelegramResponse("UNAUTHORIZED")

        if not self.rate_limiter.allow(f"{principal.user_id}:{principal.chat_id}"):
            self._audit(principal, command, "RATE_LIMIT")
            return TelegramResponse("RATE_LIMITED")

        command = command.strip().split()[0].lower()
        if command not in self.READ_COMMANDS:
            self._audit(principal, command, "COMMAND_DISABLED")
            return TelegramResponse("COMMAND_DISABLED")

        if command in {"/start", "/help"}:
            response = TelegramResponse(
                "OI POSITIONING INTELLIGENCE\n\nCommands: /status /gc /oi /gex /levels /expiry /regime /alerts /report",
                self._buttons(),
            )
        elif command == "/status":
            status = getattr(market_state, "data_status", "UNAVAILABLE") if market_state else "UNAVAILABLE"
            response = TelegramResponse(
                f"STATUS\nData: {status}\nAge: {getattr(market_state, 'data_age_seconds', None)}"
            )
        elif market_state is None:
            response = TelegramResponse("DATA_UNAVAILABLE")
        elif command in {"/gc", "/report"}:
            response = TelegramResponse(
                self._summary(market_state),
                self._buttons(),
            )
        elif command == "/gex":
            response = TelegramResponse(
                f"GEX\nNet GEX: {market_state.gex}\nGamma Flip: {market_state.gamma_flip}\n"
                f"Call Wall: {market_state.call_wall}\nPut Wall: {market_state.put_wall}"
            )
        elif command == "/oi":
            response = TelegramResponse(
                f"OI\nTotal: {market_state.oi}\nΔOI: {market_state.oi_change}"
            )
        elif command == "/levels":
            response = TelegramResponse(
                f"LEVELS\nGamma Flip: {market_state.gamma_flip}\n"
                f"Call Wall: {market_state.call_wall}\nPut Wall: {market_state.put_wall}"
            )
        elif command == "/expiry":
            response = TelegramResponse("EXPIRY\nUse the dashboard/API drilldown for the current expiry matrix.")
        elif command == "/regime":
            response = TelegramResponse(
                f"REGIME\nPositioning: {market_state.positioning_regime}\n"
                f"Volatility: {market_state.volatility_regime}"
            )
        else:
            response = TelegramResponse("ALERTS\nAlert control is available to operators after alert configuration.")
        self._audit(principal, command, "OK")
        return response

    @staticmethod
    def _summary(state: Any) -> str:
        return (
            f"GC\nPrice: {state.price}\n"
            f"Positioning: {state.positioning_regime}\n"
            f"Gamma Flip: {state.gamma_flip}\n"
            f"Call Wall: {state.call_wall}\n"
            f"Put Wall: {state.put_wall}\n"
            f"Net GEX: {state.gex}\n"
            f"Data: {state.data_status.value if hasattr(state.data_status, 'value') else state.data_status}\n"
            f"Age: {state.data_age_seconds}\n"
            f"Quality: {state.data_quality:.2f}"
        )


def emit_alert(
    *,
    alert_type: str,
    dedup_key: str,
    severity: str,
    symbol: str,
    evidence: dict[str, Any],
    sender: Callable[[str], None],
    deduplicator: AlertDeduplicator,
) -> bool:
    if not deduplicator.allow(dedup_key):
        return False
    payload = (
        f"[{severity}] {symbol} {alert_type}\n"
        f"Evidence: {evidence}"
    )
    sender(payload)
    return True
