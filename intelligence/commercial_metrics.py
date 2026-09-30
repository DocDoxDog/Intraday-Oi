from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class UnitEconomics:
    revenue: float
    payment_fees: float
    market_data_cost: float
    news_data_cost: float
    aws_cost: float
    supabase_cost: float
    llm_cost: float
    storage_egress_cost: float
    support_cost: float

    @property
    gross_profit(self) -> float:
        return self.revenue - sum((
            self.payment_fees, self.market_data_cost, self.news_data_cost,
            self.aws_cost, self.supabase_cost, self.llm_cost,
            self.storage_egress_cost, self.support_cost,
        ))

    @property
    gross_margin(self) -> float:
        return self.gross_profit / self.revenue if self.revenue else 0.0

@dataclass(frozen=True)
class ProductMetrics:
    active_users: int
    telegram_active_users: int
    dashboard_active_users: int
    alerts_per_user: float
    muted_rate: float
    retention_rate: float
    trial_to_paid_rate: float
    churn_rate: float
    arpu: float
    mrr: float

def arpu(revenue: float, paying_customers: int) -> float:
    return revenue / paying_customers if paying_customers else 0.0

def mrr(monthly_recurring_revenue: float) -> float:
    return max(0.0, monthly_recurring_revenue)