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
