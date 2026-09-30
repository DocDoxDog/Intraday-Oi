from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class NotificationPreferences:
    critical_news: bool = True
    market_news: bool = True
    oi_change: bool = False
    gex_change: bool = False
    plan_change: bool = True
    morning_brief: bool = True
    quiet_hours_start: int | None = None
    quiet_hours_end: int | None = None

    def in_quiet_hours(self, hour: int) -> bool:
        if self.quiet_hours_start is None or self.quiet_hours_end is None:
            return False
        if self.quiet_hours_start == self.quiet_hours_end:
            return True
        if self.quiet_hours_start < self.quiet_hours_end:
            return self.quiet_hours_start <= hour < self.quiet_hours_end
        return hour >= self.quiet_hours_start or hour < self.quiet_hours_end

    def allows(self, event_type: str, *, hour: int) -> bool:
        if self.in_quiet_hours(hour) and event_type.upper() != 'CRITICAL_NEWS':
            return False
        mapping = {
            'CRITICAL_NEWS': self.critical_news,
            'MARKET_NEWS': self.market_news,
            'OI_CHANGE': self.oi_change,
            'GEX_CHANGE': self.gex_change,
            'PLAN_CHANGE': self.plan_change,
            'MORNING_BRIEF': self.morning_brief,
        }
        return bool(mapping.get(event_type.upper(), False))