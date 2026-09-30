from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AlertPolicy:
    max_alerts_per_hour: int = 6
    max_news_alerts_per_day: int = 20
    cooldown_minutes: int = 15
    same_story_cooldown_minutes: int = 60
    severity_threshold: str = "HIGH"
    digest_interval_minutes: int = 30
    quiet_hours_start: int | None = None
    quiet_hours_end: int | None = None

    def allows_severity(self, severity: str) -> bool:
        order = {"IGNORE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        return order.get(severity.upper(), 0) >= order.get(self.severity_threshold.upper(), 3)

    def in_quiet_hours(self, hour: int) -> bool:
        if self.quiet_hours_start is None or self.quiet_hours_end is None:
            return False
        if self.quiet_hours_start == self.quiet_hours_end:
            return True
        if self.quiet_hours_start < self.quiet_hours_end:
            return self.quiet_hours_start <= hour < self.quiet_hours_end
        return hour >= self.quiet_hours_start or hour < self.quiet_hours_end


from collections import deque
from datetime import datetime, timezone


class AlertGate:
    """Stateful anti-spam gate for customer-facing alerts."""

    def __init__(self, policy: AlertPolicy | None = None) -> None:
        self.policy = policy or AlertPolicy()
        self._hour = deque()
        self._day = deque()
        self._story_last_sent: dict[str, datetime] = {}

    @staticmethod
    def _trim(events: deque, now: datetime, seconds: int) -> None:
        cutoff = now.timestamp() - seconds
        while events and events[0] < cutoff:
            events.popleft()

    def allow(
        self,
        *,
        severity: str,
        story_cluster_id: str,
        now: datetime | None = None,
    ) -> tuple[bool, str]:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("NOW_MUST_BE_TIMEZONE_AWARE")
        if not self.policy.allows_severity(severity):
            return False, "SEVERITY_BELOW_THRESHOLD"
        if self.policy.in_quiet_hours(current.hour) and severity.upper() != "CRITICAL":
            return False, "QUIET_HOURS"

        self._trim(self._hour, current, 3600)
        self._trim(self._day, current, 86400)
        if len(self._hour) >= self.policy.max_alerts_per_hour:
            return False, "HOURLY_BUDGET"
        if len(self._day) >= self.policy.max_news_alerts_per_day:
            return False, "DAILY_BUDGET"

        previous = self._story_last_sent.get(story_cluster_id)
        if previous is not None:
            elapsed_minutes = (current - previous).total_seconds() / 60.0
            if elapsed_minutes < self.policy.same_story_cooldown_minutes:
                return False, "SAME_STORY_COOLDOWN"
            if elapsed_minutes < self.policy.cooldown_minutes:
                return False, "COOLDOWN"

        stamp = current
        timestamp = stamp.timestamp()
        self._hour.append(timestamp)
        self._day.append(timestamp)
        self._story_last_sent[story_cluster_id] = stamp
        return True, "ALLOWED"
