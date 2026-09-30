from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AlertQualityMetrics:
    alerts_sent: int
    alerts_opened: int
    alerts_clicked: int
    alerts_muted: int
    alerts_ignored: int
    duplicate_alerts: int
    false_priority: int
    late_alerts: int
    plan_updates: int
    plan_invalidations: int

    @property
    def muted_rate(self) -> float:
        return self.alerts_muted / self.alerts_sent if self.alerts_sent else 0.0

    @property
    def duplicate_rate(self) -> float:
        return self.duplicate_alerts / self.alerts_sent if self.alerts_sent else 0.0

    @property
    def false_priority_rate(self) -> float:
        return self.false_priority / self.alerts_sent if self.alerts_sent else 0.0

    @property
    def late_rate(self) -> float:
        return self.late_alerts / self.alerts_sent if self.alerts_sent else 0.0
